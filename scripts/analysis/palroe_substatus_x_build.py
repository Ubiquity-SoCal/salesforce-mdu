"""
Pull PAL/ROE Complete Opps with Substatus__c and child SiteTracker_Project__c
build/activation fields. Print a 2D matrix of Substatus x Build state so we
can see real distribution before designing the dashboard panel.
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

soql = """
SELECT Id, Name, Substatus__c,
       (SELECT Id, Name, Build_Status__c, Site_Status__c,
               Activation_Actual__c, Activation_Forecast__c, PAL_Signed_Date__c
        FROM SiteTracker_Projects__r)
FROM Opportunity
WHERE StageName = 'PAL/ROE Complete'
ORDER BY Name
"""

print("[INFO] Querying PAL/ROE Complete Opps with linked SiteTracker projects...")
res = sf.query(soql)
records = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    records.extend(res['records'])

print(f"[INFO] {len(records)} PAL/ROE Complete Opps")

# Per-Opp build state derived from child SiteTracker_Project__c set
def build_bucket(opp):
    children = (opp.get('SiteTracker_Projects__r') or {}).get('records') or []
    if not children:
        return 'No ST link'
    activated = sum(1 for c in children if c.get('Activation_Actual__c'))
    total = len(children)
    if activated == 0:
        return 'Pre-activation'
    if activated == total:
        return 'Activated'
    return f'Partial ({activated}/{total})'

def build_status_raw(opp):
    children = (opp.get('SiteTracker_Projects__r') or {}).get('records') or []
    if not children:
        return None
    statuses = sorted({c.get('Build_Status__c') or '(null)' for c in children})
    return ', '.join(statuses)

# 1) Distribution of Substatus
substatus_counts = Counter((o.get('Substatus__c') or '(blank)') for o in records)
print("\n=== Substatus distribution ===")
for k, v in substatus_counts.most_common():
    print(f"  {k:35s} {v}")

# 2) Distribution of derived Build bucket
bucket_counts = Counter(build_bucket(o) for o in records)
print("\n=== Derived Build bucket (from child ST Activation_Actual__c) ===")
for k, v in bucket_counts.most_common():
    print(f"  {k:35s} {v}")

# 3) Distribution of raw Build_Status__c values seen
raw_status_counts = Counter()
for o in records:
    children = (o.get('SiteTracker_Projects__r') or {}).get('records') or []
    for c in children:
        raw_status_counts[c.get('Build_Status__c') or '(null)'] += 1
print("\n=== Raw Build_Status__c values (across all child ST projects) ===")
for k, v in raw_status_counts.most_common():
    print(f"  {k:60s} {v}")

# 4) The matrix: Substatus x Build bucket
matrix = defaultdict(lambda: Counter())
for o in records:
    sub = o.get('Substatus__c') or '(blank)'
    bucket = build_bucket(o)
    matrix[sub][bucket] += 1

# Stable column order
all_buckets = sorted(bucket_counts.keys(), key=lambda b: (
    0 if b == 'Activated' else
    1 if b.startswith('Partial') else
    2 if b == 'Pre-activation' else
    3
))

print("\n=== Substatus x Build bucket matrix ===")
header = ['Substatus'] + all_buckets + ['Total']
widths = [max(35, max(len(s) for s in [r for r in substatus_counts] + ['(blank)']))] + [max(15, len(b)) for b in all_buckets] + [7]

def row(cells):
    return '  '.join(str(c).ljust(w) for c, w in zip(cells, widths))

print(row(header))
print(row(['-' * w for w in widths]))
sub_order = [s for s, _ in substatus_counts.most_common()]
for sub in sub_order:
    counts = [matrix[sub].get(b, 0) for b in all_buckets]
    total = sum(counts)
    print(row([sub] + counts + [total]))

print(row(['-' * w for w in widths]))
totals = [bucket_counts.get(b, 0) for b in all_buckets]
print(row(['TOTAL'] + totals + [sum(totals)]))
