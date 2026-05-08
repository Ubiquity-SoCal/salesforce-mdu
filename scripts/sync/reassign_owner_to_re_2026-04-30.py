"""Reassign Opportunity Owner to RE_Assigned__c user.
Scope: MDU + Business_ROE record types, RE_Assigned populated, Owner != RE,
       active stages only (excludes Closed Lost, EMA/Bulk Complete),
       SKIP Opps that have BOTH a PAL and ROE Agreement attached.

Usage:
  python reassign_owner_to_re_2026-04-30.py --dry-run
  python reassign_owner_to_re_2026-04-30.py --apply
"""
import argparse, csv, sys
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

q = """
SELECT Id, Name, OwnerId, Owner.Name, RE_Assigned__c, RE_Assigned__r.Name, RE_Assigned__r.IsActive,
       RecordType.DeveloperName, StageName,
       (SELECT Agreement_Type__c FROM Agreements__r)
FROM Opportunity
WHERE RecordType.DeveloperName IN ('MDU','Business_ROE')
  AND RE_Assigned__c != null
  AND StageName NOT IN ('Closed Lost','EMA/Bulk Complete')
"""
records = sf.query_all(q)['records']

def types_for(r):
    sub = r.get('Agreements__r')
    ags = sub.get('records', []) if sub else []
    return set(a.get('Agreement_Type__c') for a in ags if a.get('Agreement_Type__c'))

planned = []
skipped_pal_roe = []
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

print(f'Total active-stage candidates: {len(records)}')
print(f'  Skipped (Owner already = RE or RE inactive): {len(records) - len(planned) - len(skipped_pal_roe)}')
print(f'  Skipped (has both PAL and ROE): {len(skipped_pal_roe)}')
print(f'  Planned reassignments: {len(planned)}')

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'reassign_owner_to_re_{ts}.csv'

# Write audit (always, even on dry-run)
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action',
                'RecordType', 'StageName', 'OldOwnerName', 'NewOwnerName', 'AgreementTypes'])
    for r in planned:
        w.writerow([r['Id'], r['Name'], 'OwnerId', r['OwnerId'], r['RE_Assigned__c'],
                    'reassign_owner_to_re_2026-04-30.py', ts,
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

# Apply via Bulk API (faster for ~100 records)
print(f'\nApplying {len(planned)} owner updates...')
batch = [{'Id': r['Id'], 'OwnerId': r['RE_Assigned__c']} for r in planned]
results = sf.bulk.Opportunity.update(batch, batch_size=200)

succeeded = sum(1 for x in results if x.get('success'))
failed = [(r['Id'], x) for r, x in zip(planned, results) if not x.get('success')]
print(f'  Succeeded: {succeeded}')
print(f'  Failed: {len(failed)}')
for rid, x in failed[:10]:
    print(f'    {rid}: {x}')
