"""For each of my 13 'no signal' Opps, search for OTHER Opps with similar name
that might have the agreement evidence (potential duplicates from the
CA MDU Merge or earlier imports)."""
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

REVIEW = [
    ('San Ito',                            '006WR00000ywTezYAE',  'Justin',   'Ito'),
    ('512-514 Via De La Valle',            '006WR00000ywTDZYA2',  'Justin',   'Via De La Valle'),
    ('Converge Justin',                    '006WR00000yvY5dYAE',  'Brett',    'Converge'),
    ('Lexington Place (Monterey)',         '006WR00000wkEcKYAU',  'Chuck',    'Lexington'),
    ('Paul Mark Apts',                     '006WR00000wkAC1YAM',  'Tanya',    'Paul Mark'),
    ('Killeen_MDU_Bradley Arms',           '006WR00000xuzoQYAQ',  'Tanya',    'Bradley'),
    ('Decatur_MDU_Smallwood Trailer Park', '006WR00000y3k5NYAQ',  'Melissa',  'Smallwood'),
    ('Omaha_MDU_4612 Redman Ave',          '006WR00000y3jyvYAA',  'Melissa',  'Redman'),
    ('Omaha_MDU_4760 LAFAYETTE AVE',       '006WR00000y2FzkYAE',  'Melissa',  'Lafayette'),
    ('Omaha_MDU_5004 Davenport St',        '006WR00000y3J0LYAU',  'Melissa',  'Davenport'),
    ('Omaha_MDU_9208 Ohio St',             '006WR00000y3k29YAA',  'Melissa',  'Ohio'),
    ('Omaha_MDU_Benson Crest Apartments 2','006WR00000y3NdSYAU',  'Melissa',  'Benson'),
    ('Omaha_MDU_Farnam Flats',             '006WR00000y46nRYAQ',  'Melissa',  'Farnam'),
]

for name, opp_id, owner, frag in REVIEW:
    print(f"\n{'='*100}")
    print(f"{name}  ({owner}, {opp_id})  searching for similar Opps with fragment '{frag}'")
    print('='*100)
    rs = sf.query_all(f"""
        SELECT Id, Name, StageName, RecordType.DeveloperName, Owner.Name,
               CreatedDate, Agreement_Count__c, Notes_Count__c
        FROM Opportunity
        WHERE Name LIKE '%{frag}%' AND Id != '{opp_id}'
        ORDER BY CreatedDate
        LIMIT 20
    """)['records']
    if not rs:
        print(f"  No similar Opps found.")
        continue
    for r in rs:
        rt = (r.get('RecordType') or {}).get('DeveloperName')
        own = (r.get('Owner') or {}).get('Name')
        print(f"  {r['Id']}  {r['Name']}  [{rt}] Stage={r['StageName']}  Owner={own}  Created={r['CreatedDate'][:10]}  Agr={r['Agreement_Count__c']}  Notes={r['Notes_Count__c']}")
