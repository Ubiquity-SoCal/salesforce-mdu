"""
Tightened smart-matcher: ST_Project -> Opportunity.

Hardening over v1 (which produced false positives at score 100):
  1. Number-set gate: if both ST and Opp names contain digit sequences,
     the SETS must match. Catches "4750 Lafayette" vs "4501 Lafayette"
     and "Hallcraft Villas Mesa 2" vs "Hallcraft Villas Mesa 1".
  2. State gate: if ST name has a 2-letter state prefix (CA_, TX_, etc.),
     it must match Opp.Property_State__c (or Account.BillingState as fallback).
  3. Dual-scorer requirement: min(fuzz.ratio, fuzz.token_set_ratio) must clear
     threshold. Catches "MCCALIP_GROUP" vs "Skinner Clouse Group" (token_set
     hit 100 on overlap of "GROUP" but ratio was much lower).
  4. Test-data exclusion: skip ST records with TEST_SITE in name.

Buckets:
  AUTO    >= 92 dual-score AND all gates pass
  REVIEW  any failed gate, or score 75-91
  NOMATCH score < 75
"""
import sys
import re
import csv
import argparse
from datetime import datetime
from pathlib import Path
from rapidfuzz import process, fuzz
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true')
p.add_argument('--auto-threshold', type=int, default=92)
p.add_argument('--review-threshold', type=int, default=75)
args = p.parse_args()

OUT_DIR = Path('C:/Users/cass/Work_Projects/SalesForce/audit_logs')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = OUT_DIR / f'smart_link_v2_{TS}.csv'

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

# ---------- ST name parsing ----------

PREFIX_PATTERNS = [
    re.compile(r'^[a-z]{2,}_[a-z]+_feeder_[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_sa\d+_fb\d+_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_sa\d+_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_', re.IGNORECASE),
]

STATE_RE = re.compile(r'^([A-Z]{2})_', re.IGNORECASE)
STATE_FULL = {
    'CA': 'California', 'TX': 'Texas', 'AZ': 'Arizona', 'NE': 'Nebraska',
    'OK': 'Oklahoma', 'NM': 'New Mexico', 'CO': 'Colorado', 'UT': 'Utah',
}
FULL_TO_CODE = {v: k for k, v in STATE_FULL.items()}

def normalize(name: str) -> str:
    if not name: return ''
    s = name.strip()
    for _ in range(3):
        for pat in PREFIX_PATTERNS:
            new = pat.sub('', s)
            if new != s and len(new) >= 4:
                s = new; break
    s = s.lower()
    s = re.sub(r'[_\-/]+', ' ', s)
    s = re.sub(r'[^a-z0-9& ]', ' ', s)
    s = re.sub(r'\b(apartments|apartment|apts|community|hoa|the|llc|lp|inc|condos|condo|townhomes|townhouse)\b', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def state_code_from_st(name: str):
    if not name: return None
    m = STATE_RE.match(name)
    if not m: return None
    code = m.group(1).upper()
    return code if code in STATE_FULL else None

def opp_state_code(opp):
    pst = opp.get('Property_State__c')
    if pst:
        if len(pst) == 2: return pst.upper()
        return FULL_TO_CODE.get(pst, pst[:2].upper())
    acc = opp.get('Account') or {}
    bs = acc.get('BillingState')
    if bs:
        if len(bs) == 2: return bs.upper()
        return FULL_TO_CODE.get(bs, bs[:2].upper())
    return None

NUM_RE = re.compile(r'\d+')
def numbers(s):
    return set(NUM_RE.findall(s or ''))

def is_test_record(st_name):
    return 'TEST_SITE' in (st_name or '').upper() or 'TEST SITE' in (st_name or '').upper()

# ---------- pull data ----------

print("[INFO] Pulling unlinked SiteTracker projects...")
res = sf.query("""
    SELECT Id, Name, Site_Name__c, Monday_Name__c
    FROM SiteTracker_Project__c
    WHERE Opportunity__c = null
""")
unlinked = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True); unlinked.extend(res['records'])
print(f"[INFO] {len(unlinked)} unlinked ST projects")

print("[INFO] Pulling all Opps...")
res = sf.query("""
    SELECT Id, Name, Agreement_Name__c, StageName, Property_State__c,
           Account.Name, Account.BillingState
    FROM Opportunity
""")
opps = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True); opps.extend(res['records'])
print(f"[INFO] {len(opps)} Opps")

# Build candidate corpus: each Opp gets one or two entries (Name, Agreement_Name)
candidates = []  # (norm, opp_id, label, opp_name, stage, opp_state, opp_numbers)
for o in opps:
    opp_state = opp_state_code(o)
    if o.get('Name'):
        norm_n = normalize(o['Name'])
        if norm_n:
            candidates.append((norm_n, o['Id'], 'Opp.Name', o['Name'], o.get('StageName'), opp_state, numbers(o['Name'])))
    if o.get('Agreement_Name__c'):
        norm_a = normalize(o['Agreement_Name__c'])
        if norm_a:
            candidates.append((norm_a, o['Id'], 'Agreement_Name', o['Name'], o.get('StageName'), opp_state, numbers(o['Agreement_Name__c'])))
norm_strings = [c[0] for c in candidates]

# ---------- match each ST with gates ----------

def best_match(st_norm, st_state, st_numbers):
    # Get top 5 candidates by token_set; then re-score with ratio + apply gates.
    top = process.extract(st_norm, norm_strings, scorer=fuzz.token_set_ratio, limit=5)
    best = None
    for _, ts_score, idx in top:
        ratio_score = fuzz.ratio(st_norm, norm_strings[idx])
        dual = min(ts_score, ratio_score)
        cand = candidates[idx]
        cand_state = cand[5]
        cand_numbers = cand[6]

        # Gate: state mismatch
        state_ok = True
        if st_state and cand_state and st_state != cand_state:
            state_ok = False

        # Gate: number-set mismatch (only fails if both have numbers and sets differ)
        nums_ok = True
        if st_numbers and cand_numbers and st_numbers != cand_numbers:
            nums_ok = False

        record = {
            'idx': idx,
            'ts_score': ts_score,
            'ratio_score': ratio_score,
            'dual_score': dual,
            'state_ok': state_ok,
            'nums_ok': nums_ok,
            'cand': cand,
        }
        if best is None or dual > best['dual_score']:
            best = record
    return best

results = []
for st in unlinked:
    raw_name = st.get('Site_Name__c') or st.get('Monday_Name__c') or st.get('Name')
    if is_test_record(raw_name):
        results.append({
            'st_id': st['Id'], 'st_project_number': st['Name'], 'st_site_name': raw_name,
            'opp_id': None, 'opp_name': '', 'matched_via': '', 'opp_stage': '',
            'dual_score': 0, 'ts_score': 0, 'ratio_score': 0,
            'state_ok': True, 'nums_ok': True, 'bucket': 'TEST_SKIP',
        })
        continue

    norm = normalize(raw_name)
    st_state = state_code_from_st(raw_name)
    st_numbers = numbers(raw_name)

    bm = best_match(norm, st_state, st_numbers)
    if bm is None:
        results.append({
            'st_id': st['Id'], 'st_project_number': st['Name'], 'st_site_name': raw_name,
            'opp_id': None, 'opp_name': '', 'matched_via': '', 'opp_stage': '',
            'dual_score': 0, 'ts_score': 0, 'ratio_score': 0,
            'state_ok': True, 'nums_ok': True, 'bucket': 'NOMATCH',
        })
        continue

    cand = bm['cand']
    gates_pass = bm['state_ok'] and bm['nums_ok']
    if bm['dual_score'] >= args.auto_threshold and gates_pass:
        bucket = 'AUTO'
    elif bm['dual_score'] >= args.review_threshold or not gates_pass:
        bucket = 'REVIEW'
    else:
        bucket = 'NOMATCH'

    results.append({
        'st_id': st['Id'], 'st_project_number': st['Name'], 'st_site_name': raw_name,
        'opp_id': cand[1], 'opp_name': cand[3], 'matched_via': cand[2], 'opp_stage': cand[4],
        'dual_score': bm['dual_score'], 'ts_score': bm['ts_score'], 'ratio_score': bm['ratio_score'],
        'state_ok': bm['state_ok'], 'nums_ok': bm['nums_ok'], 'bucket': bucket,
    })

# ---------- summary ----------

print("\n=== Summary ===")
buckets = {'AUTO': 0, 'REVIEW': 0, 'NOMATCH': 0, 'TEST_SKIP': 0}
for r in results: buckets[r['bucket']] += 1
for k in ['AUTO', 'REVIEW', 'NOMATCH', 'TEST_SKIP']:
    print(f"  {k:10s} {buckets[k]}")

def fmt_row(r):
    gate_flags = []
    if not r['state_ok']: gate_flags.append('STATE-MISMATCH')
    if not r['nums_ok']:  gate_flags.append('NUM-MISMATCH')
    flags = (' [' + ','.join(gate_flags) + ']') if gate_flags else ''
    return f"  dual={r['dual_score']:5.1f} ts={r['ts_score']:5.1f} r={r['ratio_score']:5.1f} | {r['st_project_number']} '{r['st_site_name'][:50]}' -> {r['opp_name'][:50]} [{r['opp_stage']}] (via {r['matched_via']}){flags}"

print("\n=== AUTO (will apply if --apply) ===")
for r in [x for x in results if x['bucket']=='AUTO']: print(fmt_row(r))

print("\n=== REVIEW (Taylor) ===")
for r in [x for x in results if x['bucket']=='REVIEW']: print(fmt_row(r))

print("\n=== NOMATCH ===")
for r in [x for x in results if x['bucket']=='NOMATCH']: print(fmt_row(r))

print("\n=== TEST_SKIP ===")
for r in [x for x in results if x['bucket']=='TEST_SKIP']: print(f"  {r['st_project_number']} '{r['st_site_name']}'")

# ---------- write CSV ----------

with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    w.writeheader(); w.writerows(results)
print(f"\n[INFO] CSV: {OUT}")

# ---------- apply ----------

if args.apply:
    auto = [r for r in results if r['bucket']=='AUTO']
    print(f"\n[APPLY] Linking {len(auto)} AUTO matches...")
    applied = errors = 0
    for r in auto:
        try:
            sf.SiteTracker_Project__c.update(r['st_id'], {'Opportunity__c': r['opp_id']})
            sf.Opportunity.update(r['opp_id'], {'SiteTracker_Project_ID__c': r['st_project_number']})
            applied += 1
            print(f"  [LINKED] {r['st_project_number']} -> {r['opp_name']}")
        except Exception as e:
            errors += 1
            print(f"  [ERROR] {r['st_project_number']}: {e}")
    print(f"[APPLY DONE] {applied} linked, {errors} errors")
else:
    print("\n[INFO] Preview only. Re-run with --apply to write links.")
