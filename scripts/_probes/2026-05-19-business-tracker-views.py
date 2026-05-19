"""Show all Tracker_View__c records on the Business Sales app and dump their column configs."""
import os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

# Pull all active views to understand the layout
q = ("SELECT Id, Name, App_Context__c, Object__c, Is_Active__c, Sort_Order__c, Config__c "
     "FROM Tracker_View__c WHERE Is_Active__c = true "
     "ORDER BY App_Context__c, Sort_Order__c, Name")
views = sf.query_all(q)['records']
print(f'Found {len(views)} active Tracker_View__c records.\n')

# Group by App_Context__c
by_app = {}
for v in views:
    by_app.setdefault(v.get('App_Context__c') or '(blank)', []).append(v)

for app, vs in by_app.items():
    print(f'=== App_Context__c: {app!r}  ({len(vs)} views) ===')
    for v in vs:
        print(f"  [{v['Sort_Order__c']}]  {v['Name']}  (Obj={v['Object__c']}, Id={v['Id']})")
        try:
            cfg = json.loads(v['Config__c'])
            cols = cfg.get('columns', [])
            print(f"    Columns ({len(cols)}):")
            for c in cols:
                lbl = c.get('label') or c.get('field')
                ed = '  [editable]' if c.get('editable') else ''
                print(f"      - {c.get('field')}  ({lbl}){ed}")
            filt = cfg.get('filters', [])
            if filt:
                print(f"    Filters: {filt}")
        except Exception as e:
            print(f"    Config parse failed: {e}")
        print()
