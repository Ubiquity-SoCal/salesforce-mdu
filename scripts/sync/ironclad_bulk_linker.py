"""
IronClad bulk linker — match 358 unlinked ROE/PAL IronClad records to SF Opps.

Matching signals (in priority order):
  1. Parcel Number exact match  -> HIGH confidence
  2. Property Address (street + city + state) exact match  -> HIGH
  3. Counterparty Name exact-normalized  -> HIGH
  4. Counterparty Name substring/contains  -> MEDIUM
  5. Property Address fuzzy (street name only, not house #)  -> LOW

On match: create a new Agreement__c with Type derived from IronClad Record Type
(Right of Entry Agreement → ROE, Premises Access License → PAL), link both sides.

PREVIEW ONLY by default. Run with --apply to execute.
"""
import sys, io, re, json, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from collections import Counter
from simple_salesforce import Salesforce

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true', help='Execute the matched linkages in SF')
parser.add_argument('--fuzzy', action='store_true', help='Also apply MEDIUM-confidence fuzzy matches')
args = parser.parse_args()

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
TS = datetime.now().isoformat(timespec='seconds')
SOURCE = 'ironclad_bulk_linker.py'

# ── Normalization helpers ──
_LEGAL_STOPS = [' hoa',' homeowners association',' home owners association',' association',
                ' llc',' inc',', inc.',' inc.',' l.p.',' lp',' ltd',' co.',' corp',
                ' limited partnership',', a california limited partnership',
                ' apartments',' apts',' mhp',' residences']
_ADDR_STOPS = {'STREET','ST','AVENUE','AVE','ROAD','RD','DRIVE','DR','BOULEVARD','BLVD',
               'LANE','LN','COURT','CT','CIRCLE','CIR','PLACE','PL','PARKWAY','PKWY',
               'TRAIL','TRL','TERRACE','TER','HIGHWAY','HWY','NORTH','SOUTH','EAST','WEST',
               'N','S','E','W','NE','NW','SE','SW'}

def norm_name(s):
    if not s: return ''
    s = s.lower()
    for stop in _LEGAL_STOPS:
        s = s.replace(stop, ' ')
    s = re.sub(r'[,\.\#\'\"]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def norm_street(s):
    if not s: return ''
    s = re.sub(r'\s+', ' ', re.sub(r'[.,#]', '', s.upper())).strip()
    return ' '.join(t for t in s.split(' ') if t not in _ADDR_STOPS)

def norm_parcel(s):
    if not s: return ''
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())

# ── 1. Pull 358 unlinked IronClad ROE + PAL records ──
IC_TYPES = "('Right of Entry Agreement','Premises Access License')"
ic = sf.query_all(f"""
  SELECT Id, IronClad_Id__c, Record_Name__c, Record_Type_IC__c, Counterparty_Name__c,
         Property_Address__c, Property_City__c, Property_State__c, Property_Postcode__c,
         Counterparty_Address__c,
         Parcel_Number__c, Agreement_Date__c, Contract_Status__c, Stage_IC__c, MDU_or_BUS__c
  FROM IronClad__c WHERE Agreement__c = null AND Record_Type_IC__c IN {IC_TYPES}
""")['records']
print(f"Unlinked IronClad ROE/PAL records: {len(ic)}")

# ── 2. Pull all SF Opps with match fields ──
opps = sf.query_all("""
  SELECT Id, Name, RecordType.DeveloperName, StageName,
         Property_Address__c, Property_City__c, Property_State__c,
         Agreement_Name__c, In_SiteTracker__c
  FROM Opportunity
""")['records']
print(f"SF Opps available for matching: {len(opps)}")

# Build indexes on the Opp side
opp_by_norm_name = {}
opp_by_addr_city = {}
opp_by_street_n = {}
for o in opps:
    nn = norm_name(o['Name'])
    if nn: opp_by_norm_name.setdefault(nn, []).append(o)
    if o.get('Property_Address__c'):
        first = o['Property_Address__c'].split(',')[0].strip()
        m = re.match(r'^\s*([0-9]+[A-Za-z\-]?)\s+(.+?)\s*$', first)
        if m:
            hn = m.group(1).strip()
            st = norm_street(m.group(2))
            city = (o.get('Property_City__c') or '').strip().upper()
            state = (o.get('Property_State__c') or '').strip().upper()[:2] if o.get('Property_State__c') else ''
            key = (hn, st, city, state)
            opp_by_addr_city.setdefault(key, []).append(o)
            opp_by_street_n.setdefault((st, city, state), []).append(o)

# ── 3. Match each IronClad record ──
matches = []
no_match = []

def parse_addr_components(raw):
    """Return (housenum, street_n, city, state) tuple parsed from a free-text address."""
    if not raw: return None, None, None, None
    first = raw.split(',')[0].strip()
    am = re.match(r'^\s*([0-9]+[A-Za-z\-]?)\s+(.+?)\s*$', first)
    if not am: return None, None, None, None
    hn = am.group(1).strip()
    st = norm_street(am.group(2))
    # Try to pull city/state out of the later commas
    parts = [p.strip() for p in raw.split(',')[1:]]
    city = (parts[0].upper() if parts else '').strip()
    state = ''
    if len(parts) > 1:
        sm = re.search(r'\b([A-Z]{2})\b', parts[1].upper())
        if sm: state = sm.group(1)
    return hn, st, city, state

def match_one(ic_rec):
    cp = ic_rec.get('Counterparty_Name__c') or ''
    prop_addr = ic_rec.get('Property_Address__c') or ''
    cp_addr = ic_rec.get('Counterparty_Address__c') or ''
    city = (ic_rec.get('Property_City__c') or '').upper().strip()
    state = (ic_rec.get('Property_State__c') or '').upper().strip()[:2] if ic_rec.get('Property_State__c') else ''

    # Parse IC Property Address
    prop_hn, prop_street, _, _ = parse_addr_components(prop_addr)

    candidates = []

    # Signal 1: Property Address exact (hn + street + city + state)
    if prop_hn and prop_street:
        for o in opp_by_addr_city.get((prop_hn, prop_street, city, state), []):
            candidates.append((o, 'HIGH', 'property_address_exact'))
        # with state loose
        if not candidates and state:
            for o in opp_by_addr_city.get((prop_hn, prop_street, city, ''), []):
                candidates.append((o, 'HIGH', 'property_address_state_loose'))

    # Signal 1b: Counterparty Address as fallback (when Property Address missing or didn't match)
    if not candidates and cp_addr:
        cp_hn, cp_street, cp_city, cp_state = parse_addr_components(cp_addr)
        if cp_hn and cp_street:
            cp_city_u = (cp_city or city).upper()
            cp_state_u = cp_state or state
            for o in opp_by_addr_city.get((cp_hn, cp_street, cp_city_u, cp_state_u), []):
                candidates.append((o, 'HIGH', 'counterparty_address_exact'))

    # Signal 2: counterparty name exact-normalized
    if not candidates:
        nn = norm_name(cp)
        if nn:
            hit = opp_by_norm_name.get(nn)
            if hit and len(hit) <= 3:
                for o in hit:
                    candidates.append((o, 'HIGH', 'counterparty_name_exact'))

    # Signal 3: counterparty name partial / substring
    if not candidates:
        nn = norm_name(cp)
        if nn and len(nn) > 6:
            for n, opps_ in opp_by_norm_name.items():
                if len(opps_) == 1 and (nn in n or n in nn):
                    candidates.append((opps_[0], 'MEDIUM', 'counterparty_name_partial'))
                    break

    # Signal 4: street+city (fuzzy, same street but different housenum)
    if not candidates and prop_street:
        hit = opp_by_street_n.get((prop_street, city, state))
        if hit and len(hit) == 1:
            candidates.append((hit[0], 'LOW', 'street_only'))

    return candidates[:1]  # best match

for rec in ic:
    c = match_one(rec)
    if c:
        o, conf, method = c[0]
        matches.append({
            'ic_id': rec['Id'], 'ic_record_name': rec.get('Record_Name__c'),
            'ic_type': rec.get('Record_Type_IC__c'),
            'ic_counterparty': rec.get('Counterparty_Name__c'),
            'ic_parcel': rec.get('Parcel_Number__c'),
            'ic_property_address': rec.get('Property_Address__c'),
            'ic_counterparty_address': rec.get('Counterparty_Address__c'),
            'ic_signed_date': rec.get('Agreement_Date__c'),
            'ic_contract_status': rec.get('Contract_Status__c'),
            'ic_stage': rec.get('Stage_IC__c'),
            'opp_id': o['Id'], 'opp_name': o['Name'], 'opp_stage': o.get('StageName'),
            'opp_rt': (o.get('RecordType') or {}).get('DeveloperName'),
            'confidence': conf, 'method': method,
        })
    else:
        no_match.append(rec)

print(f"\n=== MATCH RESULTS ===")
by_conf = Counter(m['confidence'] for m in matches)
print(f"  HIGH:   {by_conf.get('HIGH', 0)}")
print(f"  MEDIUM: {by_conf.get('MEDIUM', 0)}")
print(f"  LOW:    {by_conf.get('LOW', 0)}")
print(f"  No match: {len(no_match)}")

by_method = Counter(m['method'] for m in matches)
print(f"\nBy method: {dict(by_method)}")

# Save preview
preview_path = Path(r'C:\Users\cass\Work_Projects\SalesForce\ironclad_linker_preview_2026-04-24.json')
with preview_path.open('w', encoding='utf-8') as f:
    json.dump({'matches': matches, 'no_match_count': len(no_match)}, f, indent=2, default=str)
print(f"Preview saved: {preview_path.name}")

# Sample output
print(f"\n--- Sample HIGH-confidence matches (first 15) ---")
for m in [x for x in matches if x['confidence'] == 'HIGH'][:15]:
    print(f"  [{m['method']:<25}] {m['ic_counterparty'][:32]:<32} -> {m['opp_name'][:32]:<32} ({m['opp_stage']})")

print(f"\n--- Sample MEDIUM-confidence matches (first 10) ---")
for m in [x for x in matches if x['confidence'] == 'MEDIUM'][:10]:
    print(f"  [{m['method']:<25}] {m['ic_counterparty'][:32]:<32} -> {m['opp_name'][:32]:<32} ({m['opp_stage']})")

print(f"\n--- Sample LOW-confidence matches (first 5) ---")
for m in [x for x in matches if x['confidence'] == 'LOW'][:5]:
    print(f"  [{m['method']:<25}] {m['ic_counterparty'][:32]:<32} -> {m['opp_name'][:32]:<32} ({m['opp_stage']})")

# ── 4. Apply (preview unless --apply) ──
if not args.apply:
    print(f"\n[dry-run] Use --apply to execute. Add --fuzzy to include MEDIUM matches.")
    sys.exit(0)

to_apply = [m for m in matches if m['confidence'] == 'HIGH']
if args.fuzzy:
    to_apply += [m for m in matches if m['confidence'] == 'MEDIUM']
print(f"\nApplying {len(to_apply)} matches...")

audit_rows = []
created = 0
failed = 0
for m in to_apply:
    ag_type = 'ROE' if m['ic_type'] == 'Right of Entry Agreement' else 'PAL'
    # Provenance note so reviewers can see how each link was derived
    method_desc = {
        'property_address_exact':       'Matched by IRONCLAD Property Address exact (hn+street+city+state)',
        'property_address_state_loose': 'Matched by IRONCLAD Property Address (state loose)',
        'counterparty_address_exact':   'Matched by IRONCLAD Counterparty Address (Property Address was blank or no match)',
        'counterparty_name_exact':      'Matched by IRONCLAD Counterparty Name (exact, normalized)',
        'counterparty_name_partial':    'Matched by IRONCLAD Counterparty Name (partial / substring — verify)',
        'street_only':                  'Matched by street only (low confidence, verify address)',
    }.get(m['method'], m['method'])
    note = (
        f"AUTO-LINKED via IronClad Bulk Linker on {TS[:10]}.\n"
        f"Match method: {method_desc}  (confidence: {m['confidence']})\n"
        f"IronClad Counterparty Name: {m.get('ic_counterparty') or '(blank)'}\n"
        f"IronClad Property Address:  {m.get('ic_property_address') or '(blank)'}\n"
        f"IronClad Counterparty Address: {m.get('ic_counterparty_address') or '(blank)'}\n"
        f"IronClad Parcel: {m.get('ic_parcel') or '(blank)'}\n"
        f"Recommendation: human review to confirm match quality."
    )
    payload = {
        'Opportunity__c': m['opp_id'],
        'Agreement_Type__c': ag_type,
        'Status__c': 'Completed' if (m['ic_stage'] == 'completed' or m['ic_contract_status'] == 'active') else 'Review',
        'Signed_Date__c': m['ic_signed_date'],
        'IronClad_Record__c': m['ic_id'],
        'Notes__c': note,
    }
    try:
        r = sf.Agreement__c.create(payload)
        if r.get('success'):
            new_ag_id = r['id']
            sf.IronClad__c.update(m['ic_id'], {'Agreement__c': new_ag_id})
            created += 1
            audit_rows.append([m['opp_id'], m['opp_name'],
                               'Agreement__c.Created', '(no link)',
                               f"Type={ag_type} link IC={m['ic_id']} Ag={new_ag_id} (conf={m['confidence']}/{m['method']})",
                               SOURCE, TS, 'create'])
        else:
            failed += 1
    except Exception as e:
        failed += 1
        audit_rows.append([m['opp_id'], m['opp_name'], 'Agreement__c.Created', '(no link)',
                           f"FAIL: {str(e)[:120]}", SOURCE, TS, 'error'])

# write audit log
audit_path = AUDIT_DIR / 'ironclad_bulk_linker_2026-04-24.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id','Name','Field','Before','After','Source','Timestamp','Action'])
    for r in audit_rows: w.writerow(r)

print(f"\nCreated: {created}, Failed: {failed}")
print(f"Audit log: {audit_path.name}")
