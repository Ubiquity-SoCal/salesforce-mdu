"""Add a read-only "Originator" column (Originator__r.Name) to every active MDU tracker
view, placed right after the Owner column. Config lives as JSON in Tracker_View__c.Config__c.

Snapshots each view's prior Config__c to a rollback CSV before editing. Idempotent: skips a
view that already has the Originator column.

    python 2026-07-08-add-originator-tracker-column.py            # dry run
    python 2026-07-08-add-originator-tracker-column.py --apply     # write

Target org: fun-power-747 (PRODUCTION).
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "output"
APPLY = "--apply" in sys.argv

creds = {}
for line in open(ROOT / "api" / "Salesforce_Credentials.txt", encoding="utf-8"):
    if ":" in line:
        k, v = line.split(":", 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds["Username"], password=creds["Password"],
                security_token=creds["Security Token"])

NEW_COL = {"field": "Originator__r.Name", "label": "Originator", "width": 130}

views = sf.query_all(
    "SELECT Id, Name, Config__c FROM Tracker_View__c "
    "WHERE App_Context__c='MDU_Sales' AND Object__c='Opportunity' AND Is_Active__c=true "
    "ORDER BY Name")["records"]
print(f"Active MDU Opportunity views: {len(views)}")

plan = []  # (id, name, new_config_json)
for v in views:
    cfg = json.loads(v["Config__c"])
    cols = cfg.get("columns", [])
    fields = [c.get("field") for c in cols]
    if "Originator__r.Name" in fields:
        print(f"  SKIP (already has it): {v['Name']}")
        continue
    if "Owner.Name" in fields:
        idx = fields.index("Owner.Name") + 1
    else:
        idx = len(cols)
    new_cols = cols[:idx] + [dict(NEW_COL)] + cols[idx:]
    cfg["columns"] = new_cols
    plan.append((v["Id"], v["Name"], json.dumps(cfg)))
    print(f"  WILL ADD to: {v['Name']:28s} (insert at col {idx}, now {len(new_cols)} cols)")

if not plan:
    print("\nNothing to do."); sys.exit(0)
if not APPLY:
    print(f"\nDry run. {len(plan)} views would change. Re-run with --apply.")
    sys.exit(0)

OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%dT%H%M%S")
snap = OUT / f"2026-07-08-tracker-originator-column-rollback-{ts}.csv"
by_id = {v["Id"]: v for v in views}
with open(snap, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["Tracker_View_Id", "Name", "Config__c_before"])
    for vid, name, _ in plan:
        w.writerow([vid, name, by_id[vid]["Config__c"]])

for vid, name, new_cfg in plan:
    sf.Tracker_View__c.update(vid, {"Config__c": new_cfg})
    print(f"  updated {name}")
print(f"\nUpdated {len(plan)} views.\n  rollback -> {snap}")
