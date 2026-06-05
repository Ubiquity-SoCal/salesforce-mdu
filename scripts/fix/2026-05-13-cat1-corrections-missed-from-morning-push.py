"""
Push the 102 Cat 1 corrections that my morning fix script missed.

The morning push (2026-05-13-property-category-cat1-and-cleanup-backfill.py)
covered fill_blank -> Cat 1 (158) and over-tag-blanks (19), but skipped
change_type=change rows where current!=Cat 1 and suggested=Cat 1. Cat 1's
500ft definition is locked, so those should have been pushed too.

Reads the 2026-05-12 audit snapshot, finds rows where:
  change_type=change AND suggested_category='Cat 1' AND current_category!='Cat 1' AND current_category!=''

Plus, per re-check, also catches 2 records whose current Property_Category__c
in SF differs from what the snapshot recorded (could be a drift case). For
the actual push we re-pull SF state to confirm intent.

Usage:
  python 2026-05-13-cat1-corrections-missed-from-morning-push.py
  python 2026-05-13-cat1-corrections-missed-from-morning-push.py --execute
"""
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

EXECUTE = '--execute' in sys.argv

SNAPSHOT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-12-category-vs-serviceability-snapshot.csv")
AUDIT_PATH    = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-cat1-corrections-missed-backfill.csv")
SOURCE_LABEL  = 'fix/2026-05-13-cat1-corrections-missed-from-morning-push.py'

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    # 1. Find audit-flagged Cat 1 corrections that aren't blank-fills
    with SNAPSHOT_PATH.open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    candidates = [r for r in rows if r['change_type'] == 'change'
                                 and r['suggested_category'] == 'Cat 1'
                                 and r['current_category'] != 'Cat 1']
    print(f"[INFO] Audit-flagged Cat 1 corrections (change rows): {len(candidates)}")
    print("[INFO] Original category breakdown (per snapshot):")
    for k, v in Counter(r['current_category'] for r in candidates).most_common():
        print(f"        {k or '(blank)':<15} {v:>4}")

    # 2. Re-pull current SF state to confirm and drift-check
    ids = [r['Id'] for r in candidates]
    quoted_chunks = [ids[i:i+200] for i in range(0, len(ids), 200)]
    cur = {}
    for ch in quoted_chunks:
        q = ",".join(f"'{x}'" for x in ch)
        res = sf.query(
            f"SELECT Id, Name, Property_Category__c "
            f"FROM Opportunity WHERE Id IN ({q})"
        )
        for o in res['records']:
            cur[o['Id']] = o

    ready = []
    already_cat1 = []
    for r in candidates:
        sf_rec = cur.get(r['Id'])
        if not sf_rec:
            continue
        sf_cat = sf_rec.get('Property_Category__c') or ''
        if sf_cat == 'Cat 1':
            already_cat1.append(r['Id'])
        else:
            ready.append({
                'Id': r['Id'],
                'Name': sf_rec['Name'],
                'before': sf_cat,
                'snapshot_before': r['current_category'],
                'distance_ft': r['distance_ft'],
                'nearest': r['nearest_fiber_addr'],
            })

    print(f"\n[INFO] Already Cat 1 in SF (no-op): {len(already_cat1)}")
    print(f"[INFO] Will update to Cat 1:        {len(ready)}")
    print("\n[INFO] Current SF category breakdown (the universe we're updating):")
    for k, v in Counter(r['before'] or '(blank)' for r in ready).most_common():
        print(f"        {k:<15} {v:>4}")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute to push.")
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action', 'Provenance'])

    stamp = datetime.now().isoformat(timespec='seconds')
    ok = 0
    failed = 0
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for r in ready:
            try:
                sf.Opportunity.update(r['Id'], {'Property_Category__c': 'Cat 1'})
                action = 'updated'
                ok += 1
            except Exception as e:
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                failed += 1
                print(f"  FAIL {r['Id']} {r['Name']}: {action}")
            provenance = f"dist={r['distance_ft']}ft nearest={r['nearest']}"
            w.writerow([r['Id'], r['Name'], 'Property_Category__c',
                        r['before'], 'Cat 1', SOURCE_LABEL, stamp, action, provenance])

    print(f"\n[RESULT] {ok} updated, {failed} failed.")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
