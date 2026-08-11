from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

r = sf.query(
    "SELECT Name, CreatedDate, StageName, Amount "
    "FROM Opportunity WHERE Owner.Name = 'Julian Harrell' "
    "AND IsClosed = false ORDER BY CreatedDate"
)
for rec in r["records"]:
    amt = rec["Amount"] or 0
    print(f"  {rec['CreatedDate'][:10]} | {rec['Name']} | {rec['StageName']} | ${amt}")
print(f"\nTotal: {r['totalSize']}")
