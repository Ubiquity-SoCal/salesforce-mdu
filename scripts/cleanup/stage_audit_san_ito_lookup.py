"""For San Ito + the 13 'no signal' Opps, search for Property_Location matches
by name fragments and check whether THOSE PL records have signed files attached."""
from simple_salesforce import Salesforce
from collections import defaultdict
import re

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

SIGN_PAT = re.compile(r'\b(signed|executed|fully executed|acknowledg|agreement|easement|PAL|ROE|consent)\b', re.I)

REVIEW_OPPS = [
    ('Paul Mark Apts', 'Paul Mark', 'Tanya Friese'),
    ('Lexington Place (Monterey)', 'Lexington', 'Chuck McNeely'),
    ('Killeen_MDU_Bradley Arms', 'Bradley', 'Tanya Friese'),
    ('Omaha_MDU_4760 LAFAYETTE AVE', 'LAFAYETTE', 'Melissa Baker'),
    ('Omaha_MDU_5004 Davenport St', 'Davenport', 'Melissa Baker'),
    ('Omaha_MDU_Benson Crest Apartments 2', 'Benson Crest', 'Melissa Baker'),
    ('Omaha_MDU_4612 Redman Ave', 'Redman', 'Melissa Baker'),
    ('Omaha_MDU_9208 Ohio St', 'Ohio St', 'Melissa Baker'),
    ('Decatur_MDU_Smallwood Trailer Park', 'Smallwood', 'Melissa Baker'),
    ('Omaha_MDU_Farnam Flats', 'Farnam', 'Melissa Baker'),
    ('Converge Justin', 'Converge', 'Brett Spivey'),
    ('512-514 Via De La Valle', 'Via De La Valle', 'Justin Barry'),
    ('San Ito', 'Ito', 'Justin Barry'),
]

for name, frag, owner in REVIEW_OPPS:
    print(f"\n{'='*100}")
    print(f"{name}  ({owner})")
    print('='*100)

    # PL by name match
    pls = sf.query(f"""
        SELECT Id, Name, Property_Location_Name__c, City__c, State__c
        FROM Property_Location__c
        WHERE Name LIKE '%{frag}%' OR Property_Location_Name__c LIKE '%{frag}%'
        LIMIT 15
    """)['records']
    if not pls:
        print(f"  no PL matches for fragment '{frag}'")
        continue

    pl_ids = [p['Id'] for p in pls]
    pl_str = "','".join(pl_ids)
    cdl = sf.query_all(f"SELECT LinkedEntityId, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{pl_str}')")['records']
    doc_to_pl = defaultdict(list)
    for r in cdl:
        doc_to_pl[r['ContentDocumentId']].append(r['LinkedEntityId'])

    files_by_pl = defaultdict(list)
    if doc_to_pl:
        docs_str = "','".join(doc_to_pl.keys())
        cv = sf.query_all(f"""
            SELECT Id, ContentDocumentId, Title, FileType, FileExtension, CreatedDate
            FROM ContentVersion WHERE ContentDocumentId IN ('{docs_str}') AND IsLatest = TRUE
        """)['records']
        for r in cv:
            if r.get('FileType') == 'SNOTE': continue
            for pl_id in doc_to_pl[r['ContentDocumentId']]:
                files_by_pl[pl_id].append((r.get('Title'), r.get('FileExtension'), r['CreatedDate'][:10]))

    for p in pls[:8]:
        flist = files_by_pl.get(p['Id'], [])
        signed = [f for f in flist if f[0] and SIGN_PAT.search(f[0])]
        if signed:
            print(f"  PL {p['Id']}  {p['Name']}  ({p.get('City__c')}, {p.get('State__c')})  -- {len(signed)} signed file(s):")
            for t, ext, d in signed[:5]:
                print(f"    {d}  {t}.{ext}")
        elif flist:
            print(f"  PL {p['Id']}  {p['Name']}  ({p.get('City__c')}, {p.get('State__c')})  -- {len(flist)} file(s) but no signed-keyword match:")
            for t, ext, d in flist[:3]:
                print(f"    {d}  {t}.{ext}")
        else:
            print(f"  PL {p['Id']}  {p['Name']}  ({p.get('City__c')}, {p.get('State__c')})  -- no files")
