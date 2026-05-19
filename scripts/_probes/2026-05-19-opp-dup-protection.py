"""Check what (if any) duplicate protection exists for Opportunity in this org."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

# Field-level uniqueness on Opp custom fields
d = sf.Opportunity.describe()
print('=== Opportunity uniqueness ===')
print(f'  Name:  unique=False (standard, never unique)')
for f in d['fields']:
    if f['name'].endswith('__c') and f.get('unique'):
        print(f"  {f['name']}: unique=True (label={f['label']})")

# Check Agreement_Name__c specifically
for f in d['fields']:
    if f['name'] == 'Agreement_Name__c':
        print(f"\n  Agreement_Name__c: unique={f.get('unique')}  externalId={f.get('externalId')}  label={f['label']}")

# DuplicateRules on Opportunity via Tooling API
print('\n=== DuplicateRules on Opportunity ===')
try:
    res = sf.toolingexecute(
        "query/?q=" + "SELECT+Id,DeveloperName,MasterLabel,SobjectType,IsActive+FROM+DuplicateRule+WHERE+SobjectType='Opportunity'"
    )
    for r in res.get('records', []):
        print(f"  {r['DeveloperName']}  IsActive={r['IsActive']}  Label={r['MasterLabel']}")
    if not res.get('records'):
        print('  (none)')
except Exception as e:
    print(f'  Tooling query failed: {e}')

# Validation rules on Opportunity
print('\n=== Validation rules on Opportunity ===')
try:
    res = sf.toolingexecute(
        "query/?q=" + "SELECT+Id,ValidationName,Active+FROM+ValidationRule+WHERE+EntityDefinition.QualifiedApiName='Opportunity'"
    )
    for r in res.get('records', []):
        print(f"  {r['ValidationName']}  Active={r['Active']}")
    if not res.get('records'):
        print('  (none)')
except Exception as e:
    print(f'  Tooling query failed: {e}')
