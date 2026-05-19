"""Add Units__c column to the 9 Business tracker views.

Business ROE Opps (291 of 489 Business app Opps, 89% Units__c populated) are
building-wide pursuits and need a units column. Business Opps (per-tenant) will
show blank in this column, which is correct -- units don't apply to a single
tenant pursuit.

Column placement: right after Property_Unit__r.Unit__c (Unit #) -- the suite
identifier and the building unit count read naturally next to each other.

Snapshot each Tracker_View__c.Config__c before edit so a rollback is one-step.
"""
import os, sys, io, csv, json, copy
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

SCRIPT = '2026-05-19-business-tracker-add-units.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT = Path(r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs') / \
        '2026-05-19-business-tracker-add-units.csv'
AUDIT.parent.mkdir(parents=True, exist_ok=True)
audit_rows = []

NEW_COL = {
    'field': 'Units__c',
    'label': 'Units',
    'editable': True,
}
INSERT_AFTER = 'Property_Unit__r.Unit__c'   # the existing 'Unit #' column

views = sf.query_all(
    "SELECT Id, Name, Config__c FROM Tracker_View__c "
    "WHERE App_Context__c = 'Business_Sales' AND Is_Active__c = true "
    "ORDER BY Sort_Order__c"
)['records']
print(f'Updating {len(views)} Business tracker views...\n')

for v in views:
    cfg = json.loads(v['Config__c'])
    cols = cfg.get('columns', [])

    # Skip if already present (idempotent)
    if any(c.get('field') == 'Units__c' for c in cols):
        print(f"  [{v['Name']}] already has Units__c -- skipping")
        continue

    # Find insert position
    idx = next((i for i, c in enumerate(cols) if c.get('field') == INSERT_AFTER), None)
    if idx is None:
        print(f"  [{v['Name']}] anchor column {INSERT_AFTER!r} not found -- skipping")
        continue

    before_cfg = v['Config__c']
    new_cols = cols[:idx + 1] + [NEW_COL] + cols[idx + 1:]
    cfg['columns'] = new_cols
    after_cfg = json.dumps(cfg)

    sf.Tracker_View__c.update(v['Id'], {'Config__c': after_cfg})

    print(f"  [{v['Name']}] inserted Units__c after position {idx} ({INSERT_AFTER})")
    audit_rows.append({
        'SF_Id': v['Id'],
        'Name': v['Name'],
        'Field': 'Config__c',
        'Before': before_cfg,
        'After': after_cfg,
        'Source': SCRIPT,
        'Timestamp': TS,
        'Action': 'UPDATE',
        'Note': 'Added Units__c column after Property_Unit__r.Unit__c for Business ROE building-wide unit count',
    })

with AUDIT.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before', 'After',
                                       'Source', 'Timestamp', 'Action', 'Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f'\nAudit log: {AUDIT} ({len(audit_rows)} rows)')
