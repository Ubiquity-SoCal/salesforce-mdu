"""Create the missing PAL Agreement__c on Opp '1810 N 8th St_Colt RE'
(006WR000013P1ulYAC). 1810 shares a PAL with its twin 1807 Mulford
(AGR-0949, signed 2026-03-12); this mirrors that record.

Source: Signed MDU Agreement Analysis V1.xlsx, P-006826
(PAL Status 'MDUs On Net - Access Agreement Complete').

Default DRY RUN; pass --apply to create. Logs to audit_logs/.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
OPP = "006WR000013P1ulYAC"
FIELDS = {
    "Opportunity__c": OPP,
    "Agreement_Type__c": "PAL",
    "Status__c": "Completed",
    "Signed_Date__c": "2026-03-12",
}
PROVENANCE = ("Created 2026-05-19 from Signed MDU Agreement Analysis V1.xlsx (P-006826). "
             "Mirrors twin 1807 Mulford PAL AGR-0949. 1807 & 1810 share one access agreement.")


def main(apply: bool):
    sys.stdout.reconfigure(line_buffering=True)
    c = {}
    for line in (ROOT / "api/Salesforce_Credentials.txt").read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            c[k.strip().lower()] = v.strip()
    sf = Salesforce(username=c["username"], password=c["password"], security_token=c["security token"])

    # Guard: don't double-create
    existing = sf.query(
        f"SELECT Id, Name FROM Agreement__c WHERE Opportunity__c='{OPP}' AND Agreement_Type__c='PAL'"
    )["records"]
    if existing:
        print(f"[ABORT] A PAL agreement already exists on this Opp: {existing[0]['Name']} ({existing[0]['Id']})")
        return

    fields = dict(FIELDS)
    has_notes = any(f["name"] == "Notes__c" for f in sf.Agreement__c.describe()["fields"])
    if has_notes:
        fields["Notes__c"] = PROVENANCE

    print("[PLAN] Create Agreement__c with:")
    for k, v in fields.items():
        print(f"   {k}: {v!r}")

    if not apply:
        print("\n[DRY RUN] No record created. Re-run with --apply.")
        return

    res = sf.Agreement__c.create(fields)
    new_id = res["id"]
    print(f"\n[CREATED] Agreement__c {new_id} (success={res['success']})")

    audit_dir = ROOT / "data" / "output" / "audit_logs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"pal_agreement_1810_n_8th_{STAMP}.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
        w.writerow([new_id, "(new PAL)", "Agreement__c", "(none)",
                    "PAL/Completed/2026-03-12 on 1810 N 8th St_Colt RE",
                    "Signed MDU Agreement Analysis V1.xlsx P-006826", STAMP, "create"])
    print(f"Audit log: {audit_path}")

    # Verify rollup
    o = sf.Opportunity.get(OPP)
    print(f"[VERIFY] Opp Agreement_Count__c now: {o.get('Agreement_Count__c')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    main(ap.parse_args().apply)
