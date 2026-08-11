"""Reorder: move the Originator column to just BEFORE Owner in every active MDU tracker
view (was inserted after Owner). Config-only change to Tracker_View__c.Config__c.

Snapshots each view's prior Config__c to a rollback CSV. Idempotent: skips a view where
Originator is already immediately before Owner.

    python 2026-07-08-move-originator-before-owner.py            # dry run
    python 2026-07-08-move-originator-before-owner.py --apply     # write

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
OWNER = "Owner.Name"
ORIG = "Originator__r.Name"

creds = {}
for line in open(ROOT / "api" / "Salesforce_Credentials.txt", encoding="utf-8"):
    if ":" in line:
        k, v = line.split(":", 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds["Username"], password=creds["Password"],
                security_token=creds["Security Token"])

views = sf.query_all(
    "SELECT Id, Name, Config__c FROM Tracker_View__c "
    "WHERE App_Context__c='MDU_Sales' AND Object__c='Opportunity' AND Is_Active__c=true "
    "ORDER BY Name")["records"]
print(f"Active MDU Opportunity views: {len(views)}")

plan = []
for v in views:
    cfg = json.loads(v["Config__c"])
    cols = cfg.get("columns", [])
    fields = [c.get("field") for c in cols]
    if ORIG not in fields or OWNER not in fields:
        print(f"  SKIP (missing col): {v['Name']}")
        continue
    orig_col = cols[fields.index(ORIG)]
    remaining = [c for c in cols if c.get("field") != ORIG]
    owner_idx = [c.get("field") for c in remaining].index(OWNER)
    if fields.index(ORIG) == fields.index(OWNER) - 1:
        print(f"  SKIP (already before Owner): {v['Name']}")
        continue
    new_cols = remaining[:owner_idx] + [orig_col] + remaining[owner_idx:]
    cfg["columns"] = new_cols
    plan.append((v["Id"], v["Name"], json.dumps(cfg)))
    order = [c.get("field") for c in new_cols]
    print(f"  WILL REORDER: {v['Name']:28s} -> ...{order[owner_idx-1] if owner_idx>0 else ''}, {order[owner_idx]}, {order[owner_idx+1]}...")

if not plan:
    print("\nNothing to do."); sys.exit(0)
if not APPLY:
    print(f"\nDry run. {len(plan)} views would change. Re-run with --apply.")
    sys.exit(0)

OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%dT%H%M%S")
snap = OUT / f"2026-07-08-tracker-originator-reorder-rollback-{ts}.csv"
by_id = {v["Id"]: v for v in views}
with open(snap, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["Tracker_View_Id", "Name", "Config__c_before"])
    for vid, name, _ in plan:
        w.writerow([vid, name, by_id[vid]["Config__c"]])

for vid, name, new_cfg in plan:
    sf.Tracker_View__c.update(vid, {"Config__c": new_cfg})
    print(f"  updated {name}")
print(f"\nReordered {len(plan)} views.\n  rollback -> {snap}")
