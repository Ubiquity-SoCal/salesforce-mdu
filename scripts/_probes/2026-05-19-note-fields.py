"""Check Note__c custom object existence and structure."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)
for obj in ('Note__c',):
    try:
        d = getattr(sf, obj).describe()
        print(f'=== {obj} ===')
        for f in d['fields']:
            nm = f['name']
            if nm.endswith('__c') or nm in ('Id','Name','CreatedDate'):
                ref = f.get('referenceTo')
                ref_str = f"  -> {ref}" if ref else ''
                print(f"  {nm}  ({f['type']}){ref_str}  {f['label']}")
    except Exception as e:
        print(f'{obj} not present: {type(e).__name__}')
