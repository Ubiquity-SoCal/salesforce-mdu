"""
Refresh Agreement__c Status (and Signed_Date) from current Monday.com state.
Skips any Agreement that already has IronClad_ID (those came from IronClad sync).

Logic mirrors migration_phase2_agreements.py:
  - PAL: Monday status_19 + date0
  - EMA: Monday status_18 + date3
  - Bulk: Monday color5
  - PAL Addendum, MSA Addendum, 2nd ISP NEMA, 2nd ISP MSA: signed-date-only

Run: python refresh_agreement_status_from_monday_2026-04-28.py [--apply]
Without --apply, prints diff only.
"""

import json
import sys
import time
from datetime import datetime
from collections import Counter
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

MONDAY_PULL = Path("C:/Users/cass/Work_Projects/Monday.com/fresh_pull_20260424.json")
LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

APPLY = "--apply" in sys.argv

STAGE_TO_STATUS = {
    "Signed": "Completed",
    "Signed - 3rd Party / Tenant": "Completed",
    "Owner-Signed PAL": "Completed",
    "ROE Signed": "Completed",
    "Out for Signature": "Sign",
    "Under Client Review": "Review",
    "Pending - 3rd Party / Tenant": "Review",
    "On Hold": "Paused",
    "Dead/Lost": "Cancelled",
    "Terminated": "Cancelled",
    "Existing EMA": "Archive",
    "No Agreement Desired": "Cancelled",
}
SKIP_VALUES = {"", "N/A - Bulk", "N/A - Retail MA"}

TYPE_TO_COLS = {
    "PAL":  {"stage": "status_19", "date": "date0"},
    "EMA":  {"stage": "status_18", "date": "date3"},
    "Bulk": {"stage": "color5",    "date": None},
    "PAL Addendum":         {"stage": None, "date": "date7"},
    "MSA Addendum":         {"stage": None, "date": "date07"},
    "2nd ISP NEMA":         {"stage": None, "date": "date_mktzmpzk"},
    "2nd ISP MSA Addendum": {"stage": None, "date": "date_mkrsd2n"},
}


def get_col(item, col_id):
    if not col_id:
        return ""
    for cv in item.get("column_values", []):
        if cv["id"] == col_id:
            return (cv.get("text") or "").strip()
    return ""


def parse_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(d.strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def expected_status_and_date(item, agr_type):
    cols = TYPE_TO_COLS.get(agr_type)
    if not cols:
        return None, None  # unknown type, skip
    stage = get_col(item, cols["stage"]) if cols["stage"] else ""
    signed = parse_date(get_col(item, cols["date"])) if cols["date"] else None

    if cols["stage"]:
        if stage in SKIP_VALUES and not signed:
            return None, None  # nothing to set
        status = STAGE_TO_STATUS.get(stage, "Create") if stage and stage not in SKIP_VALUES else None
        if signed:
            if status not in ("Completed", "Archive"):
                status = "Completed"
        return status, signed
    else:
        # Date-only types (Addendums, 2nd ISP)
        if signed:
            return "Completed", signed
        return None, None


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("Connected to Salesforce")

    items = json.loads(MONDAY_PULL.read_text(encoding="utf-8"))
    by_monday_id = {str(it["id"]): it for it in items}
    print(f"Loaded {len(items)} Monday items from {MONDAY_PULL.name}")

    # Pull MDU Agreements WITHOUT IronClad ID + their Opp's Monday ID
    soql = """
        SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c, IronClad_ID__c,
               Opportunity__c, Opportunity__r.Name, Opportunity__r.Monday_Item_ID__c
        FROM Agreement__c
        WHERE Opportunity__r.RecordType.DeveloperName = 'MDU'
          AND IronClad_ID__c = NULL
    """
    res = sf.query_all(soql)
    agrs = res["records"]
    print(f"Pulled {len(agrs)} MDU Agreements without IronClad_ID")

    diffs = []  # (sf_id, opp_name, type, current_status, new_status, current_signed, new_signed)
    skipped_no_monday = 0
    skipped_no_change = 0

    for a in agrs:
        opp = a.get("Opportunity__r") or {}
        monday_id = opp.get("Monday_Item_ID__c")
        if not monday_id or monday_id not in by_monday_id:
            skipped_no_monday += 1
            continue
        item = by_monday_id[monday_id]
        agr_type = a.get("Agreement_Type__c")
        new_status, new_signed = expected_status_and_date(item, agr_type)
        if not new_status:
            skipped_no_change += 1
            continue
        cur_status = a.get("Status__c")
        cur_signed = a.get("Signed_Date__c")
        if new_status == cur_status and new_signed == cur_signed:
            skipped_no_change += 1
            continue
        diffs.append({
            "Id": a["Id"],
            "Name": a["Name"],
            "OppName": opp.get("Name") or "",
            "Type": agr_type,
            "FromStatus": cur_status,
            "ToStatus": new_status,
            "FromSigned": cur_signed,
            "ToSigned": new_signed,
        })

    print(f"\nSkipped (no Monday match): {skipped_no_monday}")
    print(f"Skipped (no change):      {skipped_no_change}")
    print(f"DIFFS to apply:           {len(diffs)}")

    # Status transition summary
    transitions = Counter((d["FromStatus"], d["ToStatus"]) for d in diffs)
    print("\nStatus transitions (top 20):")
    for (frm, to), c in transitions.most_common(20):
        print(f"  {str(frm):<14} -> {str(to):<14}  {c}")

    type_counts = Counter(d["Type"] for d in diffs)
    print("\nBy Agreement Type:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    # Sample
    print("\nSample diffs (first 10):")
    for d in diffs[:10]:
        print(f"  {d['Name']}  {d['OppName'][:35]:<35}  {d['Type']:<14}  "
              f"{str(d['FromStatus']):<10} -> {str(d['ToStatus']):<10}  "
              f"signed: {d['FromSigned']} -> {d['ToSigned']}")

    # Write audit CSV
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit_path = LOG_DIR / f"agreement_status_refresh_{ts}.csv"
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write("SF_Id,Name,OppName,Type,FromStatus,ToStatus,FromSigned,ToSigned,Source,Action,Timestamp\n")
        action = "UPDATE" if APPLY else "PREVIEW"
        for d in diffs:
            f.write(f"{d['Id']},{d['Name']},\"{d['OppName']}\",{d['Type']},"
                    f"{d['FromStatus']},{d['ToStatus']},{d['FromSigned']},{d['ToSigned']},"
                    f"Monday.com fresh_pull_20260424,{action},{datetime.now().isoformat()}\n")
    print(f"\nAudit written: {audit_path}")

    if not APPLY:
        print("\nPREVIEW ONLY. Re-run with --apply to push updates.")
        return

    # Apply via bulk update
    print(f"\nApplying {len(diffs)} updates...")
    batch_size = 200
    updates = []
    for d in diffs:
        rec = {"Id": d["Id"], "Status__c": d["ToStatus"]}
        if d["ToSigned"]:
            rec["Signed_Date__c"] = d["ToSigned"]
        updates.append(rec)

    total_ok = 0
    total_fail = 0
    fail_msgs = []
    start = time.time()
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]
        try:
            results = sf.bulk.Agreement__c.update(batch, batch_size=batch_size)
            for r in results:
                if r.get("success"):
                    total_ok += 1
                else:
                    total_fail += 1
                    fail_msgs.append(str(r.get("errors", "?")))
        except Exception as e:
            print(f"  bulk failed, falling back: {e}")
            for rec in batch:
                try:
                    sf.Agreement__c.update(rec["Id"], {k: v for k, v in rec.items() if k != "Id"})
                    total_ok += 1
                except Exception as e2:
                    total_fail += 1
                    fail_msgs.append(str(e2))
        elapsed = time.time() - start
        print(f"  batch {i // batch_size + 1}: ok={total_ok} fail={total_fail} ({elapsed:.0f}s)")

    print(f"\nDone in {time.time() - start:.0f}s. ok={total_ok}  fail={total_fail}")
    if fail_msgs[:5]:
        print("Sample failures:")
        for m in fail_msgs[:5]:
            print(f"  {m}")


if __name__ == "__main__":
    main()
