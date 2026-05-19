"""List Opportunity custom fields to find correct API names."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)
d = sf.Opportunity.describe()
for f in d['fields']:
    nm = f['name']
    if nm.endswith('__c') or nm in ('Id','Name','StageName','CloseDate','Probability','Description','OwnerId','CreatedDate','LastModifiedDate','RecordTypeId'):
        print(f"{nm}  ({f['type']})  {f['label']}")
