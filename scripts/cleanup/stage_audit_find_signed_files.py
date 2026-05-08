"""Find signed-agreement PDFs uploaded by Cass Parker in SF, regardless of
what they're linked to. Then trace each back to its parent record(s) to
understand where the real agreement evidence lives."""
from simple_salesforce import Salesforce
from collections import defaultdict

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# File titles from the screenshot
HINTS = ['Ito San', 'Rubenstein', 'Cardiff Glen', 'Hygia', 'Manzanita Cove', 'Lauradia', 'Solana Beach Tennis', 'Cantebria', 'Haciendas De La Playa', 'Saxony', 'Green Valley Moble', 'Las Vistas', 'Laurel Cove', 'May Court', 'North Shore', 'Oceanic Drive', 'Portico', 'Village Park Shady']
hint_clauses = ' OR '.join(f"Title LIKE '%{h}%'" for h in HINTS)

cv = sf.query_all(f"""
    SELECT Id, ContentDocumentId, Title, FileType, FileExtension, CreatedDate, CreatedBy.Name
    FROM ContentVersion
    WHERE IsLatest = TRUE AND ({hint_clauses})
    ORDER BY Title
""")['records']
print(f"Found {len(cv)} matching ContentVersions")

doc_ids = list({r['ContentDocumentId'] for r in cv})
docs_str = "','".join(doc_ids)

# What are they linked to?
links = sf.query_all(f"""
    SELECT LinkedEntityId, LinkedEntity.Type, ContentDocumentId
    FROM ContentDocumentLink
    WHERE ContentDocumentId IN ('{docs_str}')
""")['records']
print(f"Total links: {len(links)}")

doc_links = defaultdict(list)
for r in links:
    doc_links[r['ContentDocumentId']].append((r['LinkedEntityId'], r.get('LinkedEntity', {}).get('Type')))

# For each unique entity type seen, count
type_counter = defaultdict(int)
for r in links:
    t = (r.get('LinkedEntity') or {}).get('Type')
    type_counter[t] += 1
print(f"Linked entity types: {dict(type_counter)}")

# Show each file and its parents
for r in cv[:30]:
    print(f"\n{r['Title']}.{r['FileExtension']}  ({r['CreatedDate'][:10]} by {r['CreatedBy']['Name']})")
    parents = doc_links.get(r['ContentDocumentId'], [])
    # Pull names of distinct parent IDs
    by_type = defaultdict(list)
    for pid, ptype in parents:
        by_type[ptype].append(pid)
    for ptype, pids in by_type.items():
        if not ptype: continue
        # Try to fetch Name
        if ptype in ('Opportunity','Property_Location__c','Account','User','Property_Unit__c'):
            ids_str = "','".join(pids[:50])
            try:
                rs = sf.query(f"SELECT Id, Name FROM {ptype} WHERE Id IN ('{ids_str}')")['records']
                for rec in rs[:3]:
                    print(f"  -> [{ptype}] {rec['Id']}  {rec['Name']}")
                if len(rs) > 3:
                    print(f"  -> ... +{len(rs)-3} more {ptype}")
            except Exception as e:
                print(f"  -> [{ptype}] (could not fetch Names: {e})")
        else:
            print(f"  -> [{ptype}] {len(pids)} record(s)")
