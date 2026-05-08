"""Compare agreement footprint of each dupe vs its keeper.

If a dupe has an agreement type the keeper doesn't, deleting the dupe loses data.
"""
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

PAIRS = [
    ('Killeen_MDU_The Bungalows', '006WR00000xwHL3YAM', 'The Bungalows', '006WR00000wkEboYAE'),
    ('Killeen_MDU_Bradley Arms',  '006WR00000xuzoQYAQ', 'Bradley Arms',  '006WR00000wkCjuYAE'),
    ('Killeen_MDU_117-121_W_Avenue_A', '006WR00000xwGf7YAE', '117 and 121 E Avenue A Apartments', '006WR00000wk9RtYAI'),
]

for dupe_name, dupe_id, keep_name, keep_id in PAIRS:
    print(f'\n=== {dupe_name} (DUPE) vs {keep_name} (KEEPER) ===')
    for label, oid in [('DUPE', dupe_id), ('KEEPER', keep_id)]:
        ag = sf.query(f"""
            SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
                   IronClad_ID__c, IronClad_Stage__c
            FROM Agreement__c WHERE Opportunity__c = '{oid}'
            ORDER BY Agreement_Type__c
        """)['records']
        print(f'  {label} ({oid}): {len(ag)} agreements')
        for a in ag:
            ic = f' IC:{a["IronClad_ID__c"]}/{a["IronClad_Stage__c"]}' if a.get('IronClad_ID__c') else ' (no IronClad)'
            sd = f' signed:{a["Signed_Date__c"]}' if a.get('Signed_Date__c') else ''
            print(f"    {a['Agreement_Type__c']:15s} {a['Name']:9s} Status={a['Status__c']:10s}{sd}{ic}")
