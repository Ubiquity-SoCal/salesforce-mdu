"""Audit all Cleanup_* reports in SF: any duplicates? What devNames exist? What folders?"""
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Reports are queryable via the Report SObject
q = """
SELECT Id, Name, DeveloperName, FolderName, OwnerId, LastModifiedDate, CreatedDate
FROM Report
WHERE DeveloperName LIKE 'Cleanup%'
ORDER BY DeveloperName, CreatedDate
"""
records = sf.query_all(q)['records']
print(f'Found {len(records)} Cleanup* reports in SF:\n')
for r in records:
    print(f"  {r['Id']}  {r['DeveloperName']:45s}  Folder={r['FolderName']!r:25s}")
    print(f"    Name={r['Name']!r}")
    print(f"    Created={r['CreatedDate'][:19]}  Modified={r['LastModifiedDate'][:19]}")
