"""
Where does the 343 vs 303 gap come from?
Break PAL/ROE Complete by RecordType and IsClosed.
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

res = sf.query("""
SELECT Id, IsClosed, CreatedDate, RecordType.DeveloperName
FROM Opportunity
WHERE StageName = 'PAL/ROE Complete'
""")
recs = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    recs.extend(res['records'])

print(f"Total PAL/ROE Complete: {len(recs)}\n")

rt = Counter()
closed = Counter()
yr = Counter()
combo = Counter()
for r in recs:
    r_rt = (r.get('RecordType') or {}).get('DeveloperName') or '(none)'
    rt[r_rt] += 1
    closed[r['IsClosed']] += 1
    yr[r['CreatedDate'][:4]] += 1
    combo[(r_rt, r['IsClosed'], r['CreatedDate'][:4])] += 1

print("=== By RecordType ===")
for k, v in rt.most_common():
    print(f"  {k:20s} {v}")

print("\n=== By IsClosed ===")
for k, v in closed.most_common():
    print(f"  {k}: {v}")

print("\n=== By Created Year ===")
for k, v in sorted(yr.items()):
    print(f"  {k}: {v}")

print("\n=== Combinations (RT, IsClosed, Year) ===")
for k, v in combo.most_common():
    print(f"  RT={k[0]:20s} IsClosed={k[1]} Year={k[2]} -> {v}")

# Replicate the dashboard's MDU filter
mdu_open_2026 = sum(1 for r in recs
    if ((r.get('RecordType') or {}).get('DeveloperName') in ('MDU', 'SFU'))
    and r['IsClosed'] == False
    and r['CreatedDate'] >= '2026-01-01')
print(f"\nReplicate dashboard MDU filter: {mdu_open_2026}")
