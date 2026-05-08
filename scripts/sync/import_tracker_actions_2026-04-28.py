"""
Read the Weekly Tracker xlsb and map Status -> Next_Action__c on matching SF Opportunities.

Match strategy:
  1. By SiteTracker Project ID (P-XXXX) -> Opportunity.SiteTracker_Project_ID__c
  2. Fallback: by Site Name -> Opportunity.Agreement_Name__c
  3. Fallback: fuzzy by Site Name -> Opportunity.Name

Sets Next_Action__c = Status text.
Sets Next_Action_Date__c = today (best signal we have for "when was this updated").

Run: python import_tracker_actions_2026-04-28.py [--apply]
Without --apply, prints diff only.
"""

import sys
import csv
import pyxlsb
from datetime import date, datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

TRACKER = Path("C:/Users/cass/Downloads/MDU Projects - Weekly Tracker (2).xlsb")
LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

APPLY = "--apply" in sys.argv


def read_tracker():
    rows = []
    with pyxlsb.open_workbook(str(TRACKER)) as wb:
        with wb.get_sheet("Sales Pipeline") as sheet:
            for i, row in enumerate(sheet.rows()):
                if i == 0:
                    continue
                cells = {c.c: c.v for c in row}
                if not cells.get(0):
                    continue
                rows.append({
                    "project_id": cells.get(0),
                    "owner": cells.get(4),
                    "site_name": cells.get(5),
                    "status": cells.get(6),
                    "units": cells.get(7),
                    "address": cells.get(12),
                })
    return rows


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    rows = read_tracker()
    print(f"Tracker rows: {len(rows)}")

    # Pull MDU Opps with key fields
    soql = """
        SELECT Id, Name, SiteTracker_Project_ID__c, Agreement_Name__c,
               Next_Action__c, Next_Action_Date__c, Owner.Name, StageName
        FROM Opportunity
        WHERE RecordType.DeveloperName = 'MDU'
    """
    opps = sf.query_all(soql)["records"]
    by_st_id = {o["SiteTracker_Project_ID__c"]: o for o in opps if o.get("SiteTracker_Project_ID__c")}
    by_agr_name = {o["Agreement_Name__c"]: o for o in opps if o.get("Agreement_Name__c")}
    by_name = {(o["Name"] or "").strip().lower(): o for o in opps}
    print(f"Pulled {len(opps)} MDU Opps")

    # Also check ST Project link table (some ST Project IDs might not be denormalized to Opp)
    st_records = sf.query_all(
        "SELECT Name, Opportunity__c FROM SiteTracker_Project__c WHERE Opportunity__c != NULL"
    )["records"]
    st_to_opp = {r["Name"]: r["Opportunity__c"] for r in st_records}
    opp_by_id = {o["Id"]: o for o in opps}

    matched = []
    unmatched = []

    for r in rows:
        pid = r["project_id"]
        site = r["site_name"]
        status = r["status"]
        if not status or not str(status).strip():
            continue

        # 1. Try ST Project ID -> SiteTracker_Project_ID__c (the salesforce ST ID)
        opp = None
        method = ""
        # The pid from tracker is "P-XXXX" but SF's SiteTracker_Project_ID__c is the SF Id (a2X...)
        # Try via ST Project Name lookup
        if pid in st_to_opp:
            opp = opp_by_id.get(st_to_opp[pid])
            method = "ST Project Name -> Opp"
        # 2. Try Site Name -> Agreement_Name__c
        if not opp and site and site in by_agr_name:
            opp = by_agr_name[site]
            method = "Agreement_Name match"
        # 3. Try Site Name -> Opportunity.Name
        if not opp and site:
            opp = by_name.get(site.strip().lower())
            if opp:
                method = "Opp Name match"
        # 4. Fuzzy: site name contained in opp name
        if not opp and site:
            site_lc = site.strip().lower()
            for name, candidate in by_name.items():
                if site_lc in name or name in site_lc:
                    opp = candidate
                    method = "fuzzy name match"
                    break

        if opp:
            matched.append({
                "tracker_pid": pid,
                "tracker_site": site,
                "tracker_status": str(status),
                "sf_id": opp["Id"],
                "sf_name": opp["Name"],
                "sf_stage": opp.get("StageName"),
                "sf_owner": (opp.get("Owner") or {}).get("Name"),
                "current_action": opp.get("Next_Action__c"),
                "current_action_date": opp.get("Next_Action_Date__c"),
                "method": method,
            })
        else:
            unmatched.append(r)

    print(f"\nMatched: {len(matched)}  Unmatched: {len(unmatched)}")
    print(f"\nMatches:")
    print(f"{'Tracker Project':<12} {'Site':<45} {'-> SF Opp':<35} {'Method':<25}")
    print("-" * 130)
    for m in matched:
        site = (m["tracker_site"] or "")[:43]
        sf_name = m["sf_name"][:33]
        print(f"{str(m['tracker_pid']):<12} {site:<45} {sf_name:<35} {m['method']:<25}")
        print(f"  CURRENT action: {(m['current_action'] or '(blank)')[:120]}")
        print(f"  NEW action:     {m['tracker_status'][:120]}")
        print()

    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}):")
        for r in unmatched:
            print(f"  {r['project_id']}  {r['site_name']}")

    # Audit CSV
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = LOG_DIR / f"tracker_action_import_{ts}.csv"
    today_str = date.today().strftime("%Y-%m-%d")
    with open(audit, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "SF_Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
        for m in matched:
            action_label = "UPDATE" if APPLY else "PREVIEW"
            w.writerow([
                m["sf_id"], m["sf_name"], "Next_Action__c",
                m["current_action"] or "", m["tracker_status"],
                "tracker_xlsb_2026-04-28", action_label, datetime.now().isoformat(),
            ])
            w.writerow([
                m["sf_id"], m["sf_name"], "Next_Action_Date__c",
                m["current_action_date"] or "", today_str,
                "tracker_xlsb_2026-04-28", action_label, datetime.now().isoformat(),
            ])
    print(f"\nAudit: {audit}")

    if not APPLY:
        print("\nPREVIEW only. Re-run with --apply to push.")
        return

    # Apply
    ok = fail = 0
    for m in matched:
        try:
            sf.Opportunity.update(m["sf_id"], {
                "Next_Action__c": m["tracker_status"][:255],  # text(255) likely
                "Next_Action_Date__c": today_str,
            })
            ok += 1
        except Exception as e:
            print(f"  ! {m['sf_name']}: {e}")
            fail += 1
    print(f"\nDone: ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
