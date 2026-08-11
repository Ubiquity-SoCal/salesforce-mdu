"""For each PAL/ROE Complete MDU Opp, check if there's an active or completed
EMA/Bulk Agreement child. Those are the only candidates for bumping to
EMA/Bulk In Progress or EMA/Bulk Complete. SiteTracker linkage doesn't matter."""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

EMA_BULK_TYPES = ('EMA','Bulk','NEMA','2nd ISP MSA Addendum','MSA','EMA Addendum','Bulk Addendum')

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']
opps = sf.query_all(f"""
    SELECT Id, Name, Owner.Name, Next_Action__c, Projected_Close_Date__c, Sales_Status__c
    FROM Opportunity
    WHERE StageName='PAL/ROE Complete' AND RecordTypeId='{rt}'
""")['records']
ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)
opp_map = {o['Id']: o for o in opps}

agrs = sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c, Signed_Date__c,
           IronClad_ID__c, IronClad_Stage__c
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
""")['records']

emabulk_by_opp = defaultdict(list)
for a in agrs:
    if a.get('Agreement_Type__c') in EMA_BULK_TYPES:
        emabulk_by_opp[a['Opportunity__c']].append(a)

active_emabulk = []  # Review/Sign — should be EMA/Bulk In Progress
completed_emabulk = []  # Completed — should be EMA/Bulk Complete
all_cancelled_emabulk = []  # All Cancelled — leave in PAL/ROE Complete

for opp_id, eb_agrs in emabulk_by_opp.items():
    has_active = any(a.get('Status__c') in ('Review','Sign') for a in eb_agrs)
    has_completed = any(a.get('Status__c') == 'Completed' or a.get('Signed_Date__c') for a in eb_agrs)
    all_cancelled = all(a.get('Status__c') == 'Cancelled' for a in eb_agrs)

    if has_active and not has_completed:
        active_emabulk.append((opp_map[opp_id], eb_agrs))
    elif has_completed and not has_active:
        completed_emabulk.append((opp_map[opp_id], eb_agrs))
    elif has_active and has_completed:
        # both — check which is more recent / dominant
        active_emabulk.append((opp_map[opp_id], eb_agrs))  # in progress wins
    elif all_cancelled:
        all_cancelled_emabulk.append((opp_map[opp_id], eb_agrs))

print(f"PAL/ROE Complete with EMA/Bulk Agreement child: {len(emabulk_by_opp)}")
print(f"  Active EMA/Bulk (Review/Sign) -> bump to EMA/Bulk In Progress: {len(active_emabulk)}")
print(f"  Completed EMA/Bulk -> bump to EMA/Bulk Complete: {len(completed_emabulk)}")
print(f"  All Cancelled (leave alone): {len(all_cancelled_emabulk)}")

print()
print("=" * 100)
print(f"-> EMA/Bulk In Progress ({len(active_emabulk)})")
print("=" * 100)
for o, eb in active_emabulk:
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}")
    print(f"  Next_Action: {o.get('Next_Action__c')}")
    for a in eb:
        print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")

print()
print("=" * 100)
print(f"-> EMA/Bulk Complete ({len(completed_emabulk)})")
print("=" * 100)
for o, eb in completed_emabulk:
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}")
    print(f"  Next_Action: {o.get('Next_Action__c')}")
    for a in eb:
        print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")

print()
print("=" * 100)
print(f"All Cancelled EMA/Bulk - stay PAL/ROE Complete ({len(all_cancelled_emabulk)})")
print("=" * 100)
for o, eb in all_cancelled_emabulk:
    print(f"  {o['Name']}  Owner={o['Owner']['Name']}")
    for a in eb:
        print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')}")
