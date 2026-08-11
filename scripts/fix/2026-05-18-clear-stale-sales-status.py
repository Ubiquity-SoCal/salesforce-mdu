"""Clear stale Sales_Status__c on Opps where StageName is outside the field's intended scope.

Per Sales_Status__c field description: "Use during Prospects, Prospecting, and Engaged stages."
Values that persist after stage advance are stale leftovers. This script nulls them out
across both MDU and Business ROE record types in one pass.

Snapshot lives at:
  SalesForce/data/output/audit_logs/2026-05-18-clear-stale-sales-status-snapshot.csv
Audit log written to:
  SalesForce/data/output/audit_logs/2026-05-18-clear-stale-sales-status.csv
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ALLOWED_STAGES = ('Prospects', 'Prospecting', 'Engaged')
AUDIT_DIR = r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs'
AUDIT_PATH = os.path.join(AUDIT_DIR, '2026-05-18-clear-stale-sales-status.csv')
SOURCE_TAG = 'sales-status-scope-enforcement-2026-05-18'


def confirm(prompt):
    print(f'\n{prompt}')
    print('Type exactly "yes" to proceed:')
    return input('> ').strip() == 'yes'


def now_iso():
    return datetime.now().isoformat()


print('Connecting to Salesforce...')
sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

stages_filter = "','".join(ALLOWED_STAGES)
records = sf.query_all(f"""
    SELECT Id, Name, StageName, Sales_Status__c, RecordType.Name
    FROM Opportunity
    WHERE Sales_Status__c != null
      AND StageName NOT IN ('{stages_filter}')
    ORDER BY StageName, Name
""")['records']

print(f'\nFound {len(records)} Opps with stale Sales_Status__c (outside {ALLOWED_STAGES}).')
by_stage = {}
for r in records:
    by_stage.setdefault(r['StageName'], 0)
    by_stage[r['StageName']] += 1
for stage, n in sorted(by_stage.items(), key=lambda x: -x[1]):
    print(f'  {stage}: {n}')

if not records:
    print('\nNothing to do.')
    sys.exit(0)

if not confirm(f'Clear Sales_Status__c on {len(records)} Opps?'):
    print('Aborted.')
    sys.exit(0)

os.makedirs(AUDIT_DIR, exist_ok=True)
with open(AUDIT_PATH, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=[
        'SF_Id', 'Name', 'Object', 'Field', 'Before', 'After',
        'Source', 'Action', 'Result', 'Error', 'Timestamp',
    ])
    w.writeheader()
    print(f'Audit -> {AUDIT_PATH}\n')

    for r in records:
        oid = r['Id']
        before = r.get('Sales_Status__c') or ''
        try:
            sf.Opportunity.update(oid, {'Sales_Status__c': None})
            w.writerow({
                'SF_Id': oid, 'Name': r['Name'], 'Object': 'Opportunity',
                'Field': 'Sales_Status__c', 'Before': before, 'After': '',
                'Source': SOURCE_TAG, 'Action': 'Clear',
                'Result': 'OK', 'Error': '', 'Timestamp': now_iso(),
            })
            print(f'  {r["Name"]} [{r["StageName"]}]: {before!r} -> cleared')
        except Exception as e:
            w.writerow({
                'SF_Id': oid, 'Name': r['Name'], 'Object': 'Opportunity',
                'Field': 'Sales_Status__c', 'Before': before, 'After': '',
                'Source': SOURCE_TAG, 'Action': 'Clear',
                'Result': 'FAIL', 'Error': str(e), 'Timestamp': now_iso(),
            })
            print(f'  FAIL {r["Name"]}: {e}')

print('\nDone.')
