"""Revert CloseDate changes and re-apply to Projected_Close_Date__c instead."""
import json
from pathlib import Path
from simple_salesforce import Salesforce

OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
log = json.load(open(OUT / 'execution_log.json'))

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

print('Step 1: reverting CloseDate changes...')
for u in log['close_date_updates']:
    try:
        sf.Opportunity.update(u['opp_id'], {'CloseDate': u['old']})
        print(f"  revert {u['opp_name']}: CloseDate back to {u['old']}")
    except Exception as e:
        print(f"  ERR revert {u['opp_name']}: {e}")

print('\nStep 2: reading current Projected_Close_Date__c values...')
ids = [u['opp_id'] for u in log['close_date_updates']]
id_list = "','".join(ids)
q = f"SELECT Id, Name, Projected_Close_Date__c FROM Opportunity WHERE Id IN ('{id_list}')"
res = sf.query_all(q)
current = {r['Id']: r for r in res['records']}

print('\nStep 3: applying Projected_Close_Date__c updates...')
new_log = []
for u in log['close_date_updates']:
    cur = current.get(u['opp_id'])
    cur_proj = cur.get('Projected_Close_Date__c') if cur else None
    new_val = u['new']
    if cur_proj == new_val:
        print(f"  skip {u['opp_name']}: already {new_val}")
        continue
    try:
        sf.Opportunity.update(u['opp_id'], {'Projected_Close_Date__c': new_val})
        new_log.append({'opp_id': u['opp_id'], 'opp_name': u['opp_name'], 'field': 'Projected_Close_Date__c', 'old': cur_proj, 'new': new_val})
        print(f"  OK  {u['opp_name']}: Projected_Close_Date__c {cur_proj} -> {new_val}")
    except Exception as e:
        print(f"  ERR {u['opp_name']}: {e}")

log['projected_close_date_updates'] = new_log
log['close_date_reverted'] = True
(OUT / 'execution_log.json').write_text(json.dumps(log, indent=2, default=str))
print(f"\nDone. Reverted {len(log['close_date_updates'])} CloseDate values, applied {len(new_log)} Projected_Close_Date__c updates.")
