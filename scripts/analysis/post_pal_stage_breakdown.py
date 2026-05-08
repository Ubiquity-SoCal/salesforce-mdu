"""
For PAL/ROE Complete + Marketing/Bulk In Progress + Marketing/Bulk Complete,
show: count, Substatus distribution, and build-state distribution.
This tells us whether substatus is meaningful on the new stages we're adding.
"""
import sys
from collections import Counter, defaultdict
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)
sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)

STAGES = ['PAL/ROE Complete', 'Marketing/Bulk In Progress', 'Marketing/Bulk Complete']

soql = """
SELECT Id, StageName, Substatus__c, RecordType.DeveloperName,
       (SELECT Activation_Actual__c FROM SiteTracker_Projects__r)
FROM Opportunity
WHERE StageName IN ('PAL/ROE Complete', 'Marketing/Bulk In Progress', 'Marketing/Bulk Complete')
"""
res = sf.query(soql)
recs = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    recs.extend(res['records'])

print(f"Total: {len(recs)} Opps across 3 post-PAL stages\n")

def build_bucket(o):
    children = (o.get('SiteTracker_Projects__r') or {}).get('records') or []
    if not children: return 'No ST Link'
    if any(c.get('Activation_Actual__c') for c in children): return 'Build Done'
    return 'Pre-Activation'

# Per-stage breakdowns
for stage in STAGES:
    subset = [r for r in recs if r['StageName'] == stage]
    print(f"=== {stage} ({len(subset)}) ===")
    rt = Counter((r.get('RecordType') or {}).get('DeveloperName') or '-' for r in subset)
    print(f"  By RT:        {dict(rt)}")
    sub = Counter(r.get('Substatus__c') or '(blank)' for r in subset)
    print(f"  By Substatus:")
    for k, v in sub.most_common():
        print(f"    {k:40s} {v}")
    bb = Counter(build_bucket(r) for r in subset)
    print(f"  By Build:     {dict(bb)}")
    print()

# Stage x Build matrix (regardless of substatus)
print("=== Stage x Build State matrix (all 3 stages) ===")
matrix = defaultdict(lambda: Counter())
for r in recs:
    matrix[r['StageName']][build_bucket(r)] += 1

cols = ['Build Done', 'Pre-Activation', 'No ST Link']
print(f"{'Stage':32s} {'  '.join(c.ljust(15) for c in cols)}  Total")
for stage in STAGES:
    row = matrix[stage]
    cells = [row.get(c, 0) for c in cols]
    print(f"{stage:32s} {'  '.join(str(c).ljust(15) for c in cells)}  {sum(cells)}")
