"""For PAL/ROE Complete Opps, find attached signed agreement FILES (not just
Agreement__c records). Files get uploaded as ContentDocuments with names like
'... - Signed.pdf' / '... Executed ...'. These are the real agreements, even
when no Agreement__c record was created."""
from simple_salesforce import Salesforce
from collections import defaultdict
import re

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

SIGN_PAT = re.compile(r'\b(signed|executed|fully executed|acknowledg|agreement|easement|PAL|ROE|consent)\b', re.I)

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']
opps = sf.query_all(f"""
    SELECT Id, Name, Owner.Name FROM Opportunity
    WHERE StageName='PAL/ROE Complete' AND RecordTypeId='{rt}'
""")['records']
ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)
opp_map = {o['Id']: o for o in opps}

# Existing Agreement records by Opp
agr_by_opp = defaultdict(list)
for r in sf.query_all(f"""
    SELECT Opportunity__c, Status__c, Agreement_Type__c, Signed_Date__c, IronClad_ID__c
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
""")['records']:
    agr_by_opp[r['Opportunity__c']].append(r)

# Files via ContentDocumentLink
cdl = sf.query_all(f"SELECT LinkedEntityId, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids_str}')")['records']
doc_to_opps = defaultdict(list)
for r in cdl:
    doc_to_opps[r['ContentDocumentId']].append(r['LinkedEntityId'])

# Pull document metadata, exclude SNOTE notes
files_by_opp = defaultdict(list)
if doc_to_opps:
    docs_str = "','".join(doc_to_opps.keys())
    cv = sf.query_all(f"""
        SELECT Id, ContentDocumentId, Title, FileType, FileExtension, ContentSize, CreatedDate, CreatedBy.Name
        FROM ContentVersion WHERE ContentDocumentId IN ('{docs_str}') AND IsLatest = TRUE
    """)['records']
    for r in cv:
        if r.get('FileType') == 'SNOTE':
            continue  # notes, not files
        for opp_id in doc_to_opps[r['ContentDocumentId']]:
            files_by_opp[opp_id].append({
                'title': r.get('Title'),
                'ftype': r.get('FileType'),
                'ext': r.get('FileExtension'),
                'size': r.get('ContentSize'),
                'date': (r.get('CreatedDate') or '')[:10],
                'by': (r.get('CreatedBy') or {}).get('Name'),
            })

# Classify
opps_with_signed_file = []
opps_without_anything = []
opps_with_only_agreement_record = []
for o in opps:
    files = files_by_opp[o['Id']]
    agrs = agr_by_opp[o['Id']]
    signed_files = [f for f in files if f.get('title') and SIGN_PAT.search(f['title'])]
    if signed_files:
        opps_with_signed_file.append((o, signed_files, agrs))
    elif agrs:
        opps_with_only_agreement_record.append((o, files, agrs))
    elif files:
        opps_without_anything.append((o, files, agrs))  # has files but none look signed
    else:
        opps_without_anything.append((o, files, agrs))

print(f"Total: {len(opps)}")
print(f"  Has signed-agreement FILE attached (regardless of Agreement__c): {len(opps_with_signed_file)}")
print(f"  No signed file but has Agreement__c record: {len(opps_with_only_agreement_record)}")
print(f"  No signed file AND no Agreement__c record: {len(opps_without_anything)}")

print()
print("=" * 100)
print("Has signed FILE but NO Agreement__c record (data gap — agreement is real, record missing)")
print("=" * 100)
gap_count = 0
for o, sfiles, agrs in opps_with_signed_file:
    if not agrs:
        gap_count += 1
        print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
        for f in sfiles[:5]:
            print(f"  FILE: {f['title']}.{f['ext']}  ({f['date']} by {f['by']})")
print(f"\nTotal: {gap_count}")

print()
print("=" * 100)
print("NO signed file AND NO Agreement__c record (genuine review candidates)")
print("=" * 100)
for o, files, agrs in opps_without_anything:
    print(f"  {o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}  files={len(files)}")
