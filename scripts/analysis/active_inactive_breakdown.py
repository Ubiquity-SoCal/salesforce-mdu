"""
For PAL/ROE Complete + Marketing/Bulk In Progress + Marketing/Bulk Complete,
break down by Active/Inactive pursuit (Active = blank substatus, Inactive = any named substatus).
"""
import sys
from collections import Counter, defaultdict
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)
sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

STAGES = ['PAL/ROE Complete', 'Marketing/Bulk In Progress', 'Marketing/Bulk Complete']
ACTIVE_SUBSTATUSES = {None, ''}  # treated as Active = blank

soql = """
SELECT Id, StageName, Substatus__c,
       (SELECT Activation_Actual__c FROM SiteTracker_Projects__r)
FROM Opportunity
WHERE StageName IN ('PAL/ROE Complete','Marketing/Bulk In Progress','Marketing/Bulk Complete')
"""
res = sf.query(soql)
recs = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    recs.extend(res['records'])

def build_bucket(o):
    children = (o.get('SiteTracker_Projects__r') or {}).get('records') or []
    if not children: return 'noLink'
    if any(c.get('Activation_Actual__c') for c in children): return 'activated'
    return 'pre'

def is_active(sub):
    return sub in ACTIVE_SUBSTATUSES

# (stage, active_label) -> {activated, pre, noLink, total}
group_totals = defaultdict(lambda: {'activated':0, 'pre':0, 'noLink':0, 'total':0})

for r in recs:
    stage = r['StageName']
    sub = r.get('Substatus__c')
    label = 'Active' if is_active(sub) else 'Inactive'
    bucket = build_bucket(r)
    g = group_totals[(stage, label)]
    g[bucket] += 1
    g['total'] += 1

print(f"{'Stage':32s} {'Bucket':10s} {'BuildDone':10s} {'Pre-Act':10s} {'NoSTLink':10s} {'Total':6s}")
print('-' * 90)
grand = {'activated':0, 'pre':0, 'noLink':0, 'total':0}
for stage in STAGES:
    for label in ['Active', 'Inactive']:
        g = group_totals.get((stage, label), {'activated':0, 'pre':0, 'noLink':0, 'total':0})
        if g['total'] == 0: continue
        print(f"{stage:32s} {label:10s} {g['activated']:<10d} {g['pre']:<10d} {g['noLink']:<10d} {g['total']:<6d}")
        for k in grand: grand[k] += g[k]
    # Stage subtotal
    sa = group_totals.get((stage, 'Active'), {'activated':0, 'pre':0, 'noLink':0, 'total':0})
    si = group_totals.get((stage, 'Inactive'), {'activated':0, 'pre':0, 'noLink':0, 'total':0})
    sub = {k: sa.get(k,0) + si.get(k,0) for k in ['activated','pre','noLink','total']}
    print(f"{'':32s} {'subtotal':10s} {sub['activated']:<10d} {sub['pre']:<10d} {sub['noLink']:<10d} {sub['total']:<6d}")
    print()

print('-' * 90)
print(f"{'GRAND TOTAL':43s} {grand['activated']:<10d} {grand['pre']:<10d} {grand['noLink']:<10d} {grand['total']:<6d}")
