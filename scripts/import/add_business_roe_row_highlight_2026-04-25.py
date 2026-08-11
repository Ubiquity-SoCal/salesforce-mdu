"""
Add a subtle row-highlight formatting rule to all Business_Sales Tracker_View__c
records. When RecordType.Name = "Business ROE", row gets a light background so
the team can distinguish Business ROE pursuits from Business Sales at a glance.
"""
import sys, io, json, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
TS = datetime.now().isoformat(timespec='seconds')

NEW_RULE = {
    'field': 'RecordType.Name',
    'operator': 'equals',
    'value': 'Business ROE',
    'style': 'background:#e3f2fd',  # subtle light blue
    'target': 'row',
}

views = sf.query("SELECT Id, Name, Config__c FROM Tracker_View__c WHERE App_Context__c='Business_Sales'")['records']
print(f"Found {len(views)} Business_Sales views")

updates = []
audit_rows = []
for v in views:
    cfg = json.loads(v.get('Config__c') or '{}')
    rules = cfg.get('formatting_rules', [])
    # Idempotency: skip if rule already present
    has_rule = any(
        r.get('field') == NEW_RULE['field']
        and r.get('value') == NEW_RULE['value']
        and r.get('target') == 'row'
        for r in rules
    )
    if has_rule:
        print(f"  - skip (rule already present): {v['Name']}")
        continue
    rules.append(NEW_RULE)
    cfg['formatting_rules'] = rules
    new_cfg = json.dumps(cfg)
    updates.append({'Id': v['Id'], 'Config__c': new_cfg})
    audit_rows.append({
        'SF_Id': v['Id'], 'Name': v['Name'], 'Field': 'Config__c.formatting_rules',
        'Before': '(no row rule for Business ROE)', 'After': json.dumps(NEW_RULE),
        'Source': 'add_business_roe_row_highlight_2026-04-25.py',
        'Timestamp': TS, 'Action': 'UPDATE',
        'Note': 'Subtle row highlight (light blue) for Business ROE Opps in BUS Tracker',
    })
    print(f"  ✓ Will add highlight rule: {v['Name']}")

if not args.apply:
    print(f"\n[Preview only — {len(updates)} updates planned. Re-run with --apply.]")
    sys.exit(0)

print(f"\nApplying {len(updates)} updates...")
results = sf.bulk.Tracker_View__c.update(updates)
errors = [(updates[i]['Id'], r) for i, r in enumerate(results) if not r.get('success')]
if errors:
    for eid, err in errors[:5]:
        print(f"  ⚠ {eid}: {err}")
print(f"  ✓ {len(updates) - len(errors)}/{len(updates)} updated")

audit_path = AUDIT_DIR / f'bus_tracker_row_highlight_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"  ✓ Audit log: {audit_path}")
