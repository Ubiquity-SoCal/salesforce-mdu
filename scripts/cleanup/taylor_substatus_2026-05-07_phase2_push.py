"""Push Taylor's Substatus + Sales_Status values from xlsx into SF.

Reads phase1_resolved_targets.json and applies the updates with a per-row audit CSV.
Idempotent: skips Opps where SF already has the target value (e.g., from re-runs).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


AUDIT_DIR = r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\2026-05-07_taylor_substatus_push'
TARGETS = os.path.join(AUDIT_DIR, 'phase1_resolved_targets.json')
SOURCE_TAG = 'TM_review_2026-05-04'

def confirm(prompt):
    print(f'\n{prompt}')
    print('Type exactly "yes" to proceed:')
    return input('> ').strip() == 'yes'

def now_iso():
    return datetime.now().isoformat()

if not os.path.exists(TARGETS):
    print(f'ERROR: {TARGETS} not found. Run Phase 1 first.')
    sys.exit(1)

with open(TARGETS, encoding='utf-8') as f:
    plan = json.load(f)

substatus = plan['substatus_pushes']
sales_status = plan['sales_status_pushes']

print(f'Loaded plan generated at {plan["generated_at"]}')
print(f'  Substatus pushes:    {len(substatus)}')
print(f'  Sales_Status pushes: {len(sales_status)}')

# Re-read current SF state for idempotency before pushing
print('\nConnecting to Salesforce...')
sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

all_ids = list({p['Id'] for p in substatus + sales_status})
ids_str = "','".join(all_ids)
current_state = {}
chunk = 200
for i in range(0, len(all_ids), chunk):
    batch = all_ids[i:i+chunk]
    bstr = "','".join(batch)
    rs = sf.query_all(f"""
        SELECT Id, StageName, Substatus__c, Sales_Status__c
        FROM Opportunity WHERE Id IN ('{bstr}')
    """)['records']
    for r in rs:
        current_state[r['Id']] = r

# Filter to actual deltas
todo_substatus = [p for p in substatus if current_state.get(p['Id'], {}).get('Substatus__c') != p['mapped_value']]
todo_sales = [p for p in sales_status if current_state.get(p['Id'], {}).get('Sales_Status__c') != p['value']]
skipped = len(substatus) - len(todo_substatus) + len(sales_status) - len(todo_sales)

print(f'\nIdempotency check vs current SF state:')
print(f'  Substatus to update:    {len(todo_substatus)} (skipping {len(substatus) - len(todo_substatus)} already set)')
print(f'  Sales_Status to update: {len(todo_sales)} (skipping {len(sales_status) - len(todo_sales)} already set)')

if not (todo_substatus or todo_sales):
    print('\nNothing to do.')
    sys.exit(0)

if not confirm(f'Push {len(todo_substatus)} Substatus + {len(todo_sales)} Sales_Status updates.  Proceed?'):
    print('Aborted.')
    sys.exit(0)

ts_str = datetime.now().strftime('%Y%m%dT%H%M%S')
audit_path = os.path.join(AUDIT_DIR, f'phase2_push_{ts_str}.csv')
with open(audit_path, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=[
        'SF_Id', 'Name', 'Object', 'Field', 'Before', 'After',
        'Source', 'Action', 'Result', 'Error', 'Timestamp',
    ])
    w.writeheader()
    print(f'Audit -> {audit_path}\n')

    for p in todo_substatus:
        oid = p['Id']
        before = current_state.get(oid, {}).get('Substatus__c') or ''
        after = p['mapped_value']
        try:
            sf.Opportunity.update(oid, {'Substatus__c': after})
            w.writerow({
                'SF_Id': oid, 'Name': p['Name'], 'Object': 'Opportunity',
                'Field': 'Substatus__c', 'Before': before, 'After': after,
                'Source': SOURCE_TAG, 'Action': 'Update',
                'Result': 'OK', 'Error': '', 'Timestamp': now_iso(),
            })
            print(f'  {p["Name"]} [{p["StageName"]}]: Substatus -> {after}')
        except Exception as e:
            w.writerow({
                'SF_Id': oid, 'Name': p['Name'], 'Object': 'Opportunity',
                'Field': 'Substatus__c', 'Before': before, 'After': after,
                'Source': SOURCE_TAG, 'Action': 'Update',
                'Result': 'FAIL', 'Error': str(e), 'Timestamp': now_iso(),
            })
            print(f'  FAIL {p["Name"]}: {e}')

    for p in todo_sales:
        oid = p['Id']
        before = current_state.get(oid, {}).get('Sales_Status__c') or ''
        after = p['value']
        try:
            sf.Opportunity.update(oid, {'Sales_Status__c': after})
            w.writerow({
                'SF_Id': oid, 'Name': p['Name'], 'Object': 'Opportunity',
                'Field': 'Sales_Status__c', 'Before': before, 'After': after,
                'Source': SOURCE_TAG, 'Action': 'Update',
                'Result': 'OK', 'Error': '', 'Timestamp': now_iso(),
            })
            print(f'  {p["Name"]} [{p["StageName"]}]: Sales_Status -> {after}')
        except Exception as e:
            w.writerow({
                'SF_Id': oid, 'Name': p['Name'], 'Object': 'Opportunity',
                'Field': 'Sales_Status__c', 'Before': before, 'After': after,
                'Source': SOURCE_TAG, 'Action': 'Update',
                'Result': 'FAIL', 'Error': str(e), 'Timestamp': now_iso(),
            })
            print(f'  FAIL {p["Name"]}: {e}')

print('\nDone.')
