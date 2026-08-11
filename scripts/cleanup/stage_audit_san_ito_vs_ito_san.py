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

ids = ['006WR00000ywTezYAE', '006WR0000112vHHYAY']
for opp_id in ids:
    o = sf.query(f"""
        SELECT Id, Name, StageName, RecordType.DeveloperName, Owner.Name,
               CreatedDate, LastModifiedDate, Sales_Status__c, Next_Action__c,
               Projected_Close_Date__c, CloseDate, Description,
               Account.Name, Property_Location__c, Property_Location__r.Name
        FROM Opportunity WHERE Id = '{opp_id}'
    """)['records'][0]
    print(f"\n{'='*80}")
    print(f"{o['Name']}  (Id={o['Id']})  RT={o['RecordType']['DeveloperName']}  Stage={o['StageName']}")
    print(f"  Owner: {o['Owner']['Name']}  Created: {o['CreatedDate'][:10]}  Modified: {o['LastModifiedDate'][:10]}")
    print(f"  Account: {(o.get('Account') or {}).get('Name')}")
    print(f"  Property_Location: {o.get('Property_Location__c')} ({(o.get('Property_Location__r') or {}).get('Name')})")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}  CloseDate: {o.get('CloseDate')}")
    print(f"  Next_Action: {o.get('Next_Action__c')}")
    if o.get('Description'):
        print(f"  Description: {o['Description'][:300]}")

    # Agreements
    agrs = sf.query_all(f"""
        SELECT Name, Status__c, Agreement_Type__c, Signed_Date__c, IronClad_ID__c
        FROM Agreement__c WHERE Opportunity__c = '{opp_id}'
    """)['records']
    print(f"  Agreements: {len(agrs)}")
    for a in agrs:
        print(f"    {a['Name']}  Status={a['Status__c']}  Type={a['Agreement_Type__c']}  Signed={a['Signed_Date__c']}  IC={a['IronClad_ID__c']}")

    # Files / Notes
    cdl = sf.query_all(f"SELECT ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId = '{opp_id}'")['records']
    if cdl:
        ids_str = "','".join(r['ContentDocumentId'] for r in cdl)
        cv = sf.query_all(f"""
            SELECT Title, FileType, FileExtension, CreatedDate, CreatedBy.Name
            FROM ContentVersion WHERE ContentDocumentId IN ('{ids_str}') AND IsLatest = TRUE
        """)['records']
        print(f"  Files/Notes: {len(cv)}")
        for v in cv:
            print(f"    [{v['FileType']}] {v['Title']}.{v.get('FileExtension')}  ({v['CreatedDate'][:10]} by {v['CreatedBy']['Name']})")
    else:
        print(f"  Files/Notes: 0")
