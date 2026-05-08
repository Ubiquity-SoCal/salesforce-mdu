"""Audit all Cleanup_* reports in SF: any duplicates? What devNames exist? What folders?"""
from simple_salesforce import Salesforce
sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

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
