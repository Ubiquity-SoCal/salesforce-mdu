"""
Change the Business ROE row-highlight rule to a cell-only highlight on the
RecordType.Name (Type) column. Subtle and contained to just that cell.
"""
import sys, io, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

views = sf.query("SELECT Id, Name, Config__c FROM Tracker_View__c WHERE App_Context__c='Business_Sales'")['records']
print(f"Found {len(views)} Business_Sales views")

updates = []
for v in views:
    cfg = json.loads(v.get('Config__c') or '{}')
    rules = cfg.get('formatting_rules', [])
    changed = False
    for r in rules:
        if r.get('field') == 'RecordType.Name' and r.get('value') == 'Business ROE':
            if r.get('target') != 'cell':
                r['target'] = 'cell'
                changed = True
    if changed:
        cfg['formatting_rules'] = rules
        updates.append({'Id': v['Id'], 'Config__c': json.dumps(cfg)})
        print(f"  ✓ Will switch to cell-only: {v['Name']}")
    else:
        print(f"  - already cell or no rule: {v['Name']}")

if not args.apply:
    print(f"\n[Preview only — {len(updates)} updates planned]")
    sys.exit(0)

results = sf.bulk.Tracker_View__c.update(updates)
errors = [(updates[i]['Id'], r) for i, r in enumerate(results) if not r.get('success')]
print(f"\n  ✓ {len(updates) - len(errors)}/{len(updates)} updated")
