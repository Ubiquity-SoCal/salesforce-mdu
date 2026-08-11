"""
Backfill Property_Category__c (Cat 1 only) and clean up corrupt category /
state values on Opportunity.

Source of truth:
  SalesForce/data/output/audit_logs/2026-05-12-category-vs-serviceability-snapshot.csv
  (produced 2026-05-12 PM by scripts/analysis/audit_category_vs_serviceability.py)

Scope (locked with Koa 2026-05-13). All operations derive from the snapshot:
  1. fill-blank-to-cat1  158 rows  '' -> 'Cat 1'           (Cat 1 def is locked)
  2. overtag-blank        19 rows  'Cat 1' -> ''           (current Cat 1 but >500ft)
  3. corrupt-blank         5 rows  'Cat 2, Cat 3' -> ''    (corrupt multi-value)
  4. hold-fix-to-cat1      1 row   'Hold' -> 'Cat 1'       (Elm Grove Estates, suggested Cat 1)
  5. state-norm           12 rows  Property_State__c 'Nebraska' -> 'NE'

Distinct Opps touched: 187 (8 of those also need state-norm alongside cat fill).

Cat 2 and Cat 3 backfills are explicitly DEFERRED — thresholds in the lookup
tool are placeholders pending Taylor's official definitions. Don't commit
placeholder values to SF.

Process (sf-audit-log-pattern):
  - Re-pull current SF values for every Opp in the changeset (snapshot is a day
    old; verify nothing drifted before mutating).
  - Filter out rows where the SF current value no longer matches what the
    snapshot recorded (concurrent edit) - log and skip.
  - One sf.Opportunity.update() per Opp, combining Category + State payload.
  - Append audit row per field-level op.

Usage:
  python 2026-05-13-property-category-cat1-and-cleanup-backfill.py            # dry-run
  python 2026-05-13-property-category-cat1-and-cleanup-backfill.py --execute  # push
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

EXECUTE = '--execute' in sys.argv

SNAPSHOT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-12-category-vs-serviceability-snapshot.csv")
AUDIT_PATH    = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-property-category-backfill.csv")
SOURCE_LABEL  = 'fix/2026-05-13-property-category-cat1-and-cleanup-backfill.py'

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)


def build_changeset() -> dict[str, dict]:
    """Read snapshot, return {opp_id: {Name, ops: [(field, before, after, reason)]}}."""
    with SNAPSHOT_PATH.open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    changes: dict[str, dict] = {}

    def add(r, field, before, after, reason):
        changes.setdefault(r['Id'], {'Name': r['Name'], 'ops': []})['ops'].append(
            (field, before, after, reason)
        )

    for r in rows:
        # 1. blank -> Cat 1
        if r['change_type'] == 'fill_blank' and r['suggested_category'] == 'Cat 1' and r['current_category'] == '':
            add(r, 'Property_Category__c', '', 'Cat 1', 'fill-blank-to-cat1')

        # 2. Cat 1 -> blank (over-tagged)
        if r['change_type'] == 'change' and r['current_category'] == 'Cat 1' and r['suggested_category'] != 'Cat 1':
            add(r, 'Property_Category__c', 'Cat 1', '', 'overtag-blank')

        # 3. 'Cat 2, Cat 3' -> blank (corrupt multi-value)
        if r['current_category'] == 'Cat 2, Cat 3':
            add(r, 'Property_Category__c', 'Cat 2, Cat 3', '', 'corrupt-blank')

        # 4. 'Hold' -> Cat 1 (Elm Grove Estates, suggested Cat 1)
        if r['current_category'] == 'Hold':
            add(r, 'Property_Category__c', 'Hold', 'Cat 1', 'hold-fix-to-cat1')

        # 5. Property_State 'Nebraska' -> 'NE'
        if r['Property_State'] == 'Nebraska':
            add(r, 'Property_State__c', 'Nebraska', 'NE', 'state-norm')

    return changes


def verify_against_sf(changes: dict[str, dict]) -> tuple[dict, list]:
    """Re-pull current SF state. Return (verified, drifted).

    drifted = list of (opp_id, field, expected_before, actual_sf_value) where
    the current SF value doesn't match what the snapshot recorded.
    """
    ids = list(changes.keys())
    print(f"[INFO] Re-verifying {len(ids):,} Opps against current SF state...")

    sf_state: dict[str, dict] = {}
    CHUNK = 200
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i+CHUNK]
        quoted = ",".join(f"'{x}'" for x in chunk)
        res = sf.query(
            f"SELECT Id, Name, Property_Category__c, Property_State__c "
            f"FROM Opportunity WHERE Id IN ({quoted})"
        )
        for o in res['records']:
            sf_state[o['Id']] = {
                'Name': o['Name'],
                'Property_Category__c': o.get('Property_Category__c') or '',
                'Property_State__c':    o.get('Property_State__c')    or '',
            }

    drifted = []
    verified: dict[str, dict] = {}
    for opp_id, c in changes.items():
        if opp_id not in sf_state:
            drifted.append((opp_id, '*', '<existed in snapshot>', '<not found in SF>'))
            continue
        cur = sf_state[opp_id]
        ok_ops = []
        for field, before, after, reason in c['ops']:
            actual = cur[field]
            if actual != before:
                drifted.append((opp_id, field, before, actual))
            else:
                ok_ops.append((field, before, after, reason))
        if ok_ops:
            verified[opp_id] = {'Name': cur['Name'], 'ops': ok_ops}

    return verified, drifted


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    changes = build_changeset()
    n_opps = len(changes)
    n_ops  = sum(len(c['ops']) for c in changes.values())

    counter: dict[str, int] = defaultdict(int)
    for c in changes.values():
        for op in c['ops']:
            counter[op[3]] += 1

    print(f"[INFO] Changeset from snapshot:")
    print(f"  Distinct Opps : {n_opps:,}")
    print(f"  Field-level ops: {n_ops:,}\n")
    for reason in ('fill-blank-to-cat1', 'overtag-blank', 'corrupt-blank', 'hold-fix-to-cat1', 'state-norm'):
        print(f"  {reason:<22} {counter[reason]:>4}")
    print()

    verified, drifted = verify_against_sf(changes)
    print(f"[INFO] Verified Opps: {len(verified):,}")
    print(f"[INFO] Drifted rows : {len(drifted):,}")
    if drifted:
        print("\n[WARN] These rows changed since the snapshot and will be skipped:")
        for opp_id, field, expected, actual in drifted[:20]:
            print(f"  {opp_id} {field}: expected before={expected!r}, found={actual!r}")
        if len(drifted) > 20:
            print(f"  ... and {len(drifted)-20} more")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute to push.")
        return

    # Write header
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action', 'Reason'])

    # Also log drifted rows so we have a record of what we skipped
    stamp = datetime.now().isoformat(timespec='seconds')
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for opp_id, field, expected, actual in drifted:
            w.writerow([opp_id, '', field, expected, actual, SOURCE_LABEL, stamp, 'SKIPPED-drift', 'value-changed-since-snapshot'])

    # Execute
    ok = 0
    failed = 0
    print(f"\n[INFO] Pushing {len(verified):,} Opp updates...")
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for opp_id, c in verified.items():
            # SF wants None to clear; '' won't clear a picklist
            payload = {}
            for field, before, after, reason in c['ops']:
                payload[field] = after if after != '' else None

            try:
                sf.Opportunity.update(opp_id, payload)
                ok += 1
                action = 'updated'
            except Exception as e:
                failed += 1
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                print(f"  FAIL {opp_id} ({c['Name']}): {action}")

            for field, before, after, reason in c['ops']:
                w.writerow([opp_id, c['Name'], field, before, after, SOURCE_LABEL, stamp, action, reason])

    print(f"\n[RESULT] {ok:,} Opps updated, {failed} failed, {len(drifted)} skipped (drift).")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
