"""Diff Weekly_MDU_Sales_Updates.xlsx against existing SF ContentNotes on matched Opps.
Flag rows with fresh content (Action Items or Notes) that isn't already captured.
"""
import pandas as pd, json, re
from pathlib import Path
from difflib import SequenceMatcher
from simple_salesforce import Salesforce

SRC = r'C:\Users\cass\Downloads\Weekly_MDU_Sales_Updates.xlsx'
OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
OUT.mkdir(exist_ok=True)

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

mdu = pd.read_excel(SRC, sheet_name='MDU_Sales')
saq = pd.read_excel(SRC, sheet_name='SAQ_Sales')
mdu['_sheet'] = 'MDU_Sales'
saq['_sheet'] = 'SAQ_Sales'
saq = saq.rename(columns={'SiteTracker Name': 'Site Tracker Name'})

rows = pd.concat([mdu, saq], ignore_index=True)
print(f'Total rows: {len(rows)}  (MDU={len(mdu)}, SAQ={len(saq)})')

# Collect unique Site Tracker Names (= Agreement_Name__c values typically)
rows['Site Tracker Name'] = rows['Site Tracker Name'].astype(str).where(rows['Site Tracker Name'].notna(), None)
agreement_keys = sorted({a for a in rows['Site Tracker Name'].dropna().unique() if a and a.lower() != 'nan'})
print(f'Unique Site Tracker Names: {len(agreement_keys)}')

# Query SF Opps by Agreement_Name__c in batches
opp_by_agreement = {}
BATCH = 100
for i in range(0, len(agreement_keys), BATCH):
    batch = agreement_keys[i:i+BATCH]
    escaped = [b.replace("\\", "\\\\").replace("'", "\\'") for b in batch]
    ids = "','".join(escaped)
    q = f"SELECT Id, Name, Agreement_Name__c, StageName FROM Opportunity WHERE Agreement_Name__c IN ('{ids}')"
    r = sf.query_all(q)
    for rec in r['records']:
        opp_by_agreement.setdefault(rec['Agreement_Name__c'], []).append(rec)

# For missing ones, try name fuzzy match
missing_agreements = [a for a in agreement_keys if a not in opp_by_agreement]
print(f'Agreement-Name matches: {len(agreement_keys) - len(missing_agreements)}')
print(f'Not found by Agreement Name, will try Property Name: {len(missing_agreements)}')

fallback = {}
for agree in missing_agreements:
    prop_rows = rows[rows['Site Tracker Name'] == agree]
    if prop_rows.empty:
        continue
    pname = str(prop_rows.iloc[0]['Property Name'])
    search = pname.split(',')[0].split('(')[0].strip()
    if len(search) < 4:
        continue
    esc = search.replace("\\", "\\\\").replace("'", "\\'")
    q = f"SELECT Id, Name, Agreement_Name__c, StageName FROM Opportunity WHERE Name LIKE '%{esc}%' OR Agreement_Name__c LIKE '%{esc}%'"
    r = sf.query_all(q)
    fallback[agree] = r['records']

# Pull existing notes on all candidate Opps
all_opp_ids = set()
for recs in opp_by_agreement.values():
    all_opp_ids.update(r['Id'] for r in recs)
for recs in fallback.values():
    all_opp_ids.update(r['Id'] for r in recs)
print(f'Pulling existing notes for {len(all_opp_ids)} Opps...')

existing = {}
id_list_all = list(all_opp_ids)
for i in range(0, len(id_list_all), BATCH):
    batch = id_list_all[i:i+BATCH]
    ids = "','".join(batch)
    q = f"""
        SELECT LinkedEntityId, ContentDocument.Title, ContentDocument.LatestPublishedVersion.TextPreview
        FROM ContentDocumentLink
        WHERE LinkedEntityId IN ('{ids}')
          AND ContentDocument.FileType = 'SNOTE'
    """
    r = sf.query_all(q)
    for rec in r['records']:
        oid = rec['LinkedEntityId']
        existing.setdefault(oid, []).append({
            'title': rec['ContentDocument'].get('Title') or '',
            'preview': (rec['ContentDocument'].get('LatestPublishedVersion') or {}).get('TextPreview') or '',
        })

def norm(s):
    s = (s or '').lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def similarity(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()

def best_dup_score(text, notes):
    if not text:
        return 0.0, None
    best = 0.0
    best_match = None
    for n in notes:
        h = (n['title'] or '') + ' ' + (n['preview'] or '')
        s = similarity(text, h)
        if s > best:
            best = s
            best_match = n
    return best, best_match

analysis = []
for _, row in rows.iterrows():
    agree = row['Site Tracker Name']
    pname = row['Property Name']
    notes_text = row['Notes'] if pd.notna(row['Notes']) else ''
    actions_text = row['Action Items'] if pd.notna(row['Action Items']) else ''
    if not notes_text and not actions_text:
        continue
    # Pick opp
    hits = opp_by_agreement.get(agree, []) if agree else []
    if not hits and agree:
        hits = fallback.get(agree, [])
    if len(hits) == 1:
        opp_id = hits[0]['Id']
        opp_name = hits[0]['Name']
        match_method = 'agreement_name' if agree in opp_by_agreement else 'name_fallback'
    elif len(hits) > 1:
        # Prefer exact agreement match
        exact = [h for h in hits if h.get('Agreement_Name__c') == agree]
        if exact:
            opp_id = exact[0]['Id']
            opp_name = exact[0]['Name']
            match_method = 'agreement_name'
        else:
            opp_id = None
            opp_name = None
            match_method = f'ambiguous ({len(hits)} candidates)'
    else:
        opp_id = None
        opp_name = None
        match_method = 'unmatched'
    existing_notes = existing.get(opp_id, []) if opp_id else []
    n_score, n_match = best_dup_score(notes_text, existing_notes)
    a_score, a_match = best_dup_score(actions_text, existing_notes)
    analysis.append({
        'sheet': row['_sheet'],
        'property_name': pname,
        'site_tracker_name': agree,
        'state': row['Property State'] if pd.notna(row['Property State']) else None,
        'opp_id': opp_id,
        'opp_name': opp_name,
        'match_method': match_method,
        'notes': notes_text,
        'notes_dup_score': round(n_score, 2),
        'action_items': actions_text,
        'action_items_dup_score': round(a_score, 2),
        'existing_note_count': len(existing_notes),
    })

(OUT / 'mdu_updates_analysis.json').write_text(json.dumps(analysis, indent=2, default=str))

total = len(analysis)
matched = sum(1 for a in analysis if a['opp_id'])
unmatched = total - matched
# Consider "new content" = dup_score < 0.70 on that field (since field has real content)
new_notes = [a for a in analysis if a['opp_id'] and a['notes'] and a['notes_dup_score'] < 0.70]
new_actions = [a for a in analysis if a['opp_id'] and a['action_items'] and a['action_items_dup_score'] < 0.70]
dup_notes = [a for a in analysis if a['opp_id'] and a['notes'] and a['notes_dup_score'] >= 0.70]
dup_actions = [a for a in analysis if a['opp_id'] and a['action_items'] and a['action_items_dup_score'] >= 0.70]

print()
print('=== SUMMARY ===')
print(f'Total rows with content: {total}')
print(f'  matched to SF Opp: {matched}')
print(f'  unmatched: {unmatched}')
print()
print(f'Notes column:')
print(f'  fresh (NOT dup of existing): {len(new_notes)}')
print(f'  already captured (dup): {len(dup_notes)}')
print(f'  no note in row: {total - len(new_notes) - len(dup_notes) - unmatched}')
print()
print(f'Action Items column:')
print(f'  fresh (NOT dup of existing): {len(new_actions)}')
print(f'  already captured (dup): {len(dup_actions)}')
print()
print(f'Unmatched rows:')
for a in analysis:
    if not a['opp_id']:
        print(f"  [{a['sheet']}] {a['property_name']}  |  {a['site_tracker_name']}  ({a['state']})  | {a['match_method']}")
