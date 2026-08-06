"""Add the Unit_Group__c column to every MDU_Sales Tracker_View__c config.

Requested by Niraj 2026-07-29 (PAL/ROE acquisition refocus): the on-net MDU
pipeline needs to be groupable and filterable by property size band. The
Unit_Group__c formula field was deployed 2026-08-06; this puts it on the tracker
grid so the LWC's server-side filter will accept it (TrackerController only
allows filtering on fields present in the view's column list).

Inserts the column immediately after Units__c, non-editable (it is a formula).

Snapshots every Config__c to data/output/ before writing. Dry-run by default.

Usage:
    python 2026-08-06-add-unit-group-tracker-column.py            # dry run
    python 2026-08-06-add-unit-group-tracker-column.py --apply
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from _shared.sf_auth import get_sf  # noqa: E402

OUT = REPO / "SalesForce" / "data" / "output"
APP = "MDU_Sales"
NEW_COLUMN = {
    "field": "Unit_Group__c",
    "label": "Unit Group",
    "width": 110,
    "editable": False,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to Salesforce")
    args = ap.parse_args()

    sf = get_sf("main")
    views = sf.query_all(
        "SELECT Id, Name, App_Context__c, Is_Active__c, Config__c "
        "FROM Tracker_View__c ORDER BY Sort_Order__c"
    )["records"]

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    snap = OUT / f"2026-08-06-tracker-view-config-snapshot-{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            [
                {k: v for k, v in r.items() if k != "attributes"}
                for r in views
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"snapshot -> {snap.name} ({len(views)} views)\n")

    planned, skipped = [], []
    for r in views:
        if r["App_Context__c"] != APP:
            continue
        cfg = json.loads(r["Config__c"])
        cols = cfg.get("columns", [])
        fields = [c.get("field") for c in cols]

        if "Unit_Group__c" in fields:
            skipped.append((r["Name"], "already present"))
            continue
        if "Units__c" not in fields:
            skipped.append((r["Name"], "no Units__c column to anchor to"))
            continue

        idx = fields.index("Units__c") + 1
        cols.insert(idx, dict(NEW_COLUMN))
        cfg["columns"] = cols
        planned.append((r["Id"], r["Name"], idx, json.dumps(cfg)))

    print(f"{len(planned)} views to update, {len(skipped)} skipped")
    for _, name, idx, _ in planned:
        print(f"   + {name:<32} Unit Group inserted at column index {idx}")
    for name, why in skipped:
        print(f"   - {name:<32} skipped: {why}")

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return 0

    print()
    ok = fail = 0
    for vid, name, _, cfg_json in planned:
        try:
            sf.Tracker_View__c.update(vid, {"Config__c": cfg_json})
            ok += 1
            print(f"   updated {name}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"   FAILED  {name}: {str(exc)[:180]}")
    print(f"\napplied {ok}, failed {fail}")

    # verify
    after = sf.query_all(
        "SELECT Name, App_Context__c, Config__c FROM Tracker_View__c"
    )["records"]
    have = sum(
        1
        for r in after
        if r["App_Context__c"] == APP
        and "Unit_Group__c" in [c.get("field") for c in json.loads(r["Config__c"]).get("columns", [])]
    )
    total = sum(1 for r in after if r["App_Context__c"] == APP)
    print(f"verify: {have} of {total} {APP} views now carry Unit_Group__c")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
