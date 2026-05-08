"""Execute the approved import: CloseDate updates + 41 ContentNotes."""
import json, base64, time
from pathlib import Path
from simple_salesforce import Salesforce

OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
plan = json.load(open(OUT / 'final_plan.json'))

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

log = {'close_date_updates': [], 'notes_created': [], 'errors': []}

print(f'Updating CloseDate on {len(plan["date_updates"])} Opps...')
for p in plan['date_updates']:
    try:
        sf.Opportunity.update(p['opp_id'], {'CloseDate': p['target_close_date']})
        log['close_date_updates'].append({'opp_id': p['opp_id'], 'opp_name': p['opp_name'],
                                          'old': p.get('current_close_date'), 'new': p['target_close_date']})
        print(f"  OK  {p['opp_name']}: {p.get('current_close_date')} -> {p['target_close_date']}")
    except Exception as e:
        log['errors'].append({'op': 'close_date', 'opp_id': p['opp_id'], 'error': str(e)})
        print(f"  ERR {p['opp_name']}: {e}")

print(f'\nCreating {len(plan["note_imports"])} ContentNotes...')
for p in plan['note_imports']:
    title = f"Weekly Tracker - 2026-04-24"
    owner = p.get('owner_tracker') or '(unassigned)'
    status = p.get('status') or ''
    notes = p.get('notes') or ''
    body = f"Status: {status}\nOwner (tracker): {owner}\n\n{notes}"
    content_b64 = base64.b64encode(body.encode('utf-8')).decode('utf-8')
    try:
        note = sf.ContentNote.create({'Title': title, 'Content': content_b64})
        note_id = note['id']
        sf.ContentDocumentLink.create({
            'ContentDocumentId': note_id,
            'LinkedEntityId': p['opp_id'],
            'ShareType': 'V',
            'Visibility': 'AllUsers',
        })
        log['notes_created'].append({'opp_id': p['opp_id'], 'opp_name': p['opp_name'], 'note_id': note_id})
        print(f"  OK  {p['opp_name']}")
    except Exception as e:
        log['errors'].append({'op': 'note', 'opp_id': p['opp_id'], 'error': str(e)})
        print(f"  ERR {p['opp_name']}: {e}")
    time.sleep(0.15)

(OUT / 'execution_log.json').write_text(json.dumps(log, indent=2, default=str))
print(f"\nDone. dates={len(log['close_date_updates'])}  notes={len(log['notes_created'])}  errors={len(log['errors'])}")
