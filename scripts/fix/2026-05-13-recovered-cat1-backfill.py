"""
Push 11 newly-categorized Cat 1 records to SF.

Source: SalesForce/data/output/blank-category-deep-retry-2026-05-13.csv
Recovered via aggressive geocoding variants (Nominatim fallback with state-
spelled-out fix, USA-suffix strip, synthetic house number, etc).

Excluded from this push: 2 records (Omaha_MDU_4822 and Omaha_MDU_1115) that
matched the ZIP 68132 centroid rather than an actual address. Koa is verifying
those manually in Vetro before they get categorized.

Follows the sf-audit-log-pattern:
  - re-pull current SF Property_Category__c per Opp (drift check)
  - update Property_Category__c = 'Cat 1' one Opp at a time
  - audit log captures before/after with provenance

Usage:
  python 2026-05-13-recovered-cat1-backfill.py            # dry-run
  python 2026-05-13-recovered-cat1-backfill.py --execute  # push
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

EXECUTE = '--execute' in sys.argv

SOURCE_CSV = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\blank-category-deep-retry-2026-05-13.csv")
AUDIT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-recovered-cat1-backfill.csv")
SOURCE_LABEL = 'fix/2026-05-13-recovered-cat1-backfill.py'

# Records to exclude: zip-centroid false-positive risk
EXCLUDE_VARIANT_PREFIX = '[nominatim] 68132,'

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)


def build_changeset() -> list[dict]:
    with SOURCE_CSV.open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    cat1 = [r for r in rows if r['New_Category'] == 'Cat 1']
    confident = [r for r in cat1 if not (r['Geocoder_Matched'] or '').startswith(EXCLUDE_VARIANT_PREFIX)]
    excluded = [r for r in cat1 if (r['Geocoder_Matched'] or '').startswith(EXCLUDE_VARIANT_PREFIX)]
    print(f"[INFO] Cat 1 recoveries total: {len(cat1)}")
    print(f"[INFO]   Confident (push):     {len(confident)}")
    print(f"[INFO]   ZIP-centroid (skip):  {len(excluded)}")
    for r in excluded:
        print(f"           - {r['Name']}  ({r['Geocoder_Matched']})")
    return confident


def verify(records: list[dict]) -> tuple[list[dict], list[tuple]]:
    """Re-pull current Property_Category__c. Filter out anything that drifted."""
    ids = [r['Id'] for r in records]
    quoted = ",".join(f"'{x}'" for x in ids)
    res = sf.query(
        f"SELECT Id, Name, Property_Category__c "
        f"FROM Opportunity WHERE Id IN ({quoted})"
    )
    cur = {o['Id']: (o.get('Property_Category__c') or '') for o in res['records']}

    ok, drift = [], []
    for r in records:
        actual = cur.get(r['Id'], '<not-found>')
        if actual == '':
            ok.append(r)
        else:
            drift.append((r['Id'], r['Name'], actual))
    return ok, drift


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    changes = build_changeset()
    print()
    print("Records to push:")
    print(f"  {'Name':<35} {'State':<5} {'Dist':>6}  {'Nearest fiber':<40}")
    for r in changes:
        print(f"  {r['Name'][:34]:<35} {r['State']:<5} {r['Distance_ft']:>6}  {r['Nearest_Addr'][:39]}")
    print()

    verified, drift = verify(changes)
    print(f"\n[INFO] Verified (blank in SF): {len(verified)}")
    print(f"[INFO] Drifted: {len(drift)}")
    for d in drift:
        print(f"  SKIP: {d[0]} {d[1]} (now {d[2]!r})")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute to push.")
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action', 'Provenance'])

    stamp = datetime.now().isoformat(timespec='seconds')
    ok, failed = 0, 0
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        # Log drift skips first
        for d in drift:
            w.writerow([d[0], d[1], 'Property_Category__c', '', '', SOURCE_LABEL, stamp, 'SKIPPED-drift', f'now={d[2]}'])
        for r in verified:
            provenance = f"dist={r['Distance_ft']}ft via {r['Nearest_Addr']} {r['Nearest_FDH']}"
            try:
                sf.Opportunity.update(r['Id'], {'Property_Category__c': 'Cat 1'})
                action = 'updated'
                ok += 1
            except Exception as e:
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                failed += 1
                print(f"  FAIL {r['Id']} {r['Name']}: {action}")
            w.writerow([r['Id'], r['Name'], 'Property_Category__c', '', 'Cat 1', SOURCE_LABEL, stamp, action, provenance])

    print(f"\n[RESULT] {ok} updated, {failed} failed, {len(drift)} skipped (drift).")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
