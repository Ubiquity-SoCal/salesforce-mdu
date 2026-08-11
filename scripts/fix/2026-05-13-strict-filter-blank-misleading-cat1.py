"""
Blank Property_Category__c on Opportunities currently tagged Cat 1 that the
strict-addrstatus audit reclassified as Cat 2 or Cat 3.

Why: Cat 1 means "we can sell this today." Under the original loose filter
(milestone='asbuilt' only), the index included 24% future_serviceable +
1.5% unserviceable points. 66 properties were within 500ft of one of those
non-sellable points and got tagged Cat 1 even though their nearest TRULY
serviceable drop is farther away.

Source: Serviceability_Lookup/data/output/strict-addrstatus-audit-2026-05-13.csv
Filter: Cat_current = 'Cat 1' AND Cat_strict in ('Cat 2','Cat 3')
        (excludes no-geo cases - geocoder failure isn't a category claim)

We blank rather than push to Cat 2/Cat 3 because those are placeholder
categories pending Pankaj/Taylor's framework decision. Same pattern as the
morning over-tag-blank pass.

Usage:
  python 2026-05-13-strict-filter-blank-misleading-cat1.py
  python 2026-05-13-strict-filter-blank-misleading-cat1.py --execute
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

DELTA_CSV = Path(r"C:\Users\cass\Work_Projects\Serviceability_Lookup\data\output\strict-addrstatus-audit-2026-05-13.csv")
AUDIT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-strict-filter-blank-misleading-cat1.csv")
SOURCE_LABEL = 'fix/2026-05-13-strict-filter-blank-misleading-cat1.py'

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    with DELTA_CSV.open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    targets = [r for r in rows
               if r['Cat_current'] == 'Cat 1'
               and r['Cat_strict'] in ('Cat 2', 'Cat 3')]
    print(f"[INFO] Cat 1 -> not-Cat-1 under strict filter: {len(targets)}")
    print("[INFO] Strict-filter destination breakdown:")
    from collections import Counter
    for k, v in Counter(r['Cat_strict'] for r in targets).most_common():
        print(f"        Cat 1 -> {k}: {v}")
    print()

    # Re-pull current SF state for drift check
    ids = [r['Id'] for r in targets]
    quoted_chunks = [ids[i:i+200] for i in range(0, len(ids), 200)]
    cur = {}
    for ch in quoted_chunks:
        q = ",".join(f"'{x}'" for x in ch)
        res = sf.query(f"SELECT Id, Name, Property_Category__c FROM Opportunity WHERE Id IN ({q})")
        for o in res['records']:
            cur[o['Id']] = o

    ready = []
    drifted = []
    for r in targets:
        sf_rec = cur.get(r['Id'])
        if not sf_rec:
            continue
        sf_cat = sf_rec.get('Property_Category__c') or ''
        if sf_cat != 'Cat 1':
            drifted.append((r['Id'], sf_rec['Name'], sf_cat))
        else:
            ready.append({
                'Id': r['Id'],
                'Name': sf_rec['Name'],
                'strict_cat': r['Cat_strict'],
                'distance_ft_strict': r['Distance_ft_strict'],
            })

    print(f"[INFO] Verified (currently Cat 1 in SF): {len(ready)}")
    print(f"[INFO] Drifted (already not Cat 1): {len(drifted)}")
    for d in drifted[:10]:
        print(f"  SKIP {d[0]} {d[1]} (now {d[2]!r})")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute.")
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action', 'Provenance'])

    stamp = datetime.now().isoformat(timespec='seconds')
    ok = failed = 0
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for d in drifted:
            w.writerow([d[0], d[1], 'Property_Category__c', '', '', SOURCE_LABEL, stamp, f'SKIPPED-drift-to-{d[2]}', ''])
        for r in ready:
            try:
                sf.Opportunity.update(r['Id'], {'Property_Category__c': None})
                action = 'blanked'
                ok += 1
            except Exception as e:
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                failed += 1
                print(f"  FAIL {r['Id']} {r['Name']}: {action}")
            provenance = f"strict_cat={r['strict_cat']} dist_to_serviceable={r['distance_ft_strict']}ft"
            w.writerow([r['Id'], r['Name'], 'Property_Category__c', 'Cat 1', '', SOURCE_LABEL, stamp, action, provenance])

    print(f"\n[RESULT] {ok} blanked, {failed} failed, {len(drifted)} skipped (drift).")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
