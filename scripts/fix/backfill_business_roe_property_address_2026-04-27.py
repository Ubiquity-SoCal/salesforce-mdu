"""
Backfill Property_Address__c on the 245 Business_ROE Opps.

Saturday's backfill set City/State/Zip but skipped Property_Address__c. The IronClad
bulk linker matches on hn+street+city+state, so without an address, no Business_ROE
Opp can be matched to its IronClad record.

Strategy: derive Property_Address__c from the Opp Name. Names look like
"ROE - 1930 S ALMA SCHOOL RD MESA AZ". Strip the "ROE - " prefix and the trailing
"{Property_City__c} {Property_State__c}" segment. Whatever remains is the street.

Usage:
  python backfill_business_roe_property_address_2026-04-27.py            # preview
  python backfill_business_roe_property_address_2026-04-27.py --apply    # writes
"""
import sys, io, re, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()
APPLY = args.apply

SCRIPT_NAME = 'backfill_business_roe_property_address_2026-04-27.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

opps = sf.query_all("""
  SELECT Id, Name, Property_Address__c, Property_City__c, Property_State__c
  FROM Opportunity
  WHERE RecordType.DeveloperName='Business_ROE'
""")['records']
print(f"Pulled {len(opps)} Business_ROE Opps")

STREET_SUFFIXES = {
    'RD','ROAD','ST','STREET','AVE','AVENUE','BLVD','BOULEVARD','DR','DRIVE',
    'LN','LANE','CT','COURT','CIR','CIRCLE','PL','PLACE','PKWY','PARKWAY',
    'TRL','TRAIL','TER','TERRACE','HWY','HIGHWAY','WAY','PLZ','PLAZA',
    'ALY','ALLEY','SQ','SQUARE','HTS','HEIGHTS','ROW','RTE','ROUTE',
    'EXPY','EXPRESSWAY','FWY','FREEWAY','LOOP','RUN','PATH','XING',
    'CV','COVE','BND','BEND','PASS','RDG','RIDGE',
    # Texas-specific route prefixes that work as suffixes here ("S FM 51 DECATUR")
    'FM','RM','CR','SH','SR',
}

def derive_street(name, state):
    """Derive (street, city) from an Opp Name like 'ROE - 1930 S ALMA SCHOOL RD MESA AZ'."""
    if not name:
        return None, None
    s = re.sub(r'^\s*ROE\s*-\s*', '', name).strip()
    if state:
        s = re.sub(r'\s+' + re.escape(state) + r'\s*$', '', s).strip()
    tokens = s.split()
    if not tokens:
        return None, None
    # Walk backwards for last street-suffix token
    last_suffix_idx = None
    for i in range(len(tokens) - 1, -1, -1):
        t = tokens[i].upper().rstrip('.,')
        if t in STREET_SUFFIXES:
            last_suffix_idx = i
            break
    if last_suffix_idx is None:
        return s, None
    # After the suffix, keep tokens that are numeric or single-letter (route numbers, unit letters)
    # Stop at the first multi-letter alphabetic token (likely the city name)
    end_idx = last_suffix_idx
    for j in range(last_suffix_idx + 1, len(tokens)):
        t = tokens[j].rstrip('.,')
        if re.fullmatch(r'\d+|[A-Za-z]|\d+[A-Za-z]+|[A-Za-z]\d+', t):
            end_idx = j
        else:
            break
    street = ' '.join(tokens[:end_idx + 1])
    city = ' '.join(tokens[end_idx + 1:]) if end_idx + 1 < len(tokens) else None
    if not re.match(r'^\d', street):
        return None, city
    street = re.sub(r'\s+', ' ', street).strip()
    return street, city


planned = []
already_filled = 0
no_derive = 0
for o in opps:
    if o.get('Property_Address__c'):
        already_filled += 1
        continue
    name = o['Name'] or ''
    city = (o.get('Property_City__c') or '').strip()
    state = (o.get('Property_State__c') or '').strip()
    derived_street, derived_city = derive_street(name, state)
    if not derived_street:
        no_derive += 1
        continue
    # Mark city update if derived_city is more specific than opp_city.
    # We treat opp_city='DFW' or empty as definitionally less specific than any derived city.
    fix_city = False
    if derived_city:
        if not city or city.upper() == 'DFW' or city.upper() != derived_city.upper():
            # Only fix when the derived city looks like a real specific city (not a generic 'CITY OF...')
            # Heuristic: at least 3 chars, mostly alphabetic
            d_alpha = re.sub(r'[^A-Za-z]', '', derived_city)
            if len(d_alpha) >= 3:
                fix_city = (city.upper() == 'DFW' or not city)
    planned.append({
        'Id': o['Id'],
        'Name': name,
        'derived': derived_street,
        'derived_city': derived_city,
        'opp_city': city,
        'opp_state': state,
        'fix_city': fix_city,
    })

print(f"  Already filled: {already_filled}")
print(f"  Could not derive: {no_derive}")
print(f"  Planned updates: {len(planned)}")

print("\nFirst 10 derivations:")
for p in planned[:10]:
    flag = '  <-- city mismatch?' if (p['derived_city'] and p['opp_city'] and p['derived_city'].upper() != p['opp_city'].upper()) else ''
    print(f"  {p['Name'][:55]:55s} -> {p['derived']!s:45s}{flag}")

# Look for any obvious oddballs
mismatch = [p for p in planned if p['derived_city'] and p['opp_city']
            and p['derived_city'].upper() != p['opp_city'].upper()]
if mismatch:
    print(f"\n  {len(mismatch)} rows where derived city != Opp Property_City__c:")
    for m in mismatch[:10]:
        will_fix = '  [WILL FIX]' if m['fix_city'] else ''
        print(f"    {m['Name'][:55]:55s} derived={m['derived_city']!r:25s} vs Opp={m['opp_city']!r:20s}{will_fix}")

city_fixes = sum(1 for p in planned if p['fix_city'])
print(f"\n  Property_City__c fixes planned (DFW/blank -> specific): {city_fixes}")

if not APPLY:
    print(f"\n[Preview only — re-run with --apply to update {len(planned)} Opps]")
    sys.exit(0)

print("\nApplying...")
audit_rows = []
batch = []
for p in planned:
    rec = {'Id': p['Id'], 'Property_Address__c': p['derived']}
    if p['fix_city']:
        rec['Property_City__c'] = p['derived_city'].upper()
    batch.append(rec)

for i in range(0, len(batch), 200):
    chunk = batch[i:i+200]
    plan_chunk = planned[i:i+200]
    print(f"  Batch {i//200 + 1}: {len(chunk)}")
    results = sf.bulk.Opportunity.update(chunk)
    for j, res in enumerate(results):
        p = plan_chunk[j]
        if res.get('success'):
            audit_rows.append({
                'SF_Id': p['Id'], 'Name': p['Name'],
                'Field': 'Property_Address__c',
                'Before': '(null)', 'After': p['derived'],
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'FILL',
                'Note': f'Derived from Opp Name; opp_city={p["opp_city"]} state={p["opp_state"]}',
            })
            if p['fix_city']:
                audit_rows.append({
                    'SF_Id': p['Id'], 'Name': p['Name'],
                    'Field': 'Property_City__c',
                    'Before': p['opp_city'] or '(null)',
                    'After': p['derived_city'].upper(),
                    'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'OVERWRITE',
                    'Note': f'DFW/blank -> specific city derived from Opp Name',
                })
        else:
            print(f"    ⚠ FAIL: {p['Name']} — {res.get('errors', res)}")

audit_path = AUDIT_DIR / f'business_roe_property_address_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\n✓ Done. Audit log: {audit_path} ({len(audit_rows)} rows)")
