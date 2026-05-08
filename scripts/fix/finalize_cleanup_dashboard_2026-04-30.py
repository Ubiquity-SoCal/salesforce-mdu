"""Repoint MDU Cleanup Dashboard from broken clones (IuG... / `1` suffix) to fixed originals (Im...).
Then delete the 8 broken clones. Audit log everything."""
import argparse, csv, json, requests, sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.apply and not args.dry_run:
    print('Specify --dry-run or --apply'); sys.exit(1)

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
host = sf.sf_instance
hdrs = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

DASHBOARD_ID = '01ZWR000004LNk52AG'
# clone_id -> original_id (clones to delete after repoint)
CLONE_TO_ORIGINAL = {
    '00OWR00000IuGhF2AV': '00OWR00000ImYwH2AV',  # Under_Contract_No_PAL
    '00OWR00000IuGir2AF': '00OWR00000ImZE32AN',  # No_Projected_Close
    '00OWR00000IuGkT2AV': '00OWR00000ImZE52AN',  # Stale_Active_Opps
    '00OWR00000IuGm52AF': '00OWR00000ImZE22AN',  # Need_IC_ID_Signed
    '00OWR00000IuGnh2AF': '00OWR00000ImZE42AN',  # No_RE_Assigned
    '00OWR00000IuGqv2AF': '00OWR00000InCk12AF',  # Stale_EMA_Bulk
    '00OWR00000IuGu92AF': '00OWR00000ImZE12AN',  # Need_IC_ID_OutForSign
    '00OWR00000IuGxN2AV': '00OWR00000ImYRd2AN',  # No_Property_Location
}

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_path = Path('audit_logs') / f'finalize_cleanup_dashboard_{ts}.csv'
audit_path.parent.mkdir(exist_ok=True)

# 1. Pull current dashboard, repoint each component
print('Fetching dashboard...')
dash_url = f'https://{host}/services/data/v62.0/analytics/dashboards/{DASHBOARD_ID}'
dash = requests.get(dash_url + '/describe', headers=hdrs).json()
components = dash['components']
print(f'  {len(components)} components')

repoint_count = 0
for c in components:
    rid = c.get('reportId')
    if rid in CLONE_TO_ORIGINAL:
        new_id = CLONE_TO_ORIGINAL[rid]
        print(f'  Repoint: {rid} -> {new_id}')
        c['reportId'] = new_id
        repoint_count += 1
    else:
        print(f'  Keep:    {rid}')

if args.dry_run:
    print(f'\nDry run. Would repoint {repoint_count} components and delete {len(CLONE_TO_ORIGINAL)} clones.')
    sys.exit(0)

with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

    # 2. PATCH dashboard
    pr = requests.patch(dash_url, headers=hdrs, json=dash)
    print(f'\nDashboard PATCH: {pr.status_code}')
    if pr.status_code not in (200, 204):
        print(f'  ERR {pr.text[:500]}')
        sys.exit(2)
    w.writerow([DASHBOARD_ID, 'MDU Cleanup Dashboard', 'components.reportId',
                f'{repoint_count} clone refs', f'{repoint_count} original refs',
                'finalize_cleanup_dashboard_2026-04-30.py', ts, 'REPOINT'])

    # 3. Delete the clones (use Tooling API for hard delete)
    for clone_id, orig_id in CLONE_TO_ORIGINAL.items():
        del_url = f'https://{host}/services/data/v62.0/analytics/reports/{clone_id}'
        dr = requests.delete(del_url, headers=hdrs)
        print(f'  Delete clone {clone_id}: {dr.status_code}')
        action = 'DELETED' if dr.status_code in (200, 204) else f'DELETE_FAILED_{dr.status_code}'
        w.writerow([clone_id, 'broken clone', '(report)', clone_id, '(deleted)',
                    'finalize_cleanup_dashboard_2026-04-30.py', ts, action])

print(f'\nAudit log: {audit_path}')
print('\nNEXT: hard refresh the dashboard in Lightning UI to verify.')
