"""
MDU Tracker enhancement (Melissa's request, 2026-06-01):
  1. Append a read-only "MDU Activation" column (ST_Activation_Actual__c) to the end
     of every active MDU_Sales tracker view.
  2. Add two row-level formatting rules so completion state is visible at a glance:
       - GREEN  (#d4edda): activated (ST_Activation_Actual__c present)  -> done.
       - BLUE   (#cfe2ff): Stage = Marketing/Bulk Complete & not activated -> awaiting activation.
     Green is listed first so it wins precedence (getRowFormatting returns first match).

Snapshots every view's Config__c to a timestamped JSON before touching anything (rollback).
Idempotent: re-running will not duplicate the column or the rules.

Read/transform/preview by default. Pass --apply to write. Creds from env.
"""
import os, sys, json, argparse
from datetime import datetime, timezone
from simple_salesforce import Salesforce

ACT_FIELD = "ST_Activation_Actual__c"
ACT_LABEL = "MDU Activation"
GREEN = "background:#d4edda"
BLUE = "background:#cfe2ff"
GRAY = "background:#e2e3e5"
SNAP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output", "tracker_view_snapshots")

# Pursuit Status (Substatus__c) values that mean "stalled / not actively proceeding".
# Excludes "No Marketing/Bulk Needed", which means done-no-bulk-needed (not stalled).
STALLED_STATUSES = [
    "Owner Unresponsive", "Budget Not Approved / Business Case", "Chose Another Provider",
    "Bulk/Marketing Rejected", "ISP or Funding Needed", "Incumbent EMA",
]

# Row rules in precedence order (getRowFormatting returns the FIRST matching row rule):
#   green activated (done) > gray stalled (pursuit status) > blue marketing-complete (awaiting activation)
# Fields used here are tracked in ROW_RULE_FIELDS so re-runs strip+re-add idempotently.
ROW_RULE_FIELDS = {ACT_FIELD, "Substatus__c", "StageName"}
BLUE_STAGES = ["Marketing/Bulk Complete", "PAL/ROE Complete"]
ROW_RULES = [
    {"field": ACT_FIELD, "operator": "greater_than", "value": "2015-01-01", "style": GREEN, "target": "row",
     "_note": "MDU activated = done (real date after 2015; ignores 1900/placeholder dates engineering enters). GREEN RESERVED FOR ACTIVATION ONLY."},
    {"field": "Substatus__c", "operator": "in_list", "value": STALLED_STATUSES, "style": GRAY, "target": "row",
     "_note": "has a stalled pursuit status = not actively proceeding"},
    {"field": "StageName", "operator": "in_list", "value": BLUE_STAGES, "style": BLUE, "target": "row",
     "_note": "at an advanced stage, in progress, not yet activated (incl. No Marketing/Bulk Needed)"},
]


def env(n):
    v = os.environ.get(n)
    if not v:
        print(f"[ERROR] missing env {n}"); sys.exit(1)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    sf = Salesforce(username=env("SF_MAIN_USERNAME"), password=env("SF_MAIN_PASSWORD"),
                    security_token=env("SF_MAIN_TOKEN"))
    views = sf.query("SELECT Id, Name, App_Context__c, Is_Active__c, Config__c "
                     "FROM Tracker_View__c WHERE App_Context__c='MDU_Sales' AND Object__c='Opportunity'")['records']

    # snapshot
    os.makedirs(SNAP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap_path = os.path.join(SNAP_DIR, f"mdu_tracker_views_{stamp}.json")
    with open(snap_path, "w", encoding="utf-8") as fh:
        json.dump([{"Id": v["Id"], "Name": v["Name"], "Is_Active__c": v["Is_Active__c"],
                    "Config__c": v["Config__c"]} for v in views], fh, indent=2)
    print(f"Snapshot ({len(views)} views) -> {os.path.relpath(snap_path)}\n")

    for v in views:
        cfg = json.loads(v["Config__c"])
        cols = cfg.setdefault("columns", [])
        rules = cfg.setdefault("formatting_rules", [])
        changes = []

        # 1. append activation column if absent
        if not any(c.get("field") == ACT_FIELD for c in cols):
            cols.append({"field": ACT_FIELD, "label": ACT_LABEL, "editable": False, "width": 130})
            changes.append("+column")

        # 2. ensure our row rules are present (strip any prior copies, re-add at front)
        existing = [r for r in rules if not (r.get("target") == "row" and r.get("field") in ROW_RULE_FIELDS)]
        new_rules = [dict(r) for r in ROW_RULES] + existing
        if new_rules != rules:
            cfg["formatting_rules"] = new_rules
            changes.append("row-rules")

        active = "" if v["Is_Active__c"] else " (inactive)"
        if changes:
            print(f"  {v['Name']:<30}{active}: {', '.join(changes)}")
            if args.apply:
                sf.Tracker_View__c.update(v["Id"], {"Config__c": json.dumps(cfg)})
        else:
            print(f"  {v['Name']:<30}{active}: already current")

    print("\n" + ("APPLIED." if args.apply else "PREVIEW only. Re-run with --apply to write."))


if __name__ == "__main__":
    main()
