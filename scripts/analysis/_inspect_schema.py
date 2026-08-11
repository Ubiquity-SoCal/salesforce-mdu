import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
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

for obj in ['Property_Location__c', 'Opportunity', 'Agreement__c', 'SiteTracker_Project__c', 'Property_Unit__c']:
    print(f"\n=== {obj} ===")
    desc = getattr(sf, obj).describe()
    for f in desc['fields']:
        n = f['name']
        if any(k in n.lower() for k in ['address', 'street', 'city', 'state', 'zip', 'name']):
            print(f"  {n:40}  type={f['type']:15}  label={f['label']}")

# Print child relationships for Opportunity
print("\n=== Opportunity child relationships ===")
desc = sf.Opportunity.describe()
for cr in desc['childRelationships']:
    if cr.get('relationshipName'):
        print(f"  {cr['relationshipName']:40}  child={cr['childSObject']}  field={cr['field']}")
