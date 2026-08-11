"""How many SF Agreements are actually linked to IronClad?
Look at IronClad_Id__c on Agreement__c, plus the parent IronClad__c object."""
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

# Total Agreements + how many have IronClad linkage
desc = sf.Agreement__c.describe()
ic_fields = [f['name'] for f in desc['fields'] if 'IronClad' in f['name'] or 'Ironclad' in f['name']]
print(f"IronClad-related fields on Agreement__c: {ic_fields}")
total = sf.query("SELECT COUNT(Id) c FROM Agreement__c")['records'][0]['c']
with_ic_id = sf.query("SELECT COUNT(Id) c FROM Agreement__c WHERE IronClad_Id__c != null")['records'][0]['c']
ic_lookup_field = next((f for f in ic_fields if f.endswith('__c') and 'Id' not in f and 'URL' not in f and 'Stage' not in f and 'Status' not in f), None)
with_ic_lookup = 0
if ic_lookup_field:
    with_ic_lookup = sf.query(f"SELECT COUNT(Id) c FROM Agreement__c WHERE {ic_lookup_field} != null")['records'][0]['c']
with_ic_url = sf.query("SELECT COUNT(Id) c FROM Agreement__c WHERE IronClad_URL__c != null")['records'][0]['c']
print(f"Total Agreement__c records: {total}")
print(f"  With IronClad_Id__c populated: {with_ic_id}")
print(f"  With IronClad__c lookup populated: {with_ic_lookup}")
print(f"  With IronClad_URL__c populated: {with_ic_url}")

# By Status
print("\nBy Status:")
for r in sf.query_all("SELECT Status__c, COUNT(Id) c FROM Agreement__c GROUP BY Status__c ORDER BY COUNT(Id) DESC")['records']:
    print(f"  {r['Status__c'] or '<null>'}: {r['c']}")

# By IronClad_Stage
print("\nBy IronClad_Stage:")
for r in sf.query_all("SELECT IronClad_Stage__c, COUNT(Id) c FROM Agreement__c GROUP BY IronClad_Stage__c ORDER BY COUNT(Id) DESC")['records']:
    print(f"  {r['IronClad_Stage__c'] or '<null>'}: {r['c']}")

# How many IronClad__c parent records exist
ic_total = sf.query("SELECT COUNT(Id) c FROM IronClad__c")['records'][0]['c']
print(f"\nTotal IronClad__c parent records: {ic_total}")

# For Contract Negotiations specifically
rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']
cn_opps = sf.query_all(f"SELECT Id FROM Opportunity WHERE StageName='Contract Negotiations' AND RecordTypeId='{rt}'")
cn_ids = [o['Id'] for o in cn_opps['records']]
ids_str = "','".join(cn_ids)
cn_agr_total = sf.query(f"SELECT COUNT(Id) c FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')")['records'][0]['c']
cn_agr_ic = sf.query(f"SELECT COUNT(Id) c FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}') AND IronClad_Id__c != null")['records'][0]['c']
print(f"\nContract Negotiations MDU: {len(cn_ids)} Opps, {cn_agr_total} Agreements, {cn_agr_ic} of those linked to IronClad")
