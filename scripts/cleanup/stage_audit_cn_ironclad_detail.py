"""Show which Contract Negotiations Agreements are vs aren't IronClad-linked."""
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

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']
cn_opps = sf.query_all(f"""
    SELECT Id, Name, Owner.Name FROM Opportunity
    WHERE StageName='Contract Negotiations' AND RecordTypeId='{rt}'
""")['records']
ids = [o['Id'] for o in cn_opps]
opp_map = {o['Id']: o for o in cn_opps}
ids_str = "','".join(ids)

agrs = sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c, Signed_Date__c,
           IronClad_ID__c, IronClad_Record__c, IronClad_Stage__c, IronClad_Contract_Status__c,
           CreatedDate, LastModifiedDate
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
    ORDER BY Opportunity__c, Name
""")['records']

linked = [a for a in agrs if a.get('IronClad_ID__c')]
unlinked = [a for a in agrs if not a.get('IronClad_ID__c')]
print(f"Total Agreements on CN Opps: {len(agrs)}")
print(f"  IronClad-linked: {len(linked)}")
print(f"  NOT linked (manual SF entries): {len(unlinked)}")

print("\n=== IronClad-linked (3) ===")
for a in linked:
    opp = opp_map.get(a['Opportunity__c'], {})
    print(f"  {a['Name']}  Opp={opp.get('Name')}  Owner={(opp.get('Owner') or {}).get('Name')}")
    print(f"    Status={a.get('Status__c')}  Type={a.get('Agreement_Type__c')}  Signed={a.get('Signed_Date__c')}")
    print(f"    IC_ID={a.get('IronClad_ID__c')}  IC_Stage={a.get('IronClad_Stage__c')}  IC_Status={a.get('IronClad_Contract_Status__c')}")

print(f"\n=== NOT linked ({len(unlinked)}) — manual SF entries ===")
for a in unlinked:
    opp = opp_map.get(a['Opportunity__c'], {})
    print(f"  {a['Name']}  Status={a.get('Status__c'):<12} Type={a.get('Agreement_Type__c'):<20} Opp={opp.get('Name')}")
