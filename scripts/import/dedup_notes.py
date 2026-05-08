"""Pull existing ContentNotes on matched Opps and flag likely duplicates of tracker notes."""
import json, re
from simple_salesforce import Salesforce
from pathlib import Path
from difflib import SequenceMatcher

OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
d = json.load(open(OUT / 'match_results.json'))

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

all_matched = d['matched_by_project_id'] + d['matched_by_name']
# Exclude the suspicious state-mismatch auto-match
all_matched = [r for r in all_matched if r['site_name'] != 'Bridgeport_MDU_Dry Creek HOA']

# Only rows with actual notes
with_notes = [r for r in all_matched if r.get('notes')]
print(f'{len(with_notes)} matched rows have notes to import, {len(all_matched) - len(with_notes)} rows matched but empty notes')

opp_ids = list({r['opp_id'] for r in with_notes})
print(f'Querying existing ContentNotes on {len(opp_ids)} Opps...')

# Batch the IN clause
existing = {}  # opp_id -> [note bodies]
BATCH = 100
for i in range(0, len(opp_ids), BATCH):
    batch = opp_ids[i:i+BATCH]
    ids = "','".join(batch)
    q = f"""
        SELECT LinkedEntityId, ContentDocument.LatestPublishedVersion.TextPreview, ContentDocument.Title, ContentDocument.CreatedDate
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
            'created': rec['ContentDocument'].get('CreatedDate'),
        })

def norm(s):
    s = (s or '').lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def similar(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()

plan = {'import': [], 'skip_dup': []}
for r in with_notes:
    tracker_note = r['notes']
    oid = r['opp_id']
    ex = existing.get(oid, [])
    best_score = 0.0
    best_match = None
    for e in ex:
        haystack = (e['title'] or '') + ' ' + (e['preview'] or '')
        score = similar(tracker_note, haystack)
        if score > best_score:
            best_score = score
            best_match = e
    rec = {
        'opp_id': oid,
        'opp_name': r['opp_name'],
        'site_name': r['site_name'],
        'state': r['state'],
        'owner_tracker': r.get('owner_tracker'),
        'status': r['status'],
        'notes': tracker_note,
        'project_id': r.get('project_id'),
        'existing_note_count': len(ex),
        'best_dup_score': round(best_score, 2),
        'best_dup_preview': (best_match['preview'][:120] if best_match else None),
    }
    if best_score >= 0.70:
        plan['skip_dup'].append(rec)
    else:
        plan['import'].append(rec)

(OUT / 'import_plan.json').write_text(json.dumps(plan, indent=2, default=str))

print(f'\nPlan:')
print(f'  to import: {len(plan["import"])}')
print(f'  skip as likely dup: {len(plan["skip_dup"])}')
print(f'\n  Samples of skip-as-dup:')
for r in plan['skip_dup'][:5]:
    print(f"    [{r['best_dup_score']}] {r['opp_name']}")
    print(f"       tracker: {r['notes'][:100]}")
    print(f"       existing: {r['best_dup_preview']}")
