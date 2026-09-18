"""Drop the RE Assigned column from every MDU Tracker view.

Koa's ask 2026-09-15: remove RE Assigned from the MDU Tracker. Columns live in
Tracker_View__c.Config__c JSON, one record per view, so this is a data edit,
not a deploy. The filter dropdown is removed in trackerGrid itself, gated on
appContext, so the Business Tracker keeps it.

Scope is App_Context__c = 'MDU_Sales' only. Business views carry no RE column.

Rollback: the pre-change configs were snapshotted to
SalesForce/data/output/audit_logs/2026-09-15-mdu-tracker-view-configs-before-re-assigned-removal.json
and this script refuses to write if that file is missing.

Usage:
    python 2026-09-15-remove-re-assigned-from-mdu-tracker-views.py           # dry run
    python 2026-09-15-remove-re-assigned-from-mdu-tracker-views.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from _shared.sf_auth import get_sf  # noqa: E402

FIELD = "RE_Assigned__r.Name"
SNAPSHOT = (REPO / "SalesForce" / "data" / "output" / "audit_logs"
            / "2026-09-15-mdu-tracker-view-configs-before-re-assigned-removal.json")


def strip(config: dict) -> tuple[dict, bool]:
    before = len(config.get("columns", []))
    config["columns"] = [c for c in config.get("columns", [])
                         if c.get("field") != FIELD]
    changed = len(config["columns"]) != before
    # A sort or saved filter on the removed column would query a field the
    # grid no longer shows. None exist today; refuse rather than guess.
    if (config.get("sort") or {}).get("field") == FIELD:
        raise ValueError("view sorts on RE Assigned")
    if FIELD in json.dumps(config.get("filters", [])):
        raise ValueError("view filters on RE Assigned")
    return config, changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not SNAPSHOT.exists():
        print(f"FATAL: rollback snapshot missing: {SNAPSHOT}")
        return 1
    snap = {r["Id"]: r["Config__c"]
            for r in json.loads(SNAPSHOT.read_text())["result"]["records"]}

    sf = get_sf("main")
    views = sf.query_all(
        "SELECT Id, Name, Config__c FROM Tracker_View__c "
        "WHERE App_Context__c = 'MDU_Sales' ORDER BY Name")["records"]

    plan = []
    for v in views:
        if snap.get(v["Id"]) != v["Config__c"]:
            print(f"FATAL: {v['Name']} changed since the snapshot. Re-snapshot first.")
            return 1
        cfg, changed = strip(json.loads(v["Config__c"]))
        print(f"{'remove' if changed else 'no RE col':>9}  {v['Name']}")
        if changed:
            plan.append((v, cfg))

    print(f"\nviews to update: {len(plan)} of {len(views)}")
    if not args.apply:
        print("DRY RUN. Re-run with --apply to write.")
        return 0

    for v, cfg in plan:
        sf.Tracker_View__c.update(v["Id"], {"Config__c": json.dumps(cfg, indent=2)})

    print("\n=== VERIFY (re-query live) ===")
    after = sf.query_all(
        "SELECT Id, Name, Config__c FROM Tracker_View__c "
        "WHERE App_Context__c = 'MDU_Sales'")["records"]
    bad = 0
    for v in after:
        cols = [c.get("field") for c in json.loads(v["Config__c"])["columns"]]
        before = [c.get("field") for c in json.loads(snap[v["Id"]])["columns"]]
        expected = [f for f in before if f != FIELD]
        if cols != expected:
            bad += 1
            print(f"   MISMATCH {v['Name']}")
    print(f"views with RE removed and every other column intact: "
          f"{len(after) - bad} of {len(after)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
