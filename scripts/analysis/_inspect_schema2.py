import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

for obj in ['Property_Location__c', 'Agreement__c', 'SiteTracker_Project__c']:
    print(f"\n=== {obj} ALL FIELDS ===")
    desc = getattr(sf, obj).describe()
    for f in desc['fields']:
        print(f"  {f['name']:45} type={f['type']:12} label={f['label']}")
