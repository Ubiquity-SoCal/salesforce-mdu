"""Quick check: how many Opps are at each stage right now? Confirms which old stages are truly dead."""
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

q = """
SELECT StageName, RecordType.DeveloperName, COUNT(Id) cnt
FROM Opportunity
GROUP BY StageName, RecordType.DeveloperName
ORDER BY RecordType.DeveloperName, StageName
"""
for r in sf.query_all(q)['records']:
    print(f"  {r['RecordType']['DeveloperName'] if r.get('RecordType') else 'NULL':15s}  {r['StageName']:30s}  {r['cnt']}")
