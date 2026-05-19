"""Add MDU_Categorization__c as a column in the MDU Tracker, positioned right
after Property_Category__c ('Category'), across all MDU_Sales Tracker_View__c views.

Columns are stored as JSON in Tracker_View__c.Config__c; the Apex controller
builds its SOQL dynamically from them, so no code deploy is needed.

Snapshots every MDU view's current Config__c to a rollback file first.
Default is DRY RUN; pass --apply to write.

  python add_mdu_categorization_tracker_column_2026-05-19.py
  python add_mdu_categorization_tracker_column_2026-05-19.py --apply
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
NEW_COL = {"field": "MDU_Categorization__c", "label": "MDU Categorization",
           "width": 150, "editable": True}
ANCHOR = "Property_Category__c"


def main(apply: bool):
    sys.stdout.reconfigure(line_buffering=True)
    c = {}
    for line in (ROOT / "api/Salesforce_Credentials.txt").read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            c[k.strip().lower()] = v.strip()
    sf = Salesforce(username=c["username"], password=c["password"], security_token=c["security token"])

    recs = sf.query_all(
        "SELECT Id, Name, App_Context__c, Config__c FROM Tracker_View__c "
        "WHERE App_Context__c = 'MDU_Sales' ORDER BY Name"
    )["records"]
    print(f"[INFO] {len(recs)} MDU_Sales Tracker_View__c records")

    # Rollback snapshot
    snap_dir = ROOT / "data" / "output"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"tracker_view_config_rollback_{STAMP}.json"
    snap_path.write_text(json.dumps(
        {r["Id"]: r["Config__c"] for r in recs}, indent=2), encoding="utf-8")
    print(f"[INFO] Rollback snapshot: {snap_path}")

    to_update = []
    for r in recs:
        cfg = json.loads(r["Config__c"])
        cols = cfg.get("columns", [])
        fields = [col.get("field") for col in cols]
        if NEW_COL["field"] in fields:
            print(f"   [skip] {r['Name']}: already has column")
            continue
        if ANCHOR not in fields:
            print(f"   [WARN] {r['Name']}: no {ANCHOR} anchor; appending after Name")
            idx = fields.index("Name") if "Name" in fields else 0
        else:
            idx = fields.index(ANCHOR)
        cols.insert(idx + 1, dict(NEW_COL))
        cfg["columns"] = cols
        new_json = json.dumps(cfg)
        to_update.append((r["Id"], r["Name"], new_json))
        print(f"   [will add] {r['Name']}: inserted at position {idx + 1}")

    print(f"\n[SUMMARY] {len(to_update)} views to update, "
          f"{len(recs) - len(to_update)} skipped/unchanged")

    if not apply:
        print("\n[DRY RUN] No writes. Re-run with --apply.")
        return
    ok = err = 0
    for vid, name, new_json in to_update:
        try:
            sf.Tracker_View__c.update(vid, {"Config__c": new_json})
            ok += 1
            print(f"   [updated] {name}")
        except Exception as e:
            err += 1
            print(f"   [ERROR] {name}: {e}")
    print(f"\n[DONE] Updated: {ok}, Errors: {err}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    main(ap.parse_args().apply)
