"""Quick check: how many Opps are at each stage right now? Confirms which old stages are truly dead."""
from simple_salesforce import Salesforce
sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

q = """
SELECT StageName, RecordType.DeveloperName, COUNT(Id) cnt
FROM Opportunity
GROUP BY StageName, RecordType.DeveloperName
ORDER BY RecordType.DeveloperName, StageName
"""
for r in sf.query_all(q)['records']:
    print(f"  {r['RecordType']['DeveloperName'] if r.get('RecordType') else 'NULL':15s}  {r['StageName']:30s}  {r['cnt']}")
