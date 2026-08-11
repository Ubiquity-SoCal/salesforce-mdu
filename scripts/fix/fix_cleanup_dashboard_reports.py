"""
Fix the MDU Cleanup Dashboard reports after the 4/29 stage restructure.
Each report has STAGE_NAME filters referencing dead picklist values
(ROE Secured, Under Contract, EMA/Bulk Completed) which causes the
Lightning report runner to throw "Cannot read properties of undefined (reading 'label')".

Patches each report's metadata via the Analytics REST API.
Logs Before/After to audit_logs/.
"""
import argparse, csv, json, sys, requests
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.apply and not args.dry_run:
    print('Specify --dry-run or --apply'); sys.exit(1)

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
host = sf.sf_instance
hdrs = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

# Active pipeline stages post 4/29 restructure
ACTIVE_BEYOND_PROSPECTING = 'Engaged,Proposal Sent,Contract Negotiations,PAL/ROE Complete'
ACTIVE_INCL_BULK = 'Engaged,Proposal Sent,Contract Negotiations,PAL/ROE Complete,EMA/Bulk In Progress'
COMPLETED_PIPELINE = 'PAL/ROE Complete,EMA/Bulk In Progress,EMA/Bulk Complete'

# Per-report patches: reportId -> dict of changes to reportMetadata
PATCHES = {
    '00OWR00000ImYwH2AV': {
        'name': 'Cleanup: PAL/ROE Complete: No PAL',  # rename, must be <=40 chars
        'stage_filter_replacement': 'PAL/ROE Complete',
    },
    '00OWR00000ImZE42AN': {
        'name': None,
        'stage_filter_replacement': ACTIVE_BEYOND_PROSPECTING,
    },
    '00OWR00000ImYRd2AN': {
        'name': None,
        'stage_filter_replacement': ACTIVE_INCL_BULK,
    },
    '00OWR00000ImZE32AN': {
        'name': None,
        'stage_filter_replacement': ACTIVE_BEYOND_PROSPECTING,
    },
    '00OWR00000ImZE52AN': {
        'name': None,
        'stage_filter_replacement': ACTIVE_INCL_BULK,
    },
    '00OWR00000InCk12AF': {
        'name': None,
        'stage_filter_replacement': COMPLETED_PIPELINE,  # operator stays notEqual
    },
}

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'cleanup_dashboard_report_fix_{ts}.csv'

success = 0
failed = []
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Report_Id', 'Report_Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

    for rid, patch in PATCHES.items():
        url = f'https://{host}/services/data/v59.0/analytics/reports/{rid}/describe'
        r = requests.get(url, headers=hdrs)
        if r.status_code != 200:
            failed.append((rid, f'GET describe {r.status_code}'))
            continue
        body = r.json()
        meta = body['reportMetadata']
        old_name = meta.get('name')
        old_filters = json.dumps(meta.get('reportFilters'))

        # Patch name if requested
        if patch.get('name'):
            meta['name'] = patch['name']

        # Find STAGE_NAME filter and patch its value
        stage_filter_changed = False
        for f_obj in meta.get('reportFilters', []):
            if f_obj.get('column') == 'STAGE_NAME':
                old_val = f_obj.get('value')
                f_obj['value'] = patch['stage_filter_replacement']
                stage_filter_changed = True
                if args.apply:
                    w.writerow([rid, old_name, 'StageName filter value', old_val, patch['stage_filter_replacement'],
                                'fix_cleanup_dashboard_reports.py', ts, 'PATCH'])
                else:
                    print(f"  [{rid}] {old_name}")
                    print(f"    StageName filter:  '{old_val}' -> '{patch['stage_filter_replacement']}'")
                    if patch.get('name'):
                        print(f"    Name:              '{old_name}' -> '{patch['name']}'")

        if not stage_filter_changed:
            print(f"  ! [{rid}] {old_name}: no STAGE_NAME filter found, skipping")
            continue

        if args.dry_run:
            continue

        # PATCH report
        patch_url = f'https://{host}/services/data/v59.0/analytics/reports/{rid}'
        payload = {'reportMetadata': meta}
        pr = requests.patch(patch_url, headers=hdrs, json=payload)
        if pr.status_code in (200, 201, 204):
            print(f"  + Updated [{rid}] {meta['name']}")
            if patch.get('name'):
                w.writerow([rid, old_name, 'Name', old_name, patch['name'],
                            'fix_cleanup_dashboard_reports.py', ts, 'PATCH'])
            success += 1
        else:
            failed.append((rid, f'PATCH {pr.status_code}: {pr.text[:200]}'))
            print(f"  FAIL [{rid}] {pr.status_code}: {pr.text[:200]}")

if args.dry_run:
    print(f"\nDry run. Re-run with --apply to execute.")
else:
    print(f"\nUpdated: {success}")
    print(f"Failed: {len(failed)}")
    print(f"Audit log: {audit_path}")
    for f in failed:
        print(f"  FAIL {f}")
