"""
Clear Sub_Bucket__c-underlying fields where the value no longer makes sense for
the current StageName.

Rules (confirmed by Koa 2026-05-12):
  - Sales_Status__c   valid only when StageName in {Prospects, Prospecting}
  - Hold_Reason__c    valid only when StageName = On Hold
  - Loss_Reason__c    valid only when StageName = Closed Lost
  - Substatus__c      already SF-enforced via dependent picklist on StageName (no action)

Process:
  1. Query violations (one row per violating field-on-Opp; an Opp can violate >1).
  2. Snapshot pre-state to audit CSV BEFORE mutating.
  3. Update one Opp at a time (sf.Opportunity.update) setting each violating field
     to null.
  4. Append result (success/failure) back to the audit log.

Outputs:
  data/output/audit_logs/2026-05-12-clear-stale-substatus.csv

Followed pattern: sf-audit-log-pattern.md (SF_Id/Name/Field/Before/After/Source/Timestamp/Action).
"""
import csv
import sys
from collections import defaultdict
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

VALID_STAGES = {
    'Sales_Status__c': {'Prospects', 'Prospecting'},
    'Hold_Reason__c':  {'On Hold'},
    'Loss_Reason__c':  {'Closed Lost'},
}
SOURCE_LABEL = 'fix/2026-05-12-clear-stale-substatus-fields.py'

AUDIT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-12-clear-stale-substatus.csv")
AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


def pull_violations() -> list[dict]:
    """One row per violating (Opp, Field) pair. Includes the current OldValue."""
    soql = """
    SELECT Id, Name, StageName,
           Sales_Status__c, Hold_Reason__c, Loss_Reason__c
    FROM Opportunity
    WHERE Sales_Status__c != null OR Hold_Reason__c != null OR Loss_Reason__c != null
    """
    print("[INFO] Pulling all Opps with any of the three fields populated...")
    res = sf.query(soql)
    recs = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        recs.extend(res['records'])
    print(f"[INFO] {len(recs):,} Opps have at least one of these fields set.")

    violations = []
    for o in recs:
        for field, valid_stages in VALID_STAGES.items():
            val = o.get(field)
            if val and o['StageName'] not in valid_stages:
                violations.append({
                    'Id': o['Id'],
                    'Name': o['Name'],
                    'StageName': o['StageName'],
                    'Field': field,
                    'OldValue': val,
                })
    return violations


def main():
    violations = pull_violations()
    print(f"\n[INFO] Total field-level violations: {len(violations)}")

    # Group by stage x field x value for a confirmation summary
    grouped = defaultdict(int)
    for v in violations:
        grouped[(v['StageName'], v['Field'], v['OldValue'])] += 1
    print("\nViolations to clear:")
    print(f"  {'Stage':<26} {'Field':<22} {'OldValue':<45} {'Count':>5}")
    for (stage, field, val), n in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1], -x[1])):
        print(f"  {stage:<26} {field:<22} {val:<45} {n:>5}")

    # Group by Opp Id so we batch one update per Opp even if it has 2 fields to clear
    by_opp = defaultdict(list)
    for v in violations:
        by_opp[v['Id']].append(v)
    print(f"\n[INFO] {len(by_opp):,} distinct Opps will be updated.")

    # Write pre-state snapshot to audit log BEFORE mutating
    print(f"\n[INFO] Writing pre-state snapshot to {AUDIT_PATH.name}...")
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Stage', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

    # Execute updates one Opp at a time. Append audit row per field cleared.
    ok = 0
    failed = 0
    stamp = datetime.now().isoformat(timespec='seconds')
    print("\n[INFO] Executing updates...")
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for opp_id, vs in by_opp.items():
            update_payload = {v['Field']: None for v in vs}
            try:
                sf.Opportunity.update(opp_id, update_payload)
                ok += 1
                action = 'cleared'
            except Exception as e:
                failed += 1
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                print(f"  FAIL {opp_id} ({vs[0]['Name']}): {action}")
            for v in vs:
                w.writerow([
                    v['Id'], v['Name'], v['StageName'], v['Field'],
                    v['OldValue'], '', SOURCE_LABEL, stamp, action,
                ])

    print(f"\n[RESULT] {ok:,} Opps updated, {failed} failed.")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
