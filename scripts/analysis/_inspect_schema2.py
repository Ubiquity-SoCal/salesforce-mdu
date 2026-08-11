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

for obj in ['Property_Location__c', 'Agreement__c', 'SiteTracker_Project__c']:
    print(f"\n=== {obj} ALL FIELDS ===")
    desc = getattr(sf, obj).describe()
    for f in desc['fields']:
        print(f"  {f['name']:45} type={f['type']:12} label={f['label']}")
