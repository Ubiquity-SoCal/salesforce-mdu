"""Compare info richness for the 2 dupe pairs Taylor flagged."""
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

PAIRS = [
    ('Bradley Arms pair', [
        ('Killeen_MDU_Bradley Arms (Taylor: DELETE)',  '006WR00000xuzoQYAQ'),
        ('Bradley Arms (KEEP)',                         '006WR00000wkCjuYAE'),
    ]),
    ('117/121 Avenue A pair (ambiguous)', [
        ('117 and 121 E Avenue A Apartments',           '006WR00000wk9RtYAI'),
        ('Killeen_MDU_117-121_W_Avenue_A',              '006WR00000xwGf7YAE'),
    ]),
]

for label, pairs in PAIRS:
    print(f'\n========== {label} ==========')
    for tag, opp_id in pairs:
        print(f'\n--- {tag} ({opp_id}) ---')
        o = sf.query(f"""
            SELECT Id, Name, OwnerId, Owner.Name, StageName, Substatus__c,
                   Sales_Status__c, Hold_Reason__c, Loss_Reason__c,
                   Next_Action__c, Next_Action_Date__c,
                   Projected_Close_Date__c, CloseDate,
                   Agreement_Count__c, Notes_Count__c,
                   Agreement_Name__c, Property_Location__c,
                   Property_City__c, Property_State__c,
                   CreatedDate, LastModifiedDate, LastModifiedBy.Name
            FROM Opportunity WHERE Id = '{opp_id}'
        """)['records']
        if not o:
            print('   (not found)')
            continue
        o = o[0]
        for k in ['Name', 'Owner.Name', 'StageName', 'Substatus__c',
                  'Sales_Status__c', 'Hold_Reason__c', 'Loss_Reason__c',
                  'Next_Action__c', 'Next_Action_Date__c',
                  'Projected_Close_Date__c', 'CloseDate',
                  'Agreement_Count__c', 'Notes_Count__c',
                  'Agreement_Name__c', 'Property_Location__c',
                  'Property_City__c', 'Property_State__c',
                  'CreatedDate', 'LastModifiedDate']:
            if '.' in k:
                a, b = k.split('.')
                v = o.get(a, {}).get(b) if o.get(a) else None
            else:
                v = o.get(k)
            if v not in (None, '', 0, 0.0):
                print(f'   {k}: {v}')

        # Children
        agrs = sf.query(f"""
            SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
                   IronClad_ID__c, IronClad_Stage__c, Notes__c, CreatedDate
            FROM Agreement__c WHERE Opportunity__c = '{opp_id}'
            ORDER BY Agreement_Type__c
        """)['records']
        print(f'   Agreements ({len(agrs)}):')
        for a in agrs:
            ic = f"  IC:{a['IronClad_ID__c']}/{a['IronClad_Stage__c']}" if a.get('IronClad_ID__c') else ''
            sd = f"  signed:{a['Signed_Date__c']}" if a.get('Signed_Date__c') else ''
            print(f"      {a['Agreement_Type__c']:12s} {a['Name']:8s} {a['Status__c'] or '':10s}{sd}{ic}")

        notes = sf.query(f"""
            SELECT Id, Title, Body, CreatedDate FROM Note WHERE ParentId = '{opp_id}'
            ORDER BY CreatedDate DESC LIMIT 5
        """)['records']
        print(f'   Notes ({len(notes)} shown, most recent first):')
        for n in notes:
            body = (n.get('Body') or '')[:200].replace('\n', ' ')
            print(f"      [{n['CreatedDate'][:10]}] {n.get('Title','(no title)')[:80]}: {body}")

        # Contact junctions
        c = sf.query(f"""
            SELECT Id, Contact__r.Name, Role__c
            FROM Opportunity_Contact__c WHERE Opportunity__c = '{opp_id}'
        """)['records']
        print(f'   Contacts ({len(c)}):')
        for cc in c:
            cn = cc.get('Contact__r', {}).get('Name') if cc.get('Contact__r') else None
            print(f"      {cn} — {cc.get('Role__c')}")

        # ContentDocumentLinks (files)
        cdl = sf.query(f"""
            SELECT Id, ContentDocument.Title, ContentDocument.FileType
            FROM ContentDocumentLink WHERE LinkedEntityId = '{opp_id}'
        """)['records']
        print(f'   Files attached ({len(cdl)}):')
        for f in cdl:
            cd = f.get('ContentDocument', {}) or {}
            print(f"      {cd.get('Title')} ({cd.get('FileType')})")
