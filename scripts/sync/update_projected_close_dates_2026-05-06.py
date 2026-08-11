"""
Update Opportunity.Projected_Close_Date__c from the Weekly Tracker xlsb.

Source: C:/Users/cass/Downloads/MDU Projects - Weekly Tracker (4).xlsb
Field: Projected_Close_Date__c (custom). Standard CloseDate is NOT touched.

Match strategy (same as import_tracker_actions_2026-04-28.py):
  1. Tracker Project ID (P-XXXX) -> SiteTracker_Project__c.Name -> Opportunity__c
  2. Site Name -> Opportunity.Agreement_Name__c
  3. Site Name -> Opportunity.Name (exact, case-insensitive)
  4. Fuzzy: tracker site contained in / containing Opp Name

Run: python update_projected_close_dates_2026-05-06.py [--apply]
Default = preview only (writes audit CSV with Action=PREVIEW).
"""

import sys
import csv
import pyxlsb
from datetime import date, datetime, timedelta
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]

TRACKER = Path("C:/Users/cass/Downloads/MDU Projects - Weekly Tracker (4).xlsb")
LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

APPLY = "--apply" in sys.argv

EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_to_iso(serial):
    if serial is None:
        return None
    return (EXCEL_EPOCH + timedelta(days=float(serial))).strftime("%Y-%m-%d")


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
                    "site_name": cells.get(5),
                    "target_serial": cells.get(8),
                    "target_iso": excel_to_iso(cells.get(8)),
                })
    return rows


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    rows = read_tracker()
    print(f"Tracker rows: {len(rows)}")

    soql = """
        SELECT Id, Name, Agreement_Name__c, Projected_Close_Date__c,
               Owner.Name, StageName
        FROM Opportunity
        WHERE RecordType.DeveloperName = 'MDU'
    """
    opps = sf.query_all(soql)["records"]
    by_agr_name = {o["Agreement_Name__c"]: o for o in opps if o.get("Agreement_Name__c")}
    by_name = {(o["Name"] or "").strip().lower(): o for o in opps}
    opp_by_id = {o["Id"]: o for o in opps}
    print(f"Pulled {len(opps)} MDU Opps")

    st_records = sf.query_all(
        "SELECT Name, Opportunity__c FROM SiteTracker_Project__c WHERE Opportunity__c != NULL"
    )["records"]
    st_to_opp = {r["Name"]: r["Opportunity__c"] for r in st_records}

    matched = []
    unmatched = []

    for r in rows:
        pid = r["project_id"]
        site = r["site_name"]
        new_date = r["target_iso"]
        if not new_date:
            continue

        opp = None
        method = ""
        if pid in st_to_opp:
            opp = opp_by_id.get(st_to_opp[pid])
            method = "ST Project Name -> Opp"
        if not opp and site and site in by_agr_name:
            opp = by_agr_name[site]
            method = "Agreement_Name match"
        if not opp and site:
            opp = by_name.get(site.strip().lower())
            if opp:
                method = "Opp Name match"
        if not opp and site:
            site_lc = site.strip().lower()
            for name, candidate in by_name.items():
                if site_lc in name or name in site_lc:
                    opp = candidate
                    method = "fuzzy name match"
                    break

        if opp:
            current = opp.get("Projected_Close_Date__c")
            matched.append({
                "tracker_pid": pid,
                "tracker_site": site,
                "new_date": new_date,
                "sf_id": opp["Id"],
                "sf_name": opp["Name"],
                "sf_stage": opp.get("StageName"),
                "sf_owner": (opp.get("Owner") or {}).get("Name"),
                "current_date": current,
                "changed": (current or "") != new_date,
                "method": method,
            })
        else:
            unmatched.append(r)

    changes = [m for m in matched if m["changed"]]
    nochange = [m for m in matched if not m["changed"]]

    print(f"\nMatched: {len(matched)}  (changes: {len(changes)}, no-op: {len(nochange)})  Unmatched: {len(unmatched)}")
    print()
    print(f"{'PID':<10} {'Site':<45} {'-> SF Opp':<35} {'Current':<12} {'New':<12} {'Method':<22}")
    print("-" * 140)
    for m in matched:
        site = (m["tracker_site"] or "")[:43]
        sf_name = (m["sf_name"] or "")[:33]
        flag = "  " if not m["changed"] else "* "
        print(f"{flag}{str(m['tracker_pid']):<8} {site:<45} {sf_name:<35} {str(m['current_date'] or ''):<12} {m['new_date']:<12} {m['method']:<22}")

    if unmatched:
        print(f"\nUnmatched ({len(unmatched)}):")
        for r in unmatched:
            print(f"  {r['project_id']}  {r['site_name']}  -> {r['target_iso']}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = LOG_DIR / f"projected_close_date_update_{ts}.csv"
    with open(audit, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "SF_Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
        for m in matched:
            if not m["changed"]:
                continue
            action_label = "UPDATE" if APPLY else "PREVIEW"
            w.writerow([
                m["sf_id"], m["sf_name"], "Projected_Close_Date__c",
                m["current_date"] or "", m["new_date"],
                "tracker_xlsb_2026-05-06", action_label, datetime.now().isoformat(),
            ])
    print(f"\nAudit: {audit}")

    if not APPLY:
        print("\nPREVIEW only. Re-run with --apply to push.")
        return

    ok = fail = 0
    for m in changes:
        try:
            sf.Opportunity.update(m["sf_id"], {
                "Projected_Close_Date__c": m["new_date"],
            })
            ok += 1
        except Exception as e:
            print(f"  ! {m['sf_name']}: {e}")
            fail += 1
    print(f"\nDone: ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
