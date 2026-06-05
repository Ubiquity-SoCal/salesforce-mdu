"""
Normalize Property_State__c 'Texas' -> 'TX' (mirror of the Nebraska fix
included in the morning Cat 1 + cleanup push).

Pulls every Opportunity with Property_State__c = 'Texas' (any RT, any stage),
snapshots before-state to audit log, then updates one at a time.

Usage:
  python 2026-05-13-texas-state-normalization.py            # dry-run
  python 2026-05-13-texas-state-normalization.py --execute  # push
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

EXECUTE = '--execute' in sys.argv

AUDIT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-texas-state-normalization.csv")
SOURCE_LABEL = 'fix/2026-05-13-texas-state-normalization.py'

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    res = sf.query(
        "SELECT Id, Name, RecordType.DeveloperName, StageName, Property_State__c "
        "FROM Opportunity WHERE Property_State__c = 'Texas'"
    )
    rows = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        rows.extend(res['records'])

    print(f"[INFO] Records with Property_State__c = 'Texas': {len(rows)}")
    print()
    for r in rows:
        print(f"  {r['Id']} {r['Name'][:40]:<42} RT={r['RecordType']['DeveloperName']:<10} Stage={r['StageName']}")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute to push.")
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

    stamp = datetime.now().isoformat(timespec='seconds')
    ok, failed = 0, 0
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for r in rows:
            try:
                sf.Opportunity.update(r['Id'], {'Property_State__c': 'TX'})
                action = 'updated'
                ok += 1
            except Exception as e:
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                failed += 1
                print(f"  FAIL {r['Id']} {r['Name']}: {action}")
            w.writerow([r['Id'], r['Name'], 'Property_State__c', 'Texas', 'TX', SOURCE_LABEL, stamp, action])

    print(f"\n[RESULT] {ok} updated, {failed} failed.")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
