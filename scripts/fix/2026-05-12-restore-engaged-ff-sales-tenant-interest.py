"""
Restore the Sales_Status__c = 'FF Sales - Tenant Interest Required' value on
Engaged-stage Opps that 2026-05-12-clear-stale-substatus-fields.py incorrectly
cleared. That value legitimately belongs to the Engaged stage (clarified by
Koa after the cleanup ran).

Source of truth: the prior cleanup's audit log captured the BEFORE value.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

PRIOR_AUDIT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-12-clear-stale-substatus.csv")
RESTORE_AUDIT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-12-restore-engaged-ff-sales.csv")
SOURCE_LABEL = 'fix/2026-05-12-restore-engaged-ff-sales-tenant-interest.py'


def main():
    # Read prior cleanup audit
    with PRIOR_AUDIT.open('r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    # Filter to the rows we want to undo
    to_restore = [
        r for r in rows
        if r['Field'] == 'Sales_Status__c'
        and r['Stage'] == 'Engaged'
        and r['Before'] == 'FF Sales - Tenant Interest Required'
        and r['Action'] == 'cleared'
    ]
    print(f"[INFO] {len(to_restore)} Opps to restore.")

    stamp = datetime.now().isoformat(timespec='seconds')
    RESTORE_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with RESTORE_AUDIT.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Stage', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

        ok = 0
        failed = 0
        for r in to_restore:
            try:
                sf.Opportunity.update(r['SF_Id'], {'Sales_Status__c': r['Before']})
                ok += 1
                action = 'restored'
            except Exception as e:
                failed += 1
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                print(f"  FAIL {r['SF_Id']} ({r['Name']}): {action}")
            w.writerow([
                r['SF_Id'], r['Name'], r['Stage'], r['Field'],
                '', r['Before'], SOURCE_LABEL, stamp, action,
            ])

    print(f"\n[RESULT] {ok} restored, {failed} failed.")
    print(f"[RESULT] Audit log: {RESTORE_AUDIT}")


if __name__ == '__main__':
    main()
