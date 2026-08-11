"""
Vetro-driven Property_Category classifier.

For each SF Opp with null or Cat 3 Property_Category, look up its address in
Vetro (via the unified snapshot) and classify:
  Cat 1  — address serviceable AND on an activated FDH (fiber live today)
  Cat 2  — address in Vetro but not serviceable OR FDH not activated (fiber planned)
  ?      — address not in Vetro (stays as-is; we do NOT assume Cat 3)

Vetro only covers TX / NE / AZ / CA today. Opps outside those states are skipped.

Reads from Vetro/data/snapshot/vetro-unified.parquet, NOT vetro_fiber_jack_table
(which undercounts SFU service_locations by ~70%). See
Vetro/docs/vetro-snapshot-schema.md.

PREVIEW ONLY by default. Pass --apply to execute the Property_Category updates.
"""
import sys, io, re, argparse, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import Counter, defaultdict
from simple_salesforce import Salesforce

sys.path.insert(0, r'C:\Users\cass\Work_Projects\Vetro\scripts\lib')
from load_vetro import load_vetro, service_locations

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true', help='Apply Property_Category updates to SF')
args = parser.parse_args()

# ── Address normalization (matches the Databricks NORM regex in vetro_reconciliation) ──
_STOP = {'STREET','ST','AVENUE','AVE','ROAD','RD','DRIVE','DR','BOULEVARD','BLVD','LANE','LN',
         'COURT','CT','CIRCLE','CIR','PLACE','PL','PARKWAY','PKWY','TRAIL','TRL','TERRACE','TER',
         'HIGHWAY','HWY','NORTH','SOUTH','EAST','WEST','N','S','E','W','NE','NW','SE','SW'}
_STATE_FULL_TO_ABBR = {'texas':'TX','california':'CA','arizona':'AZ','nebraska':'NE'}
FOOTPRINT = {'TX','NE','AZ','CA'}

def norm_street(s):
    if not s: return ''
    s = s.upper()
    s = re.sub(r'[.,#]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    toks = [t for t in s.split(' ') if t not in _STOP]
    return ' '.join(toks)

def parse_address(addr):
    """Return (housenum, street_n) from a free-text address like '1522 East Southern Avenue, Tempe, AZ, USA'."""
    if not addr: return None, None
    # strip after first comma (city/state/zip/country)
    first = addr.split(',')[0].strip()
    m = re.match(r'^\s*([0-9]+[A-Za-z\-]?)\s+(.+?)\s*$', first)
    if not m: return None, None
    return m.group(1).strip(), norm_street(m.group(2))

def norm_zip(z):
    if not z: return ''
    s = re.sub(r'[^0-9]', '', str(z))
    return s[:5]

def norm_state(s):
    if not s: return ''
    s = str(s).strip()
    if len(s) == 2: return s.upper()
    return _STATE_FULL_TO_ABBR.get(s.lower(), s.upper())


# ── 1. Build Vetro address index from snapshot ────────────────────────────
print("Loading Vetro snapshot...")
vdf = service_locations(load_vetro())
vdf = vdf[vdf.state.isin(FOOTPRINT) & vdf.housenum.notna() & vdf.streetname.notna()]
print(f"Vetro snapshot rows in footprint: {len(vdf):,}")

# Aggregate per (state, housenum, street_n, zip5) -- same grain as the old SQL.
# Use the local norm_street / norm_zip helpers already defined above so the
# index keys match the SF-side classifier keys exactly.
agg = defaultdict(lambda: {'has_serviceable': 0, 'has_drop_built': 0,
                           'has_active_customer': 0, 'drops': 0})
DROP_BUILT_STATES = {'Active customer', 'Drop completed'}
for r in vdf.to_dict(orient='records'):
    state = (r.get('state') or '').strip()
    hn    = (r.get('housenum') or '').strip()
    sn    = norm_street(r.get('streetname'))
    z     = norm_zip(r.get('zipcode'))
    key = (state, hn, sn, z)
    a = agg[key]
    if r.get('addrstatus') == 'serviceable':
        a['has_serviceable'] = 1
    insvc = r.get('ckta_insvc')
    if insvc in DROP_BUILT_STATES:
        a['has_drop_built'] = 1
    if insvc == 'Active customer':
        a['has_active_customer'] = 1
    a['drops'] += 1
vetro_idx = dict(agg)

# Also index without zip for fallback matching
vetro_no_zip = {}
for (state, hn, sn, zip5), v in vetro_idx.items():
    k = (state, hn, sn)
    if k not in vetro_no_zip:
        vetro_no_zip[k] = dict(v)
    else:
        m = vetro_no_zip[k]
        m['has_serviceable']     = max(m['has_serviceable'],     v['has_serviceable'])
        m['has_drop_built']      = max(m['has_drop_built'],      v['has_drop_built'])
        m['has_active_customer'] = max(m['has_active_customer'], v['has_active_customer'])

print(f"Vetro address universe: {len(vetro_idx):,} addresses (with zip)")

# ── 2. Pull candidate SF Opps ──────────────────────────────────────────────
sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
opps = sf.query_all("""
  SELECT Id, Name, Property_Address__c, Property_City__c, Property_State__c, Property_Zip__c,
         Property_Category__c, Franchise_Type__c
  FROM Opportunity
  WHERE (Property_Category__c NOT IN ('Cat 1','Cat 2') OR Property_Category__c = null)
    AND Property_Address__c != null
    AND Property_State__c != null
""")['records']
print(f"SF candidate Opps (null/Cat3 with address): {len(opps):,}")

# ── 3. Match + classify ────────────────────────────────────────────────────
cat1_updates = []   # Vetro: serviceable + FDH activated
cat2_updates = []   # Vetro: in Vetro but not serviceable/activated
no_match = []       # Not in Vetro or not in footprint states
skipped_state = 0
skipped_parse = 0
match_zip_used = 0
match_zip_fallback = 0

for o in opps:
    state = norm_state(o.get('Property_State__c'))
    if state not in FOOTPRINT:
        skipped_state += 1
        continue
    hn, sn = parse_address(o.get('Property_Address__c'))
    if not hn or not sn:
        skipped_parse += 1
        continue
    z = norm_zip(o.get('Property_Zip__c'))

    key = (state, hn, sn, z)
    hit = vetro_idx.get(key)
    if hit:
        match_zip_used += 1
    else:
        hit = vetro_no_zip.get((state, hn, sn))
        if hit:
            match_zip_fallback += 1

    if not hit:
        no_match.append(o)
        continue
    # Cat 1 = drop physically built to the address (Active customer or Drop completed)
    if hit['has_drop_built']:
        cat1_updates.append({'Id': o['Id'], 'Name': o['Name'], 'current': o.get('Property_Category__c'),
                             'address': o.get('Property_Address__c'), 'franchise': o.get('Franchise_Type__c'),
                             'active_customer': hit['has_active_customer']})
    else:
        cat2_updates.append({'Id': o['Id'], 'Name': o['Name'], 'current': o.get('Property_Category__c'),
                             'address': o.get('Property_Address__c'), 'franchise': o.get('Franchise_Type__c'),
                             'serviceable': hit['has_serviceable']})

# ── 4. Preview ─────────────────────────────────────────────────────────────
print(f"\n═══ PREVIEW ═══")
print(f"  Cat 1 (On Net, serviceable + activated):   {len(cat1_updates)}")
print(f"  Cat 2 (in Vetro, not yet serviceable):     {len(cat2_updates)}")
print(f"  No match in Vetro (stays null/Cat 3):      {len(no_match)}")
print(f"  Skipped (state outside TX/NE/AZ/CA):       {skipped_state}")
print(f"  Skipped (couldn't parse address):          {skipped_parse}")
print(f"\n  Match details: zip-exact {match_zip_used}, zip-fallback {match_zip_fallback}")

print(f"\n--- Sample Cat 1 (first 15) ---")
for u in cat1_updates[:15]:
    ac = 'live' if u['active_customer'] else 'built, no customer yet'
    print(f"  {u['current'] or 'null':<6} -> Cat 1 [{ac:<22}] {u['Name'][:35]:<35}  {u['address'][:55]}")
print(f"\n--- Sample Cat 2 (first 15) ---")
for u in cat2_updates[:15]:
    print(f"  {u['current'] or 'null':<6} -> Cat 2  {u['Name'][:35]:<35}  serviceable={u['serviceable']}  {u['address'][:55]}")

# breakdown by franchise
print(f"\n--- Proposed changes by Franchise_Type ---")
from collections import Counter

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

cat1_f = Counter(u.get('franchise') for u in cat1_updates)
cat2_f = Counter(u.get('franchise') for u in cat2_updates)
print(f"  Cat 1 by franchise: {dict(cat1_f)}")
print(f"  Cat 2 by franchise: {dict(cat2_f)}")

# Save preview
with open(r'C:\Users\cass\Work_Projects\SalesForce\vetro_classifier_preview.json','w') as f:
    json.dump({'cat1': cat1_updates, 'cat2': cat2_updates,
               'no_match_count': len(no_match), 'skipped_state': skipped_state,
               'skipped_parse': skipped_parse}, f, indent=2, default=str)
print(f"\nPreview saved to vetro_classifier_preview.json")

# ── 5. Apply (only with --apply flag) ──────────────────────────────────────
if not args.apply:
    print("\n[dry-run] Rerun with --apply to execute SF updates.")
    sys.exit(0)

updates = [{'Id': u['Id'], 'Property_Category__c': 'Cat 1'} for u in cat1_updates]
updates += [{'Id': u['Id'], 'Property_Category__c': 'Cat 2'} for u in cat2_updates]
print(f"\nApplying {len(updates)} updates...")
results = sf.bulk.Opportunity.update(updates, batch_size=200)
succ = sum(1 for r in results if r.get('success'))
print(f"Succeeded: {succ}, Failed: {len(results)-succ}")
