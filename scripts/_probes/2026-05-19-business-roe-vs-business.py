"""Split Business app Opps by RecordType. Business ROE (building-wide, like MDU)
vs Business (per-tenant). Check Units__c population per RT.
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

# What are these two RT ids?
for rt_id in ('012WR00000Ra0mjYAB', '012WR00000VunSPYAZ'):
    r = sf.query(f"SELECT Id, Name, DeveloperName, Description FROM RecordType WHERE Id='{rt_id}'")['records'][0]
    print(f"  {rt_id}: Name={r['Name']!r}  DevName={r['DeveloperName']!r}")
    print(f"    Desc: {r.get('Description')}")
print()

# Per-RT Units__c population
for rt_id in ('012WR00000Ra0mjYAB', '012WR00000VunSPYAZ'):
    r = sf.query(f"SELECT DeveloperName FROM RecordType WHERE Id='{rt_id}'")['records'][0]
    dev = r['DeveloperName']
    total = sf.query(f"SELECT COUNT() FROM Opportunity WHERE RecordTypeId='{rt_id}'")['totalSize']
    have = sf.query(f"SELECT COUNT() FROM Opportunity WHERE RecordTypeId='{rt_id}' AND Units__c != null")['totalSize']
    have_pu = sf.query(f"SELECT COUNT() FROM Opportunity WHERE RecordTypeId='{rt_id}' AND Property_Unit__c != null")['totalSize']
    print(f"  {dev}: total={total}  with Units__c={have} ({100*have//max(total,1)}%)  with Property_Unit__c={have_pu} ({100*have_pu//max(total,1)}%)")

# Sample a few of each
print('\n=== Sample Business ROE Opps (5) ===')
roe_id = None
for rt_id in ('012WR00000Ra0mjYAB', '012WR00000VunSPYAZ'):
    r = sf.query(f"SELECT DeveloperName FROM RecordType WHERE Id='{rt_id}'")['records'][0]
    if 'ROE' in (r['DeveloperName'] or '').upper():
        roe_id = rt_id
        break

if roe_id:
    for r in sf.query(
        f"SELECT Id, Name, Units__c, Property_Unit__c, Property_Unit__r.Property_Location__r.Property_Unit_Count__c, "
        f"Property_Unit__r.Property_Location__r.Active_Unit_Count__c, Property_Address__c, StageName "
        f"FROM Opportunity WHERE RecordTypeId='{roe_id}' LIMIT 5"
    )['records']:
        pl = ((r.get('Property_Unit__r') or {}).get('Property_Location__r') or {})
        print(f"  {r['Name'][:60]}")
        print(f"    Stage={r.get('StageName')}  Opp.Units__c={r.get('Units__c')}")
        print(f"    Property_Unit__c={r.get('Property_Unit__c')}")
        print(f"    PL.Property_Unit_Count__c={pl.get('Property_Unit_Count__c')}  Active={pl.get('Active_Unit_Count__c')}")
