"""More diag: when were these Opps' Agreements created? Why the 5/5 mass move?"""
from simple_salesforce import Salesforce
from collections import Counter

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

# Sample 3 Opps and look at their Agreement records' CreatedDate
print('== Agreement CreatedDate distribution on a few Opps ==')
for nm in ['Baldwin Manor', 'Purgatory Creek Townhomes', 'Stonebridge Gardens',
          'Villas on Horne', 'Bali Apartments']:
    rs = sf.query(f"""
        SELECT Id, Name, Agreement_Type__c, Status__c, CreatedDate, LastModifiedDate
        FROM Agreement__c
        WHERE Opportunity__r.Name = '{nm}'
        ORDER BY Agreement_Type__c
    """)['records']
    print(f'\n  {nm}:')
    for a in rs:
        print(f"    {a['Agreement_Type__c']:8s} {a['Name']:8s} {a['Status__c']:12s} created={a['CreatedDate'][:10]} mod={a['LastModifiedDate'][:10]}")

# Pull all 97 Opps, see who LastModifiedById on 5/5 was
print('\n== Who modified the 97 Opps on 5/5? ==')
import json, os

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

with open(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\2026-05-07_taylor_ema_bulk_cleanup\phase1_resolved_targets.json') as f:
    j = json.load(f)
opp_ids = list({a['Opportunity__c'] for a in j['agreements_to_delete']})
ids_str = "','".join(opp_ids)
rs = sf.query_all(f"""
    SELECT Id, Name, StageName, LastModifiedDate, LastModifiedBy.Name
    FROM Opportunity WHERE Id IN ('{ids_str}')
""")['records']

mod_counter = Counter()
ts_counter = Counter()
for o in rs:
    mod_counter[o['LastModifiedBy']['Name']] += 1
    ts_counter[o['LastModifiedDate'][:16]] += 1

print(f'  Total Opps in scope: {len(rs)}')
print('  Last modified by:')
for u, c in mod_counter.most_common():
    print(f'    {u}: {c}')
print('  Last modified at (YYYY-MM-DDTHH:MM):')
for ts, c in ts_counter.most_common(10):
    print(f'    {ts}: {c}')

# also: Check stage breakdown
stage_counter = Counter(o['StageName'] for o in rs)
print('  Current SF stage:')
for s, c in stage_counter.most_common():
    print(f'    {s}: {c}')
