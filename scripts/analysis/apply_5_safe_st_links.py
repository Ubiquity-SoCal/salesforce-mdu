"""
Targeted: apply only the 5 hand-verified safe ST -> Opp links.
Looks up IDs at runtime to avoid stale references.
Writes audit CSV before any update.
"""
import sys
import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

# (ST project number, expected Opp Name)
SAFE_PAIRS = [
    ('P-006320', 'Omaha_MDU_4704 Cass St'),
    ('P-005517', 'Omaha_MDU_4402 N 60th Ave'),
    ('P-004454', 'Sandpiper Pointe'),
    ('P-004726', 'Del Mar Downs Condos'),
    ('P-006898', 'Woodglen Square ll'),
]

OUT_DIR = Path('C:/Users/cass/Work_Projects/SalesForce/audit_logs')
OUT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = OUT_DIR / f'st_links_5safe_{TS}.csv'

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

rows = []
for st_num, opp_name in SAFE_PAIRS:
    # Lookup ST project (must currently be unlinked)
    st_q = sf.query(f"""
        SELECT Id, Name, Site_Name__c, Opportunity__c
        FROM SiteTracker_Project__c
        WHERE Name = '{st_num}'
    """)
    if not st_q['records']:
        print(f"[SKIP] {st_num} not found")
        rows.append({'st_num': st_num, 'opp_name': opp_name, 'action': 'SKIP_NOT_FOUND'})
        continue
    st = st_q['records'][0]
    if st.get('Opportunity__c'):
        print(f"[SKIP] {st_num} already linked to {st['Opportunity__c']}")
        rows.append({'st_num': st_num, 'opp_name': opp_name, 'action': 'SKIP_ALREADY_LINKED'})
        continue

    # Lookup Opp by exact Name
    safe_name = opp_name.replace("'", "\\'")
    opp_q = sf.query(f"""
        SELECT Id, Name, StageName
        FROM Opportunity
        WHERE Name = '{safe_name}'
    """)
    if not opp_q['records']:
        print(f"[SKIP] Opp '{opp_name}' not found")
        rows.append({'st_num': st_num, 'opp_name': opp_name, 'action': 'SKIP_OPP_NOT_FOUND'})
        continue
    if len(opp_q['records']) > 1:
        print(f"[SKIP] Opp '{opp_name}' is ambiguous ({len(opp_q['records'])} matches)")
        rows.append({'st_num': st_num, 'opp_name': opp_name, 'action': 'SKIP_AMBIGUOUS'})
        continue
    opp = opp_q['records'][0]

    # Apply both sides of the link
    try:
        sf.SiteTracker_Project__c.update(st['Id'], {'Opportunity__c': opp['Id']})
        sf.Opportunity.update(opp['Id'], {'SiteTracker_Project_ID__c': st_num})
        print(f"[LINKED] {st_num} -> {opp_name} [{opp['StageName']}]")
        rows.append({
            'st_num': st_num, 'opp_name': opp_name,
            'st_id': st['Id'], 'opp_id': opp['Id'], 'stage': opp['StageName'],
            'action': 'LINKED'
        })
    except Exception as e:
        print(f"[ERROR] {st_num} -> {opp_name}: {e}")
        rows.append({'st_num': st_num, 'opp_name': opp_name, 'action': f'ERROR: {e}'})

# Write audit
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    keys = sorted({k for r in rows for k in r.keys()})
    w = csv.DictWriter(f, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
print(f"\n[INFO] Audit log: {OUT}")
print(f"[SUMMARY] Linked: {sum(1 for r in rows if r['action'] == 'LINKED')}/{len(rows)}")
