"""
Investigate why Justin Barry's bucket shows almost everything in Prospecting.
Goal: figure out which Opps were upgraded from Prospects to Prospecting based on
recent Note imports rather than real 2026 activity.

Output:
1. Count of Justin's Opps by Stage
2. For each Prospecting Opp: Note count, Note created dates, what triggered the upgrade
3. Which Opps have [Ting Exclusive Priority] in Action-style fields
"""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter
import json

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Justin Barry user lookup
jb = sf.query("SELECT Id, Name, IsActive FROM User WHERE Name LIKE 'Justin%Barry%'")
print("Justin user lookup:")
for r in jb['records']:
    print(f"  {r['Id']}  {r['Name']}  active={r['IsActive']}")
print()

JB_ID = jb['records'][0]['Id']

# Stage breakdown for Justin's Opps
stage_q = sf.query(f"""
    SELECT StageName, COUNT(Id) c
    FROM Opportunity
    WHERE OwnerId = '{JB_ID}'
    GROUP BY StageName
    ORDER BY COUNT(Id) DESC
""")
print(f"Justin's Opp count by Stage:")
for r in stage_q['records']:
    print(f"  {r['StageName']:35s} {r['c']:5d}")
print()

# Find any Action-like fields on Opportunity
print("Looking for Action-like fields on Opportunity...")
opp_desc = sf.Opportunity.describe()
action_fields = [f['name'] for f in opp_desc['fields'] if 'action' in f['name'].lower() or 'priority' in f['name'].lower()]
print(f"  Opportunity fields w/ action|priority: {action_fields}")

# Check Sales_Status picklist values (might be where Ting Exclusive Priority lives)
ss_field = next((f for f in opp_desc['fields'] if f['name'] == 'Sales_Status__c'), None)
if ss_field:
    print(f"  Sales_Status__c values: {[p['value'] for p in ss_field['picklistValues']]}")
print()

# Pull all Justin's Prospecting Opps with key fields including Next_Action__c
prospecting = sf.query_all(f"""
    SELECT Id, Name, StageName, Sales_Status__c, CreatedDate, LastModifiedDate,
           Projected_Close_Date__c, Notes_Count__c, Next_Action__c, Next_Action_Date__c,
           RecordType.Name
    FROM Opportunity
    WHERE OwnerId = '{JB_ID}' AND StageName = 'Prospecting'
    ORDER BY Name
""")
print(f"Justin's Prospecting Opps: {prospecting['totalSize']}")

opp_ids = [r['Id'] for r in prospecting['records']]

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

note_dates_by_opp = defaultdict(list)
note_titles_by_opp = defaultdict(list)
all_note_dates = []

# Step 1: per chunk of opps, get ContentDocumentLink (LinkedEntityId -> ContentDocumentId)
# Step 2: fetch ContentDocument with LatestPublishedVersionId (ContentNote uses ContentVersion under the hood)
# We need note creation date; ContentDocument.CreatedDate works for the document; but for notes the ContentNote
# query is the cleanest way. Use ContentNote where Id IN list of doc ids (Note is stored where ContentDocument
# and ContentVersion share Id behavior). Easier path: query ContentVersion filtered by ContentDocumentId IN doc ids.
for chunk in chunked(opp_ids, 100):
    in_clause = "','".join(chunk)
    cdl = sf.query_all(f"""
        SELECT LinkedEntityId, ContentDocumentId
        FROM ContentDocumentLink
        WHERE LinkedEntityId IN ('{in_clause}')
    """)
    cd_to_opp = {}
    for r in cdl['records']:
        cd_to_opp.setdefault(r['ContentDocumentId'], []).append(r['LinkedEntityId'])
    if not cd_to_opp:
        continue

    # Now query the underlying ContentVersions (Notes) for those docs
    doc_ids = list(cd_to_opp.keys())
    for doc_chunk in chunked(doc_ids, 200):
        din = "','".join(doc_chunk)
        cv = sf.query_all(f"""
            SELECT Id, ContentDocumentId, Title, CreatedDate, FileType
            FROM ContentVersion
            WHERE ContentDocumentId IN ('{din}')
            AND IsLatest = true
        """)
        for v in cv['records']:
            if v['FileType'] != 'SNOTE':
                continue  # only count Notes, not file attachments
            doc_id = v['ContentDocumentId']
            d = v['CreatedDate'][:10]
            for opp_id in cd_to_opp.get(doc_id, []):
                note_dates_by_opp[opp_id].append(d)
                note_titles_by_opp[opp_id].append(v['Title'])
                all_note_dates.append(d)

print(f"\nAll Note created dates across Justin's Prospecting Opps:")
for d, c in sorted(Counter(all_note_dates).items()):
    print(f"  {d}  {c}")

# Categorize each Opp by what kept it in Prospecting
BULK_DATES = {'2026-03-24', '2026-04-25'}
classification = {'has_real_2026_note': [], 'has_close_date': [], 'only_bulk_notes': [], 'no_notes_no_date': []}
ting_priority_opps = []
for r in prospecting['records']:
    oid = r['Id']
    dates = note_dates_by_opp.get(oid, [])
    real_2026_dates = [d for d in dates if d.startswith('2026') and d not in BULK_DATES]
    has_real = len(real_2026_dates) > 0
    has_close = r['Projected_Close_Date__c'] is not None
    next_action = r.get('Next_Action__c') or ''
    if 'Ting Exclusive Priority' in next_action:
        ting_priority_opps.append(r)
    if has_real:
        classification['has_real_2026_note'].append((r, real_2026_dates))
    elif has_close:
        classification['has_close_date'].append(r)
    elif dates:
        classification['only_bulk_notes'].append((r, sorted(set(dates))))
    else:
        classification['no_notes_no_date'].append(r)

print(f"\n=== Opps with [Ting Exclusive Priority] in Next_Action__c: {len(ting_priority_opps)} ===")
for r in ting_priority_opps[:20]:
    print(f"  {r['Name'][:60]:60s} Action={(r.get('Next_Action__c') or '')[:80]}")

print(f"\n=== CLASSIFICATION ===")
print(f"Has real 2026 note (NOT bulk import day): {len(classification['has_real_2026_note'])}")
print(f"Has Projected Close Date (no real note):  {len(classification['has_close_date'])}")
print(f"Only bulk import day notes:               {len(classification['only_bulk_notes'])}")
print(f"No notes, no close date (likely Tasks):   {len(classification['no_notes_no_date'])}")

# Show samples
print(f"\n--- Sample: Has real 2026 note (first 10) ---")
for r, dates in classification['has_real_2026_note'][:10]:
    print(f"  {r['Name'][:60]:60s} note dates: {dates}")

print(f"\n--- Sample: Only bulk notes (first 10) ---")
for r, dates in classification['only_bulk_notes'][:10]:
    print(f"  {r['Name'][:60]:60s} bulk dates: {dates}")

# Dump full result for further analysis
out = {
    'jb_id': JB_ID,
    'stage_counts': {r['StageName']: r['c'] for r in stage_q['records']},
    'prospecting_total': prospecting['totalSize'],
    'classification_counts': {k: len(v) for k, v in classification.items()},
    'all_note_date_histogram': dict(Counter(all_note_dates)),
    'opps_with_real_2026': [{'Id': r['Id'], 'Name': r['Name'], 'real_dates': d} for r, d in classification['has_real_2026_note']],
    'opps_only_bulk': [{'Id': r['Id'], 'Name': r['Name'], 'bulk_dates': d} for r, d in classification['only_bulk_notes']],
    'opps_close_only': [{'Id': r['Id'], 'Name': r['Name'], 'close': r['Projected_Close_Date__c']} for r in classification['has_close_date']],
    'opps_no_notes_no_date': [{'Id': r['Id'], 'Name': r['Name']} for r in classification['no_notes_no_date']],
}
with open('justin_prospecting_audit.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print("\nWrote justin_prospecting_audit.json")
