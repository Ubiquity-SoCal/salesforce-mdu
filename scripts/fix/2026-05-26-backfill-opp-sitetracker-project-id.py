"""
Backfill Opportunity.SiteTracker_Project_ID__c (text) from the ST mirror's
SiteTracker_Record_Id__c, for every Opp where:
  - a SiteTracker_Project__c row already has Opportunity__c set to it
  - but the Opp's SiteTracker_Project_ID__c text field is null
This is one-direction drift cleanup. Does NOT touch ST.Opportunity__c (already set).

Snapshot + audit CSV before writes. Default = dry-run, pass --apply to write.

Output:
  audit_logs/opp_sitetracker_id_backfill_snapshot_<ts>.csv    (before-state)
  audit_logs/opp_sitetracker_id_backfill_<ts>.csv             (per-row results)
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)
APPLY = "--apply" in sys.argv

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)

# 1. Pull all ST rows with an Opp link, plus the linked Opp's current text field
print("[INFO] Querying ST mirror + linked Opps...")
rows = sf.query_all("""
    SELECT Id, Name, SiteTracker_Record_Id__c, Site_Name__c, Site_Status__c,
           Build_Status__c,
           Opportunity__c, Opportunity__r.Name,
           Opportunity__r.SiteTracker_Project_ID__c,
           Opportunity__r.StageName,
           Opportunity__r.Property_State__c
    FROM SiteTracker_Project__c
    WHERE Opportunity__c != null
""")["records"]
print(f"[INFO]   {len(rows)} ST mirror rows linked to an Opp")

# 2. Identify the drift cases: Opp text field is null
# One Opp can have multiple ST projects; we want to stamp ONE id per Opp.
# Strategy: prefer ST projects with newer-stage build_status if any are advanced,
# otherwise just the first encountered. (The text field can only hold one id.)
drift_by_opp = defaultdict(list)
for r in rows:
    opp = r.get("Opportunity__r") or {}
    if opp.get("SiteTracker_Project_ID__c"):
        continue  # already stamped
    drift_by_opp[r["Opportunity__c"]].append(r)

print(f"[INFO]   {len(drift_by_opp)} Opps have one or more ST links but null SiteTracker_Project_ID__c")

OUT = Path("C:/Users/cass/Work_Projects/SalesForce/data/output/audit_logs")
OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
snap_path = OUT / f"opp_sitetracker_id_backfill_snapshot_{ts}.csv"
audit_path = OUT / f"opp_sitetracker_id_backfill_{ts}.csv"

# Snapshot every Opp we plan to touch
with open(snap_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["opp_id", "opp_name", "opp_stage", "opp_state",
                "current_sitetracker_project_id", "st_count_for_opp",
                "st_ids", "st_names"])
    for opp_id, sts in drift_by_opp.items():
        first = sts[0].get("Opportunity__r") or {}
        w.writerow([
            opp_id, first.get("Name"), first.get("StageName"),
            first.get("Property_State__c"), None,
            len(sts),
            "; ".join(s.get("SiteTracker_Record_Id__c") or "" for s in sts),
            "; ".join(s.get("Name") or "" for s in sts),
        ])
print(f"[INFO]   Snapshot: {snap_path}")

# 3. Apply (or dry-run)
print(f"\n{'APPLY' if APPLY else 'DRY RUN'}: backfilling {len(drift_by_opp)} Opps\n")
ok = fail = 0
multi_st = []
with open(audit_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "opp_id", "opp_name", "opp_stage",
                "st_id_used", "st_name_used", "st_count_for_opp",
                "action", "result"])
    stamp = datetime.now().isoformat(timespec="seconds")

    for opp_id, sts in drift_by_opp.items():
        # Choose the ST id to stamp. Prefer the one with the most advanced
        # build status if multiple. (Same RANK as surface_to_opportunity.py.)
        RANK = {
            "4. Project - Completed": 5,
            "3. Project - Construction Phase": 4,
            "2. Project - Design Phase": 3,
            "2. Project - Up Next": 2,
            "1. Project - PAL/ROE Signed": 1,
            "5. Project - Pending Business Case Approval": 0,
        }
        chosen = sorted(sts, key=lambda s: RANK.get(s.get("Build_Status__c"), -1),
                        reverse=True)[0]
        st_id = chosen.get("SiteTracker_Record_Id__c") or chosen["Name"]
        st_name = chosen.get("Name")
        if len(sts) > 1:
            multi_st.append((opp_id, len(sts), [s.get("Name") for s in sts], chosen.get("Name")))

        opp_disp = (chosen.get("Opportunity__r") or {}).get("Name") or ""

        if not APPLY:
            w.writerow([stamp, opp_id, opp_disp,
                        (chosen.get("Opportunity__r") or {}).get("StageName"),
                        st_id, st_name, len(sts), "would_stamp", "dry_run"])
            continue

        try:
            sf.Opportunity.update(opp_id, {"SiteTracker_Project_ID__c": st_id})
            w.writerow([stamp, opp_id, opp_disp,
                        (chosen.get("Opportunity__r") or {}).get("StageName"),
                        st_id, st_name, len(sts), "stamped", "ok"])
            ok += 1
        except Exception as e:
            w.writerow([stamp, opp_id, opp_disp,
                        (chosen.get("Opportunity__r") or {}).get("StageName"),
                        st_id, st_name, len(sts), "stamped",
                        f"error:{type(e).__name__}:{str(e)[:120]}"])
            fail += 1

print(f"Audit: {audit_path}")
if APPLY:
    print(f"Stamped: ok={ok}  fail={fail}")
else:
    print(f"Would stamp: {len(drift_by_opp)} Opps. Re-run with --apply to write.")

if multi_st:
    print(f"\n[NOTE] {len(multi_st)} Opps had multiple ST projects -- picked most-advanced build:")
    for opp_id, n, names, chosen_name in multi_st[:15]:
        print(f"  {opp_id}  {n} STs ({', '.join(names)}); chose {chosen_name}")
