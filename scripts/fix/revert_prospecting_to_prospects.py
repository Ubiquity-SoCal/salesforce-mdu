"""
Revert MDU Prospecting Opps that have NO real signal back to Prospects (cold).
Real signal = [Ting Exclusive Priority] in Next_Action__c, real-date 2026 Note,
2026 Task/Event, or Projected_Close_Date populated.

Reads target list from mdu_prospecting_audit.csv (Verdict='REVERT').
Writes audit log to SalesForce/audit_logs/.

Usage:
  python revert_prospecting_to_prospects.py --dry-run
  python revert_prospecting_to_prospects.py --apply
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true', help='Actually run the update (default is dry run)')
parser.add_argument('--dry-run', action='store_true', help='Preview only')
args = parser.parse_args()

if not args.apply and not args.dry_run:
    print("Specify --dry-run or --apply")
    sys.exit(1)

audit_csv = Path('mdu_prospecting_audit.csv')
if not audit_csv.exists():
    print(f"Missing {audit_csv}. Run audit_mdu_prospecting.py first.")
    sys.exit(1)

revert_targets = []
with audit_csv.open(encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['Verdict'] == 'REVERT':
            revert_targets.append(row)

print(f"Records to revert: {len(revert_targets)}")
print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Verify current state matches what audit captured (no drift)
ids = [r['Opp_Id'] for r in revert_targets]
def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

current = {}
for chunk in chunked(ids, 200):
    in_clause = "','".join(chunk)
    q = sf.query_all(f"SELECT Id, StageName, Name FROM Opportunity WHERE Id IN ('{in_clause}')")
    for r in q['records']:
        current[r['Id']] = r

drifted = [r for r in revert_targets if current.get(r['Opp_Id'], {}).get('StageName') != 'Prospecting']
if drifted:
    print(f"\nWARNING: {len(drifted)} records are no longer in Prospecting (drift since audit):")
    for r in drifted[:10]:
        cur_stage = current.get(r['Opp_Id'], {}).get('StageName', 'NOT FOUND')
        print(f"  {r['Opp_Name'][:50]:50s} now in: {cur_stage}")
    print("Skipping drifted records.")

work = [r for r in revert_targets if current.get(r['Opp_Id'], {}).get('StageName') == 'Prospecting']
print(f"\nWill update {len(work)} records: Prospecting -> Prospects\n")

if args.dry_run:
    print("First 20 targets:")
    for r in work[:20]:
        print(f"  {r['Owner'][:20]:20s} {r['Opp_Name'][:55]:55s} ({r['Opp_Id']})")
    print(f"\n... and {max(0, len(work)-20)} more.")
    print("\nDry run complete. Re-run with --apply to execute.")
    sys.exit(0)

# Apply
ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'revert_prospecting_to_prospects_{ts}.csv'

success = 0
failed = []
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])
    for r in work:
        oid = r['Opp_Id']
        try:
            sf.Opportunity.update(oid, {'StageName': 'Prospects'})
            w.writerow([oid, r['Opp_Name'], 'StageName', 'Prospecting', 'Prospects',
                        'revert_prospecting_to_prospects.py', ts, 'UPDATE'])
            success += 1
        except Exception as e:
            failed.append((oid, r['Opp_Name'], str(e)))
            print(f"  FAIL {oid} {r['Opp_Name'][:40]}: {e}")

print(f"\nUpdated: {success}")
print(f"Failed: {len(failed)}")
print(f"Audit log: {audit_path}")
