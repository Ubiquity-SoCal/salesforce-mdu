"""
Bulk-advance MDU Opportunities to EMA/Bulk Completed or EMA/Bulk In Progress
based on their Agreement records. ONLY touches Opps currently in 'Under Contract'.

Logic:
  - If Opp has any EMA/Bulk agreement in Completed or Archive  -> EMA/Bulk Completed
  - Else if Opp has any EMA/Bulk agreement NOT in Cancelled    -> EMA/Bulk In Progress
  - Anything else: skipped (cleanup report will surface)

Run: python bulk_advance_ema_bulk_stage_2026-04-28.py [--apply]
"""

import sys
import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

APPLY = "--apply" in sys.argv


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("Connected")

    # Pull EMA/Bulk Agreements on MDU Opps currently at Under Contract
    soql = """
        SELECT Id, Name, Agreement_Type__c, Status__c, Opportunity__c,
               Opportunity__r.Name, Opportunity__r.StageName
        FROM Agreement__c
        WHERE Agreement_Type__c IN ('EMA','Bulk')
          AND Opportunity__r.RecordType.DeveloperName = 'MDU'
          AND Opportunity__r.StageName = 'Under Contract'
    """
    agrs = sf.query_all(soql)["records"]
    print(f"Pulled {len(agrs)} EMA/Bulk Agreements on Under Contract MDU Opps")

    by_opp = defaultdict(lambda: {"completed": [], "active": [], "name": ""})
    for a in agrs:
        s = by_opp[a["Opportunity__c"]]
        s["name"] = (a.get("Opportunity__r") or {}).get("Name", "")
        status = a.get("Status__c") or ""
        entry = (a["Name"], a["Agreement_Type__c"], status)
        if status in ("Completed", "Archive"):
            s["completed"].append(entry)
        elif status in ("Create", "Review", "Sign", "Paused"):
            s["active"].append(entry)

    to_completed = []
    to_in_progress = []
    for opp_id, s in by_opp.items():
        if s["completed"]:
            to_completed.append((opp_id, s, "EMA/Bulk Completed"))
        elif s["active"]:
            to_in_progress.append((opp_id, s, "EMA/Bulk In Progress"))

    print(f"Targets:  EMA/Bulk Completed: {len(to_completed)}    EMA/Bulk In Progress: {len(to_in_progress)}")

    # Audit CSV
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit_path = LOG_DIR / f"opp_stage_advance_ema_bulk_{ts}.csv"
    with open(audit_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Name", "Field", "Before", "After", "TriggeringAgreements", "Source", "Action", "Timestamp"])
        for opp_id, s, target in to_completed + to_in_progress:
            details = "; ".join(f"{a[0]} {a[1]} ({a[2]})" for a in s["completed"] + s["active"])
            action = "UPDATE" if APPLY else "PREVIEW"
            w.writerow([
                opp_id, s["name"], "StageName", "Under Contract", target,
                details, "bulk_advance_ema_bulk_stage_2026-04-28.py",
                action, datetime.now().isoformat(),
            ])
    print(f"Audit written: {audit_path}")

    if not APPLY:
        print("PREVIEW only. Re-run with --apply to push.")
        return

    # Apply via REST API in chunks of 200 per stage value
    def push(targets, stage):
        ok = fail = 0
        msgs = []
        for opp_id, s, _ in targets:
            try:
                sf.Opportunity.update(opp_id, {"StageName": stage})
                ok += 1
            except Exception as e:
                fail += 1
                msgs.append(f"{opp_id} ({s['name']}): {e}")
        print(f"  {stage}: ok={ok} fail={fail}")
        return ok, fail, msgs

    print("\nApplying...")
    ok1, f1, m1 = push(to_completed, "EMA/Bulk Completed")
    ok2, f2, m2 = push(to_in_progress, "EMA/Bulk In Progress")
    print(f"\nDone: ok={ok1+ok2}  fail={f1+f2}")
    for m in (m1 + m2)[:5]:
        print(f"  ! {m}")


if __name__ == "__main__":
    main()
