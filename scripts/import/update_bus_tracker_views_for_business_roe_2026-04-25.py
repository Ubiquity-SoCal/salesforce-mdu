"""
Update all Business_Sales Tracker_View__c records' Config__c to filter
RecordTypeId IN [Business, Business_ROE] instead of equals Business only.

Makes the BUS Tracker show both Business Sales and Business ROE Opps.
Type column already exists in the configs so users can sort/distinguish.
"""
import sys, io, json, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
TS = datetime.now().isoformat(timespec='seconds')

# Get RT IDs
rts = {r['DeveloperName']: r['Id'] for r in sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SObjectType='Opportunity' AND IsActive=true")['records']}
BUSINESS_RT = rts['Business']
BUSINESS_ROE_RT = rts['Business_ROE']
print(f"  Business RT:     {BUSINESS_RT}")
print(f"  Business_ROE RT: {BUSINESS_ROE_RT}")

views = sf.query("SELECT Id, Name, Config__c FROM Tracker_View__c WHERE App_Context__c='Business_Sales'")['records']
print(f"\n  Found {len(views)} Business_Sales views")

updates = []
audit_rows = []
for v in views:
    cfg = json.loads(v.get('Config__c') or '{}')
    filters = cfg.get('filters', [])
    changed = False
    for f in filters:
        if f.get('field') == 'RecordTypeId' and f.get('operator') == 'equals' and f.get('value') == BUSINESS_RT:
            f['operator'] = 'in_list'
            f['value'] = [BUSINESS_RT, BUSINESS_ROE_RT]
            changed = True
    if changed:
        new_cfg = json.dumps(cfg)
        updates.append({'Id': v['Id'], 'Config__c': new_cfg})
        audit_rows.append({
            'SF_Id': v['Id'], 'Name': v['Name'], 'Field': 'Config__c',
            'Before': 'RecordTypeId equals Business', 'After': 'RecordTypeId in_list [Business, Business_ROE]',
            'Source': 'update_bus_tracker_views_for_business_roe_2026-04-25.py',
            'Timestamp': TS, 'Action': 'UPDATE',
            'Note': 'Expand BUS Tracker to show both Business Sales and Business ROE Opps',
        })
        print(f"  ✓ Will update: {v['Name']}")
    else:
        print(f"  - skip (no Business RT equals filter): {v['Name']}")

if not args.apply:
    print(f"\n[Preview only — {len(updates)} updates planned. Re-run with --apply.]")
    sys.exit(0)

print(f"\nApplying {len(updates)} view updates...")
results = sf.bulk.Tracker_View__c.update(updates)
errors = [(updates[i]['Id'], r) for i, r in enumerate(results) if not r.get('success')]
if errors:
    for eid, err in errors[:5]:
        print(f"  ⚠ {eid}: {err}")
print(f"  ✓ {len(updates) - len(errors)}/{len(updates)} updated")

audit_path = AUDIT_DIR / f'bus_tracker_views_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"  ✓ Audit log: {audit_path}")
