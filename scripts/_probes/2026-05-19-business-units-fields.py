"""For Business ROE Opps, what's the relevant 'unit count' field?
Options:
 (a) Opportunity.Units__c (same field MDU uses, label 'Living Units')
 (b) A count rollup on the parent Property_Location__c
 (c) Something else

Check Property_Location__c fields for unit counts, and sample Business Opps to see
which fields actually have values.
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

print('=== Property_Location__c fields (looking for unit counts) ===')
d = sf.Property_Location__c.describe()
for f in d['fields']:
    nm = f['name']
    lbl = f['label']
    if 'unit' in nm.lower() or 'unit' in lbl.lower() or 'count' in nm.lower() or 'count' in lbl.lower() or f['type'] == 'summary':
        print(f"  {nm}  ({f['type']})  {lbl}  calc={f.get('calculatedFormula')}")

print('\n=== Business ROE Opp sample ===')
# Business RecordType IDs from the tracker config: 012WR00000Ra0mjYAB, 012WR00000VunSPYAZ
rt_ids = ('012WR00000Ra0mjYAB', '012WR00000VunSPYAZ')
q = (f"SELECT Id, Name, RecordType.Name, Units__c, Property_Unit__c, Property_Unit__r.Unit__c, "
     f"Property_Unit__r.Property_Location__c, Property_Unit__r.Property_Location__r.Name, "
     f"Property_Unit__r.Property_Location__r.Unit_Count__c, "
     f"Property_Unit__r.Property_Location__r.Active_Unit_Count__c "
     f"FROM Opportunity WHERE RecordTypeId IN ('{rt_ids[0]}','{rt_ids[1]}') "
     f"AND Property_Unit__c != null LIMIT 5")
try:
    for r in sf.query(q)['records']:
        pl_r = (r.get('Property_Unit__r') or {}).get('Property_Location__r') or {}
        pu_r = r.get('Property_Unit__r') or {}
        print(f"  {r['Name'][:50]}")
        print(f"    RT={r['RecordType']['Name']}  Units__c(opp)={r.get('Units__c')}")
        print(f"    Unit={pu_r.get('Unit__c')}  PL={pl_r.get('Name')}")
        print(f"    PL.Unit_Count__c={pl_r.get('Unit_Count__c')}  PL.Active_Unit_Count__c={pl_r.get('Active_Unit_Count__c')}")
except Exception as e:
    print(f'  query failed: {e}')
    # Retry without the speculative count fields
    q = (f"SELECT Id, Name, Units__c, Property_Unit__r.Property_Location__r.Name "
         f"FROM Opportunity WHERE RecordTypeId IN ('{rt_ids[0]}','{rt_ids[1]}') LIMIT 5")
    for r in sf.query(q)['records']:
        pl_r = (r.get('Property_Unit__r') or {}).get('Property_Location__r') or {}
        print(f"  {r['Name'][:50]}  Units__c(opp)={r.get('Units__c')}  PL={pl_r.get('Name')}")

# How many Business Opps have Units__c populated vs blank?
print('\n=== Business Opp Units__c population ===')
q1 = (f"SELECT COUNT() FROM Opportunity "
      f"WHERE RecordTypeId IN ('{rt_ids[0]}','{rt_ids[1]}')")
total = sf.query(q1)['totalSize']
q2 = (f"SELECT COUNT() FROM Opportunity "
      f"WHERE RecordTypeId IN ('{rt_ids[0]}','{rt_ids[1]}') AND Units__c != null")
have_units = sf.query(q2)['totalSize']
print(f'  Total Business Opps: {total}')
print(f'  With Units__c populated: {have_units}  ({100*have_units/total:.0f}% if any)')
