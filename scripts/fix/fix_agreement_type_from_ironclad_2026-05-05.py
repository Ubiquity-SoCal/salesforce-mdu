"""
Reclassify Agreement__c.Agreement_Type__c where SF disagrees with IronClad's Record Type.

Targets two specific mismatches confirmed with Koa 2026-05-05:
  - SF=EMA  + IC=Non-Exclusive Marketing Agreement  -> NEMA   (13 records)
  - SF=PAL  + IC=Right of Entry Agreement           -> ROE    (3 records)

Left as-is (legitimate per Koa):
  - ROE + Easement Agreement
  - PAL + Infrastructure and Services Agreement (likely business sales)

Run: python fix_agreement_type_from_ironclad_2026-05-05.py [--apply]
"""

import sys
import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

APPLY = "--apply" in sys.argv

REMAP = {
    ("EMA", "Non-Exclusive Marketing Agreement"): "NEMA",
    ("PAL", "Right of Entry Agreement"): "ROE",
}


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    res = sf.query_all("""
        SELECT Id, Name, Agreement_Type__c,
               IronClad_Record__r.IronClad_Id__c,
               IronClad_Record__r.Record_Type_IC__c,
               Opportunity__r.Name, Opportunity__r.RecordType.DeveloperName
        FROM Agreement__c
        WHERE IronClad_Record__c != null
        AND ((Agreement_Type__c = 'EMA' AND IronClad_Record__r.Record_Type_IC__c = 'Non-Exclusive Marketing Agreement')
             OR (Agreement_Type__c = 'PAL' AND IronClad_Record__r.Record_Type_IC__c = 'Right of Entry Agreement'))
    """)["records"]

    diffs = []
    for r in res:
        cur = r["Agreement_Type__c"]
        ic = (r.get("IronClad_Record__r") or {}).get("Record_Type_IC__c")
        new = REMAP.get((cur, ic))
        if not new:
            continue
        diffs.append({
            "id": r["Id"],
            "name": r["Name"],
            "from": cur,
            "to": new,
            "ic_name": (r.get("IronClad_Record__r") or {}).get("IronClad_Id__c"),
            "ic_type": ic,
            "opp": (r.get("Opportunity__r") or {}).get("Name", ""),
        })

    print(f"Records to fix: {len(diffs)}")
    print()
    print(f"{'AGR':<10} {'From':<5} {'To':<6} {'IC':<10} {'IC Type':<40} Opp")
    print("-" * 110)
    for d in diffs:
        print(f"  {d['name']:<8} {d['from']:<5} {d['to']:<6} {d['ic_name']:<10} {d['ic_type']:<40} {d['opp'][:35]}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = LOG_DIR / f"agr_type_fix_from_ironclad_{ts}.csv"
    action = "UPDATE" if APPLY else "PREVIEW"
    with open(audit, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Agreement_Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
        for d in diffs:
            w.writerow([
                d["id"], d["name"], "Agreement_Type__c", d["from"], d["to"],
                f"ironclad_export_2026-05-04 ({d['ic_name']}: {d['ic_type']})",
                action, datetime.now().isoformat(),
            ])
    print(f"\nAudit: {audit}")

    if not APPLY:
        print("\nPREVIEW only. Re-run with --apply to push.")
        return

    ok = fail = 0
    for d in diffs:
        try:
            sf.Agreement__c.update(d["id"], {"Agreement_Type__c": d["to"]})
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ! {d['name']}: {e}")
    print(f"\nUpdated: ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
