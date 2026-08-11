"""Verify current SF state before rebuilding cleanup reports: RecordType API name + stage picklist."""
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Record Types on Opportunity
rts = sf.query("SELECT Id, Name, DeveloperName, IsActive FROM RecordType WHERE SobjectType='Opportunity' ORDER BY DeveloperName")['records']
print('Opportunity RecordTypes:')
for r in rts:
    print(f"  {r['DeveloperName']:30s}  Label={r['Name']!r:25s}  Active={r['IsActive']}")

# Stage picklist via describe
desc = sf.Opportunity.describe()
stage = next(f for f in desc['fields'] if f['name'] == 'StageName')
print('\nStageName picklist values (active):')
for v in stage['picklistValues']:
    if v['active']:
        print(f"  {v['value']!r}")
