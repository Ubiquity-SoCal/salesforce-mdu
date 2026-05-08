"""
Smart-match unlinked SiteTracker_Project__c records to Opportunities.

Strategy:
  1. Normalize ST project name (lowercase, strip ST naming prefixes, strip
     punctuation, collapse whitespace).
  2. Score against every Opp.Name and Opp.Agreement_Name__c using multiple
     rapidfuzz scorers; take max.
  3. Bucket by confidence:
       >= 92 -> AUTO   (will apply if --apply)
       80-91 -> REVIEW (Taylor review queue)
       < 80  -> NOMATCH (Taylor review, no suggestion)

Default = preview only. Pass --apply to write links.
"""
import sys
import re
import csv
import argparse
from datetime import datetime
from pathlib import Path
from rapidfuzz import process, fuzz
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true', help='Apply AUTO-bucket links to SF')
p.add_argument('--auto-threshold', type=int, default=92)
p.add_argument('--review-threshold', type=int, default=80)
args = p.parse_args()

OUT_DIR = Path('C:/Users/cass/Work_Projects/SalesForce/audit_logs')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = OUT_DIR / f'smart_link_sitetracker_{TS}.csv'

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)

# ---------- normalization ----------

# ST naming patterns we want to strip away to expose the property name:
#   STATE_CITY_MDU_<name>          e.g. Encinitas_MDU_Sandpiper Point
#   STATE_CITY_SA##_FB##_<name>    e.g. CA_CARLSBAD_SA07_FB03_SunnyCreekApts
#   STATE_DFW_Feeder_<city>_MDU_<name>
#   STATE_<MARKET>_<NAME>_GROUP    e.g. TX_DFW_THE_MCCALIP_GROUP
PREFIX_PATTERNS = [
    re.compile(r'^[a-z]{2,}_[a-z]+_feeder_[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z ]+_mdu_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_sa\d+_fb\d+_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_sa\d+_', re.IGNORECASE),
    re.compile(r'^[a-z]{2,}_[a-z]+_', re.IGNORECASE),
]

def normalize(name: str) -> str:
    if not name:
        return ''
    s = name.strip()
    # Strip ST-style prefixes iteratively
    for _ in range(3):
        for pat in PREFIX_PATTERNS:
            new = pat.sub('', s)
            if new != s and len(new) >= 4:
                s = new
                break
    s = s.lower()
    # Replace separators with space
    s = re.sub(r'[_\-/]+', ' ', s)
    # Drop punctuation except & and digits
    s = re.sub(r'[^a-z0-9& ]', ' ', s)
    # Strip common boilerplate suffixes
    s = re.sub(r'\b(apartments|apartment|apts|community|hoa|the|llc|lp|inc)\b', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# ---------- pull data ----------

print("[INFO] Pulling unlinked SiteTracker projects...")
res = sf.query("""
    SELECT Id, Name, Site_Name__c, Monday_Name__c
    FROM SiteTracker_Project__c
    WHERE Opportunity__c = null
""")
unlinked = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    unlinked.extend(res['records'])
print(f"[INFO] {len(unlinked)} unlinked ST projects")

print("[INFO] Pulling all Opps...")
res = sf.query("""
    SELECT Id, Name, Agreement_Name__c, StageName,
           Account.Name, Account.BillingCity, Account.BillingState
    FROM Opportunity
""")
opps = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    opps.extend(res['records'])
print(f"[INFO] {len(opps)} Opps")

# Build candidate corpus: each Opp can be matched on Name OR Agreement_Name__c
candidates = []  # (norm_string, opp_id, original_label, opp_name, stage)
for o in opps:
    if o.get('Name'):
        candidates.append((normalize(o['Name']), o['Id'], 'Opp.Name', o['Name'], o.get('StageName')))
    if o.get('Agreement_Name__c'):
        candidates.append((normalize(o['Agreement_Name__c']), o['Id'], 'Agreement_Name', o['Name'], o.get('StageName')))
# Drop empty norms
candidates = [c for c in candidates if c[0]]
norm_strings = [c[0] for c in candidates]

# ---------- match ----------

def score_match(query_norm):
    """Return (best_score, candidate_index) using max of token_set + WRatio."""
    if not query_norm:
        return (0, -1)
    # token_set is good for word-order/extra-word differences
    r1 = process.extractOne(query_norm, norm_strings, scorer=fuzz.token_set_ratio)
    r2 = process.extractOne(query_norm, norm_strings, scorer=fuzz.WRatio)
    best = r1 if r1[1] >= r2[1] else r2
    return (best[1], best[2])

results = []
for st in unlinked:
    raw_name = st.get('Site_Name__c') or st.get('Monday_Name__c') or st.get('Name')
    norm = normalize(raw_name)
    score, idx = score_match(norm)
    if idx >= 0:
        cand = candidates[idx]
        match_opp_id = cand[1]
        match_label = cand[2]
        match_opp_name = cand[3]
        match_stage = cand[4]
        match_norm = cand[0]
    else:
        match_opp_id = None
        match_opp_name = ''
        match_label = ''
        match_stage = ''
        match_norm = ''
    if score >= args.auto_threshold:
        bucket = 'AUTO'
    elif score >= args.review_threshold:
        bucket = 'REVIEW'
    else:
        bucket = 'NOMATCH'
    results.append({
        'st_id': st['Id'],
        'st_project_number': st['Name'],
        'st_site_name': raw_name,
        'st_norm': norm,
        'opp_id': match_opp_id,
        'opp_name': match_opp_name,
        'opp_stage': match_stage,
        'matched_via': match_label,
        'matched_norm': match_norm,
        'score': score,
        'bucket': bucket,
    })

# ---------- summary ----------

print("\n=== Smart match summary ===")
buckets = {'AUTO': 0, 'REVIEW': 0, 'NOMATCH': 0}
for r in results:
    buckets[r['bucket']] += 1
for k in ['AUTO', 'REVIEW', 'NOMATCH']:
    print(f"  {k:10s} {buckets[k]}")

print("\n=== AUTO (will apply if --apply) ===")
for r in [r for r in results if r['bucket'] == 'AUTO']:
    print(f"  [{r['score']:5.1f}] {r['st_project_number']} '{r['st_site_name']}' -> {r['opp_name']} [{r['opp_stage']}] (via {r['matched_via']})")

print("\n=== REVIEW (suggested match, needs human eyeball) ===")
for r in [r for r in results if r['bucket'] == 'REVIEW']:
    print(f"  [{r['score']:5.1f}] {r['st_project_number']} '{r['st_site_name']}' -> {r['opp_name']} [{r['opp_stage']}] (via {r['matched_via']})")

print("\n=== NOMATCH (no Opp candidate found) ===")
for r in [r for r in results if r['bucket'] == 'NOMATCH']:
    print(f"  {r['st_project_number']} '{r['st_site_name']}' (best score {r['score']})")

# ---------- write CSV ----------

with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    w.writeheader()
    w.writerows(results)
print(f"\n[INFO] CSV written: {OUT}")

# ---------- apply ----------

if args.apply:
    auto = [r for r in results if r['bucket'] == 'AUTO']
    print(f"\n[APPLY] Linking {len(auto)} AUTO matches...")
    applied = 0
    errors = 0
    for r in auto:
        try:
            sf.SiteTracker_Project__c.update(r['st_id'], {'Opportunity__c': r['opp_id']})
            sf.Opportunity.update(r['opp_id'], {'SiteTracker_Project_ID__c': r['st_project_number']})
            applied += 1
            print(f"  [LINKED] {r['st_project_number']} -> {r['opp_name']}")
        except Exception as e:
            errors += 1
            print(f"  [ERROR] {r['st_project_number']}: {e}")
    print(f"[APPLY DONE] Applied: {applied}, Errors: {errors}")
else:
    print("\n[INFO] Preview only. Re-run with --apply to write links.")
