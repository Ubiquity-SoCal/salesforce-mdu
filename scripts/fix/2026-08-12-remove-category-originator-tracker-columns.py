"""Remove the Category and Originator columns from every MDU_Sales Tracker_View__c config.

Requested by Koa 2026-08-12. Two grid columns are coming off the MDU Tracker:

- Property_Category__c ("Category") - Vetro-computed serviceability Cat 1/2/3.
  Superseded on the grid by MDU_Categorization__c ("MDU Categorization",
  OnNet/OffNet/NearNet), which the team maintains by hand and which has been the
  authoritative categorization since 2026-05-19. The two are NOT the same field;
  serviceability still lives on the record, just not on the grid.
- Originator__r.Name ("Originator") - added 2026-07-08, now surplus on the grid.

Both fields remain on MDU_Opportunity_Record_Page (Originator__c and
Property_Category__c are live fieldInstances), so anyone who needs them opens the
record. Neither field appears in any view's filters, sort, or formatting_rules,
so nothing downstream depends on them being queried.

Business_Sales views are untouched.

Snapshots every Config__c to data/output/ before writing. Dry-run by default.

Usage:
    python 2026-08-12-remove-category-originator-tracker-columns.py            # dry run
    python 2026-08-12-remove-category-originator-tracker-columns.py --apply
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

# Column "field" values to drop, mapped to the label they render as.
DROP_FIELDS = {
    "Property_Category__c": "Category",
    "Originator__r.Name": "Originator",
}

# Config keys that reference field names and would break if we removed a field
# something still depends on. Checked before writing, not assumed.
REFERENCING_KEYS = ("filters", "sort", "formatting_rules")


def referenced_elsewhere(cfg, field):
    """True if `field` appears anywhere outside the columns list."""
    blob = json.dumps({k: v for k, v in cfg.items() if k != "columns"})
    # Originator__r.Name in a column is Originator__c in a filter; check both.
    needles = {field, field.replace("__r.Name", "__c")}
    return any(n in blob for n in needles)


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
    snap = OUT / f"2026-08-12-tracker-view-config-snapshot-{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            [{k: v for k, v in r.items() if k != "attributes"} for r in views],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"snapshot -> {snap.name} ({len(views)} views)\n")

    planned, skipped, blocked = [], [], []
    for r in views:
        if r["App_Context__c"] != APP:
            continue
        cfg = json.loads(r["Config__c"])
        cols = cfg.get("columns", [])

        present = [f for f in DROP_FIELDS if any(c.get("field") == f for c in cols)]
        if not present:
            skipped.append((r["Name"], "neither column present"))
            continue

        # Refuse to strip a field another part of the view config still needs.
        stuck = [f for f in present if referenced_elsewhere(cfg, f)]
        if stuck:
            blocked.append((r["Name"], ", ".join(stuck)))
            continue

        cfg["columns"] = [c for c in cols if c.get("field") not in DROP_FIELDS]
        removed = [DROP_FIELDS[f] for f in present]
        planned.append((r["Id"], r["Name"], removed, len(cols), json.dumps(cfg)))

    print(f"{len(planned)} views to update, {len(skipped)} skipped, {len(blocked)} blocked")
    for _, name, removed, before, _ in planned:
        print(f"   - {name:<30} drop {', '.join(removed):<22} ({before} -> {before - len(removed)} cols)")
    for name, why in skipped:
        print(f"   . {name:<30} skipped: {why}")
    for name, why in blocked:
        print(f"   ! {name:<30} BLOCKED: still referenced by filter/sort/format: {why}")

    if blocked:
        print("\nBlocked views left untouched - resolve the reference first.")

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return 0

    print()
    ok = fail = 0
    for vid, name, _, _, cfg_json in planned:
        try:
            sf.Tracker_View__c.update(vid, {"Config__c": cfg_json})
            ok += 1
            print(f"   updated {name}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"   FAILED  {name}: {str(exc)[:180]}")
    print(f"\napplied {ok}, failed {fail}")

    # verify against the org, not against what we think we sent
    after = sf.query_all(
        "SELECT Name, App_Context__c, Config__c FROM Tracker_View__c"
    )["records"]
    mdu = [r for r in after if r["App_Context__c"] == APP]
    lingering = []
    for r in mdu:
        fields = [c.get("field") for c in json.loads(r["Config__c"]).get("columns", [])]
        for f in DROP_FIELDS:
            if f in fields:
                lingering.append(f"{r['Name']}:{DROP_FIELDS[f]}")
    print(f"verify: {len(mdu)} {APP} views checked, {len(lingering)} still carrying a dropped column")
    for item in lingering:
        print(f"   still present: {item}")

    other = [r for r in after if r["App_Context__c"] != APP]
    touched = sum(
        1
        for r in other
        if any(
            c.get("field") in DROP_FIELDS
            for c in json.loads(r["Config__c"]).get("columns", [])
        )
    )
    print(f"verify: {touched} of {len(other)} non-{APP} views still carry them (expected: unchanged)")

    return 0 if fail == 0 and not lingering else 1


if __name__ == "__main__":
    sys.exit(main())
