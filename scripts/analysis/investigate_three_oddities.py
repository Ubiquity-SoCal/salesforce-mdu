from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

investigate = [
    ('Capri on Camelback', "Name='Capri on Camelback'"),
    ('The Traditions Apartments', "Name='The Traditions Apartments'"),
    ('Coyote Creek', "Name='Coyote Creek'"),
]

for label, where in investigate:
    print(f'\n=== {label} ===')
    q = sf.query(f"""SELECT Id, Name, StageName, Sales_Status__c, Hold_Reason__c, Loss_Reason__c,
                              Owner.Name, RecordType.Name, Property_City__c, Property_State__c,
                              Units__c, Property_Type__c, Build_Type__c,
                              Agreement_Count__c, Notes_Count__c,
                              Projected_Close_Date__c, CreatedDate, LastModifiedDate,
                              Next_Action__c, Next_Action_Date__c, Monday_Item_ID__c, Agreement_Name__c
                       FROM Opportunity WHERE {where}""")
    for r in q['records']:
        for k in r:
            if k not in ('attributes',) and r[k] is not None and r[k] != '':
                print(f'  {k}: {r[k]}')

        oid = r['Id']
        ag = sf.query(f"SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c, IronClad_Stage__c, IronClad_Contract_Status__c FROM Agreement__c WHERE Opportunity__c = '{oid}'")
        if ag['totalSize']:
            print(f'  AGREEMENTS ({ag["totalSize"]}):')
            for a in ag['records']:
                print(f'    - {a["Name"]}: type={a.get("Agreement_Type__c")} status={a.get("Status__c")} signed={a.get("Signed_Date__c")} iclad_stage={a.get("IronClad_Stage__c")}')

        # Get last 5 notes
        cdl = sf.query(f"SELECT ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId = '{oid}'")
        doc_ids = [c['ContentDocumentId'] for c in cdl['records']]
        if doc_ids:
            din = "','".join(doc_ids)
            cv = sf.query(f"SELECT Id, Title, CreatedDate, FileType FROM ContentVersion WHERE ContentDocumentId IN ('{din}') AND IsLatest=true ORDER BY CreatedDate DESC")
            notes = [c for c in cv['records'] if c['FileType'] == 'SNOTE']
            print(f'  LAST 5 NOTES ({len(notes)} total):')
            for n in notes[:5]:
                print(f'    [{n["CreatedDate"][:10]}] {n["Title"][:80]}')
