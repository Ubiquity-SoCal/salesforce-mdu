"""Follow-up sweep: reassign Owner to RE_Assigned for TERMINAL stages
(Closed Lost, EMA/Bulk Complete) that we excluded from the active-stage sweep.

Same logic as reassign_owner_to_re_2026-04-30.py, just inverted stage filter.
PAL+ROE caveat still applies.

Usage:
  python reassign_owner_to_re_terminal_2026-04-30.py --dry-run
  python reassign_owner_to_re_terminal_2026-04-30.py --apply
"""
import argparse, csv, sys
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

q = """
SELECT Id, Name, OwnerId, Owner.Name, RE_Assigned__c, RE_Assigned__r.Name, RE_Assigned__r.IsActive,
       RecordType.DeveloperName, StageName,
       (SELECT Agreement_Type__c FROM Agreements__r)
FROM Opportunity
WHERE RecordType.DeveloperName IN ('MDU','Business_ROE')
  AND RE_Assigned__c != null
  AND StageName IN ('Closed Lost','EMA/Bulk Complete')
"""
records = sf.query_all(q)['records']

def types_for(r):
    sub = r.get('Agreements__r')
    ags = sub.get('records', []) if sub else []
    return set(a.get('Agreement_Type__c') for a in ags if a.get('Agreement_Type__c'))

planned, skipped_pal_roe = [], []
for r in records:
    if r['OwnerId'] == r['RE_Assigned__c']:
        continue
    if not (r.get('RE_Assigned__r') or {}).get('IsActive'):
        continue
    t = types_for(r)
    if 'PAL' in t and 'ROE' in t:
        skipped_pal_roe.append(r)
        continue
    planned.append(r)

print(f'Total terminal-stage candidates: {len(records)}')
print(f'  Skipped (Owner=RE or RE inactive): {len(records) - len(planned) - len(skipped_pal_roe)}')
print(f'  Skipped (has both PAL and ROE): {len(skipped_pal_roe)}')
print(f'  Planned reassignments: {len(planned)}')

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'reassign_owner_to_re_terminal_{ts}.csv'

with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action',
                'RecordType', 'StageName', 'OldOwnerName', 'NewOwnerName', 'AgreementTypes'])
    for r in planned:
        w.writerow([r['Id'], r['Name'], 'OwnerId', r['OwnerId'], r['RE_Assigned__c'],
                    'reassign_owner_to_re_terminal_2026-04-30.py', ts,
                    'PLANNED' if args.dry_run else 'APPLIED',
                    (r.get('RecordType') or {}).get('DeveloperName'),
                    r['StageName'],
                    (r.get('Owner') or {}).get('Name'),
                    (r.get('RE_Assigned__r') or {}).get('Name'),
                    ','.join(sorted(types_for(r))) or '(none)'])
print(f'\nAudit log: {audit_path}')

if args.dry_run:
    print('\nDry run only. Re-run with --apply to execute.')
    sys.exit(0)

print(f'\nApplying {len(planned)} owner updates...')
batch = [{'Id': r['Id'], 'OwnerId': r['RE_Assigned__c']} for r in planned]
results = sf.bulk.Opportunity.update(batch, batch_size=200)
succeeded = sum(1 for x in results if x.get('success'))
failed = [(r['Id'], x) for r, x in zip(planned, results) if not x.get('success')]
print(f'  Succeeded: {succeeded}')
print(f'  Failed: {len(failed)}')
for rid, x in failed[:10]:
    print(f'    {rid}: {x}')
