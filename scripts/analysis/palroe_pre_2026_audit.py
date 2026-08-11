"""
Pull PAL/ROE Complete Opps with CreatedDate before 2026, show what they are.
"""
import sys
from collections import Counter
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
SELECT Id, Name, CreatedDate, CreatedBy.Name, IsClosed,
       RecordType.DeveloperName, Owner.Name, Substatus__c,
       Account.Name
FROM Opportunity
WHERE StageName = 'PAL/ROE Complete'
  AND CreatedDate < 2026-01-01T00:00:00Z
ORDER BY CreatedDate ASC
"""
res = sf.query(soql)
records = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    records.extend(res['records'])

print(f"[INFO] {len(records)} PAL/ROE Complete Opps with CreatedDate before 2026\n")

# Distribution by year and creator
years = Counter()
creators = Counter()
rts = Counter()
for r in records:
    yr = r['CreatedDate'][:4]
    years[yr] += 1
    creators[r['CreatedBy']['Name']] += 1
    rts[r['RecordType']['DeveloperName'] if r.get('RecordType') else '(none)'] += 1

print("=== Created year distribution ===")
for y, c in sorted(years.items()):
    print(f"  {y}: {c}")

print("\n=== CreatedBy ===")
for n, c in creators.most_common():
    print(f"  {n}: {c}")

print("\n=== RecordType ===")
for n, c in rts.most_common():
    print(f"  {n}: {c}")

print("\n=== Sample (first 15) ===")
print(f"{'CreatedDate':24s} {'RT':14s} {'Created By':25s} {'Owner':25s} {'Name'}")
for r in records[:15]:
    print(f"{r['CreatedDate'][:19]:24s} {(r['RecordType']['DeveloperName'] if r.get('RecordType') else '-'):14s} "
          f"{r['CreatedBy']['Name'][:24]:25s} {r['Owner']['Name'][:24]:25s} {r['Name'][:60]}")
