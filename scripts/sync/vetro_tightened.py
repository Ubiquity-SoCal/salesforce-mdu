"""Tightened Vetro classifier — dry-run comparison vs previously applied."""
import sys, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import Counter
from simple_salesforce import Salesforce
from databricks import sql

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
st = Salesforce(username='cass@ubiquitygp.com', password='Hawaiian84', security_token='fe2pen6ceQeqGhWXhBeOIjqP', domain='login')

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

# 2) Vetro — STRICT: serviceable-only; preserve FB vs FDH distinction
with sql.connect(server_hostname="adb-1444374860642533.13.azuredatabricks.net",
                 http_path="/sql/1.0/warehouses/9116e9c573d36d1c",
                 auth_type="databricks-oauth") as conn:
    with conn.cursor() as cur:
        cur.execute(r"""
          SELECT trim(upper(`properties.state`)), trim(upper(`properties.city`)),
                 trim(`properties.housenum`),
                 regexp_replace(regexp_replace(regexp_replace(trim(upper(`properties.streetname`)),
                   '[.,#]',''),'\s+',' '),
                   '\b(STREET|ST|AVENUE|AVE|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|LANE|LN|COURT|CT|CIRCLE|CIR|PLACE|PL|PARKWAY|PKWY|TRAIL|TRL|TERRACE|TER|HIGHWAY|HWY|NORTH|SOUTH|EAST|WEST|N|S|E|W|NE|NW|SE|SW)\b',''),
                 substr(regexp_replace(`properties.zipcode`, '[^0-9]', ''), 1, 5),
                 `properties.servarea`, `properties.fdh`
          FROM hive_metastore.default.vetro_fiber_jack_table
          WHERE `properties.housenum` IS NOT NULL AND `properties.streetname` IS NOT NULL
            AND trim(`properties.state`) IN ('TX','NE','AZ','CA')
            AND `properties.addrstatus` = 'serviceable'
        """)
        rows = cur.fetchall()

vetro_idx = {}
for row in rows:
    state, city, hn, sn, z, servarea, fdh = row
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
