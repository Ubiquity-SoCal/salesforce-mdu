"""
Set IronClad_ID__c = 'N/A' on addendum-type Agreement records that have no IronClad ID.

Per Taylor (Salesforce sync meeting 2026-06-01): addendum agreements ride on their parent
agreement and never get their own IronClad ID. Leaving the field blank makes them show up
falsely on the "Need IronClad ID - Signed" cleanup report. Stamping 'N/A' clears that noise.

Scope: Agreement_Type__c in the addendum set, IronClad_ID__c blank. Primary types
(PAL/ROE/EMA/Bulk) are intentionally NOT touched: a blank IC ID there is a real gap.

Snapshots every affected record to an audit log first (rollback). Preview by default;
pass --apply to write. Creds from env.
"""
import os, sys, csv, argparse
from datetime import datetime, timezone
from simple_salesforce import Salesforce

ADDENDUM_TYPES = ["PAL Addendum", "MSA Addendum", "2nd ISP MSA Addendum"]
NA = "N/A"
AUDIT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output", "audit_logs")


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
    intypes = "','".join(ADDENDUM_TYPES)
    soql = (f"SELECT Id, Name, Agreement_Type__c, Status__c, IronClad_ID__c, Opportunity__r.Name "
            f"FROM Agreement__c WHERE Agreement_Type__c IN ('{intypes}') "
            f"AND (IronClad_ID__c = null OR IronClad_ID__c = '')")
    recs = sf.query_all(soql)["records"]
    print(f"Addendum agreements with blank IronClad ID: {len(recs)}")
    from collections import Counter
    by = Counter(r["Agreement_Type__c"] for r in recs)
    for t, c in by.most_common():
        print(f"   {t}: {c}")

    if not recs:
        print("Nothing to do."); return

    # audit log
    os.makedirs(AUDIT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit = os.path.join(AUDIT_DIR, f"agr_na_ironclad_id_addendums_{stamp}.csv")
    with open(audit, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["SF_Id", "Name", "Opportunity", "Agreement_Type", "Status",
                    "Field", "Before", "After", "Source", "Timestamp", "Action"])
        for r in recs:
            w.writerow([r["Id"], r["Name"], (r.get("Opportunity__r") or {}).get("Name", ""),
                        r["Agreement_Type__c"], r["Status__c"], "IronClad_ID__c",
                        r.get("IronClad_ID__c") or "", NA,
                        "2026-06-01 Taylor mtg: addendums have no own IC ID", stamp,
                        "update" if args.apply else "preview"])
    print(f"\nAudit log -> {os.path.relpath(audit)}")

    if not args.apply:
        print("\nPREVIEW only. Re-run with --apply to write 'N/A'.")
        return

    data = [{"Id": r["Id"], "IronClad_ID__c": NA} for r in recs]
    res = sf.bulk.Agreement__c.update(data)
    errs = [x for x in res if not x.get("success")]
    print(f"APPLIED: {len(res) - len(errs)} updated, {len(errs)} errors")
    for e in errs[:10]:
        print("   ERR", e)


if __name__ == "__main__":
    main()
