"""
Rebuild the MDU Cleanup Dashboard reports by cloning each broken report,
repointing the dashboard at the clones, then deleting the broken originals.
The originals had corrupted internal metadata after the 4/29 stage restructure
which caused Lightning to throw 'Cannot read properties of undefined (reading 'label')'.

Usage:
  python rebuild_cleanup_dashboard_reports.py --dry-run
  python rebuild_cleanup_dashboard_reports.py --apply
"""
import argparse, csv, json, sys, requests
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

# Pull dashboard
dash_url = f'https://{host}/services/data/v59.0/analytics/dashboards/{DASHBOARD_ID}'
dash = requests.get(dash_url + '/describe', headers=hdrs).json()
components = dash['components']
print(f'Dashboard has {len(components)} components')

# For each unique report on the dashboard, clone it
old_to_new = {}  # old_report_id -> new_report_id
seen_old_ids = list({c['reportId'] for c in components})
print(f'Unique broken reports to clone: {len(seen_old_ids)}\n')

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'rebuild_cleanup_reports_{ts}.csv'

if args.dry_run:
    print('Would clone:')
    for old_id in seen_old_ids:
        meta_r = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{old_id}/describe', headers=hdrs).json()
        print(f"  {old_id}  {meta_r['reportMetadata']['name']}")
    print('Would update dashboard reference for each component then delete old reports.')
    sys.exit(0)

# 1. Clone each report
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Old_Report_Id', 'New_Report_Id', 'Report_Name', 'Action', 'Source', 'Timestamp'])

    for old_id in seen_old_ids:
        # Get original name + developerName
        meta_r = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{old_id}/describe', headers=hdrs).json()
        orig_name = meta_r['reportMetadata']['name']
        orig_devname = meta_r['reportMetadata']['developerName']

        # Clone with a temp name (we'll rename after deleting original)
        clone_url = f'https://{host}/services/data/v59.0/analytics/reports?cloneId={old_id}'
        clone_payload = {'reportMetadata': {'name': f'{orig_name[:35]} NEW'[:40]}}
        cr = requests.post(clone_url, headers=hdrs, json=clone_payload)
        if cr.status_code not in (200, 201):
            print(f'  FAIL clone {old_id}: {cr.status_code} {cr.text[:200]}')
            continue
        new_id = cr.json()['reportMetadata']['id']
        print(f'  Cloned [{old_id}] -> [{new_id}]  "{orig_name}"')
        old_to_new[old_id] = (new_id, orig_name, orig_devname)
        w.writerow([old_id, new_id, orig_name, 'CLONED', 'rebuild_cleanup_dashboard_reports.py', ts])

    # 2. Update dashboard components to point to clones
    new_components = []
    for c in components:
        old_id = c['reportId']
        if old_id in old_to_new:
            new_id, _, _ = old_to_new[old_id]
            c['reportId'] = new_id
        new_components.append(c)
    dash['components'] = new_components

    update_url = f'https://{host}/services/data/v59.0/analytics/dashboards/{DASHBOARD_ID}'
    ur = requests.patch(update_url, headers=hdrs, json=dash)
    if ur.status_code in (200, 201, 204):
        print(f'\n  Dashboard repointed to clones.')
        w.writerow([DASHBOARD_ID, '', 'MDU Cleanup Dashboard', 'DASHBOARD_REPOINTED', 'rebuild_cleanup_dashboard_reports.py', ts])
    else:
        print(f'\n  FAIL dashboard update: {ur.status_code} {ur.text[:300]}')
        print('  Stopping. Cloned reports remain but dashboard not updated. Manual cleanup may be needed.')
        sys.exit(2)

    # 3. Delete old reports
    for old_id, (new_id, orig_name, orig_devname) in old_to_new.items():
        del_url = f'https://{host}/services/data/v59.0/analytics/reports/{old_id}'
        dr = requests.delete(del_url, headers=hdrs)
        if dr.status_code in (200, 204):
            print(f'  Deleted old report [{old_id}]')
            w.writerow([old_id, '', orig_name, 'DELETED', 'rebuild_cleanup_dashboard_reports.py', ts])
        else:
            print(f'  FAIL delete [{old_id}]: {dr.status_code}')

    # 4. Rename clones back to original names (now that originals are gone)
    for old_id, (new_id, orig_name, orig_devname) in old_to_new.items():
        rename_url = f'https://{host}/services/data/v59.0/analytics/reports/{new_id}'
        # Get current metadata so we can patch with name only
        meta_r = requests.get(rename_url + '/describe', headers=hdrs).json()
        new_meta = meta_r['reportMetadata']
        new_meta['name'] = orig_name
        # Try to set developerName to the original (may not be allowed)
        new_meta['developerName'] = orig_devname
        rr = requests.patch(rename_url, headers=hdrs, json={'reportMetadata': new_meta})
        if rr.status_code in (200, 201, 204):
            print(f'  Renamed clone [{new_id}] -> "{orig_name}"')
            w.writerow([new_id, '', orig_name, 'RENAMED', 'rebuild_cleanup_dashboard_reports.py', ts])
        else:
            print(f'  WARN rename [{new_id}]: {rr.status_code} {rr.text[:200]}')

print(f'\nAudit log: {audit_path}')
