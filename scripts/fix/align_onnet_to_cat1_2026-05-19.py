"""Align serviceability category to network categorization:
set Property_Category__c = 'Cat 1' on every Opportunity where
MDU_Categorization__c = 'OnNet' and Property_Category__c is not already Cat 1.

Rationale (Koa, 2026-05-19): OnNet means on the live fiber network, which
implies serviceable / Cat 1. This overrides the Vetro-computed value where
they disagree (the 3 Cat 2 cases), treating OnNet as authoritative.

Snapshots prior values for rollback + writes an audit log.
Default DRY RUN; pass --apply.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
FIELD = "Property_Category__c"
TARGET = "Cat 1"


def main(apply: bool):
    sys.stdout.reconfigure(line_buffering=True)
    c = {}
    for line in (ROOT / "api/Salesforce_Credentials.txt").read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            c[k.strip().lower()] = v.strip()
    sf = Salesforce(username=c["username"], password=c["password"], security_token=c["security token"])

    recs = sf.query_all(
        f"SELECT Id, Name, StageName, {FIELD} FROM Opportunity "
        f"WHERE MDU_Categorization__c = 'OnNet' AND {FIELD} != '{TARGET}'"
    )["records"]
    print(f"[INFO] {len(recs)} OnNet Opps not already {TARGET}")
    for r in recs:
        print(f"   {r['Name'][:50]:50} | {FIELD}={(r[FIELD] or '(blank)'):8} | stage={r['StageName']}")

    out_dir = ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = out_dir / f"onnet_cat1_rollback_{STAMP}.csv"
    with snap.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opp_id", "name", "field", "prior_value"])
        for r in recs:
            w.writerow([r["Id"], r["Name"], FIELD, r[FIELD] or ""])
    print(f"\n[INFO] Rollback snapshot: {snap}")

    if not apply:
        print("\n[DRY RUN] No writes. Re-run with --apply.")
        return

    audit_dir = out_dir / "audit_logs"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit = audit_dir / f"onnet_cat1_applied_{STAMP}.csv"
    ok = err = 0
    with audit.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
        for r in recs:
            try:
                sf.Opportunity.update(r["Id"], {FIELD: TARGET})
                ok += 1
                w.writerow([r["Id"], r["Name"], FIELD, r[FIELD] or "", TARGET,
                            "OnNet->Cat1 alignment (Koa 2026-05-19)", STAMP, "update"])
            except Exception as e:
                err += 1
                print(f"   [ERROR] {r['Name']}: {e}")
    print(f"\n[DONE] Updated: {ok}, Errors: {err}")
    print(f"Audit log: {audit}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    main(ap.parse_args().apply)
