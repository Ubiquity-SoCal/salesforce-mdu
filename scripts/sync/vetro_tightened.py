"""Tightened Vetro classifier — dry-run comparison vs previously applied.

Vetro side now reads the unified Vetro snapshot
(Vetro/data/snapshot/vetro-unified.parquet) instead of the broken
vetro_fiber_jack_table which undercounted SFU service_locations by ~70%.
See Vetro/docs/vetro-snapshot-schema.md.
"""
import sys, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import Counter
from pathlib import Path
from simple_salesforce import Salesforce

sys.path.insert(0, r'C:\Users\cass\Work_Projects\Vetro\scripts\lib')
from load_vetro import load_vetro, service_locations, serviceable

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_ST = _sf_creds("st")

_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
st = Salesforce(username=_ST["username"], password=_ST["password"], security_token=_ST["token"], domain='login')

# 1) Activated FDH lookup from Lit_Fiber — exact (state, city, SA, FDH##)
r = st.query_all("SELECT Project__r.sitetracker__Site__r.Name, FDH_Activation_A__c FROM Lit_Fiber__c")
pat = re.compile(r'^([A-Z]{2})_([A-Z_]+)_SA(\d+)_FDH(\d+)', re.IGNORECASE)
activ = {}
for o in r['records']:
    site = ((o.get('Project__r') or {}).get('sitetracker__Site__r') or {}).get('Name') or ''
    m = pat.match(site)
    if not m: continue
    key = (m.group(1).upper(), m.group(2).upper().replace('_',' '),
           f"SA{m.group(3).zfill(2)}", f"FDH{m.group(4).zfill(2)}")
    if o.get('FDH_Activation_A__c'):
        activ[key] = o['FDH_Activation_A__c']
print(f"Activated FDH keys: {len(activ)}")

# 2) Vetro — STRICT: serviceable-only service_location rows from the snapshot.
#    Apply the same hygiene the old SQL did: upper+strip housenum/street/state,
#    regex-strip suffixes, 5-digit zip. Preserve FB vs FDH distinction in fdh.
_SUFFIX_RE = re.compile(
    r'\b(STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|LANE|LN|'
    r'COURT|CT|CIRCLE|CIR|PLACE|PL|PARKWAY|PKWY|TRAIL|TRL|TERRACE|TER|'
    r'HIGHWAY|HWY|NORTH|SOUTH|EAST|WEST|N|S|E|W|NE|NW|SE|SW)\b'
)
def _norm_sn(s):
    if not s: return None
    out = re.sub(r'[.,#]', '', str(s).upper())
    out = re.sub(r'\s+', ' ', out)
    return _SUFFIX_RE.sub('', out).strip()
def _zip5(s):
    if not s: return ''
    return re.sub(r'[^0-9]', '', str(s))[:5]

vdf = serviceable(service_locations(load_vetro()))
vdf = vdf[vdf.state.isin(('TX','NE','AZ','CA'))
         & vdf.housenum.notna() & vdf.streetname.notna()]
print(f"Vetro snapshot serviceable rows in 4 states: {len(vdf):,}")

vetro_idx = {}
for r in vdf.to_dict(orient='records'):
    state = (r.get('state') or '').strip().upper()
    city  = (r.get('city')  or '').strip().upper()
    hn    = (r.get('housenum') or '').strip()
    sn    = _norm_sn(r.get('streetname'))
    z     = _zip5(r.get('zipcode'))
    servarea = r.get('servarea')
    fdh   = r.get('fdh')
    key = (state, (hn or '').strip(), (sn or '').strip(), z or '')
    fm = re.match(r'^\s*(FDH|FB)\s*(\d+)\s*$', (fdh or '').upper()) if fdh else None
    fdh_token = f"{fm.group(1)}{fm.group(2).zfill(2)}" if fm else None
    sm = re.match(r'^\s*SA\s*(\d+)\s*$', (servarea or '').upper()) if servarea else None
    sa_token = f"SA{sm.group(1).zfill(2)}" if sm else None
    rec = vetro_idx.setdefault(key, {'city': city, 'fdhs': set(), 'fbs': set(), 'sas': set()})
    if fdh_token and fdh_token.startswith('FDH'): rec['fdhs'].add(fdh_token)
    elif fdh_token and fdh_token.startswith('FB'): rec['fbs'].add(fdh_token)
    if sa_token: rec['sas'].add(sa_token)
print(f"Vetro serviceable-only address keys: {len(vetro_idx):,}")

# 3) Classify — scan ALL footprint-state opps (including ones we just set to Cat 1/Cat 2)
#    so we can verify / revert the prior apply as needed.
opps = sf.query_all("""SELECT Id, Name, Property_Address__c, Property_State__c, Property_Zip__c,
  Property_City__c, Property_Category__c, Franchise_Type__c FROM Opportunity
  WHERE Property_Address__c != null
    AND Property_State__c IN ('TX','NE','AZ','CA','Texas','Nebraska','Arizona','California')""")['records']

_STATE = {'texas':'TX','california':'CA','arizona':'AZ','nebraska':'NE'}
_STOP = {'STREET','ST','AVENUE','AVE','ROAD','RD','DRIVE','DR','BOULEVARD','BLVD','LANE','LN','COURT','CT','CIRCLE','CIR','PLACE','PL','PARKWAY','PKWY','TRAIL','TRL','TERRACE','TER','HIGHWAY','HWY','NORTH','SOUTH','EAST','WEST','N','S','E','W','NE','NW','SE','SW'}
def norm_street(s):
    if not s: return ''
    s = re.sub(r'\s+',' ', re.sub(r'[.,#]','', s.upper())).strip()
    return ' '.join(t for t in s.split(' ') if t not in _STOP)

cat1, cat2 = [], []
for o in opps:
    state = (o.get('Property_State__c') or '').strip()
    state = state.upper() if len(state) == 2 else _STATE.get(state.lower(), state.upper())
    if state not in {'TX','NE','AZ','CA'}: continue
    first = (o.get('Property_Address__c','') or '').split(',')[0].strip()
    m = re.match(r'^\s*([0-9]+[A-Za-z\-]?)\s+(.+?)\s*$', first)
    if not m: continue
    hn, sn = m.group(1).strip(), norm_street(m.group(2))
    z = re.sub(r'[^0-9]','', str(o.get('Property_Zip__c') or ''))[:5]
    hit = vetro_idx.get((state, hn, sn, z))
    if not hit: continue
    activated = False
    for f in hit['fdhs']:
        for sa in hit['sas']:
            if (state, hit['city'], sa, f) in activ:
                activated = True; break
        if activated: break
    (cat1 if activated else cat2).append(o)

print(f"\n=== TIGHTENED ===")
print(f"  Cat 1 (strict): {len(cat1)}")
print(f"  Cat 2 (strict): {len(cat2)}")

# Diff vs previously applied
with open(r'C:\Users\cass\Work_Projects\SalesForce\vetro_classifier_preview.json') as f:
    prev = json.load(f)
prev_c1, prev_c2 = set(prev['cat1_ids']), set(prev['cat2_ids'])
new_c1, new_c2 = {o['Id'] for o in cat1}, {o['Id'] for o in cat2}

to_revert_c1 = prev_c1 - new_c1 - new_c2  # out of both buckets entirely
to_revert_c2 = prev_c2 - new_c1 - new_c2
flip_c1_to_c2 = prev_c1 & new_c2
flip_c2_to_c1 = prev_c2 & new_c1

print(f"\n=== DIFF vs applied ===")
print(f"  Revert to null (was Cat 1, now out): {len(to_revert_c1)}")
print(f"  Revert to null (was Cat 2, now out): {len(to_revert_c2)}")
print(f"  Flip Cat 1 -> Cat 2: {len(flip_c1_to_c2)}")
print(f"  Flip Cat 2 -> Cat 1: {len(flip_c2_to_c1)}")

# Show reverts from Cat 1
if to_revert_c1:
    ids = ",".join(f"'{i}'" for i in to_revert_c1)
    r2 = sf.query(f"SELECT Id, Name, Property_City__c, Property_State__c FROM Opportunity WHERE Id IN ({ids})")
    print("\n  Reverting from Cat 1 (false positives):")
    for o in r2['records']:
        print(f"    {o['Name'][:40]:<40}  {o.get('Property_City__c')}, {o.get('Property_State__c')}")

if flip_c1_to_c2:
    ids = ",".join(f"'{i}'" for i in flip_c1_to_c2)
    r2 = sf.query(f"SELECT Id, Name, Property_City__c FROM Opportunity WHERE Id IN ({ids})")
    print("\n  Flip Cat 1 -> Cat 2:")
    for o in r2['records']:
        print(f"    {o['Name'][:40]:<40}  {o.get('Property_City__c')}")

print("\n=== New Cat 1 (strict) by City ===")
for (s,c), n in Counter((o.get('Property_State__c'), o.get('Property_City__c')) for o in cat1).most_common():
    print(f"  {s} / {c}: {n}")

with open(r'C:\Users\cass\Work_Projects\SalesForce\vetro_classifier_preview_v2.json','w') as f:
    json.dump({'cat1_ids': list(new_c1), 'cat2_ids': list(new_c2),
               'revert_cat1': list(to_revert_c1), 'revert_cat2': list(to_revert_c2),
               'flip_c1_to_c2': list(flip_c1_to_c2), 'flip_c2_to_c1': list(flip_c2_to_c1)}, f, indent=2)
print("\nSaved vetro_classifier_preview_v2.json")
