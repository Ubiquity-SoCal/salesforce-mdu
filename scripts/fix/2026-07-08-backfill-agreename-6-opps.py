"""
Backfill Opportunity.Agreement_Name__c (the SiteTracker linking key) on the 6 Opps
that had the manual+IronClad dup, so the nightly SoCal-Automation link job can wire
them to their SiteTracker site. Reuses the tested ST-address/name matcher from
analysis/lookup_agree_names_for_unlinked.py (ST Site.Name is the authoritative value).

  * dry-run by default; --apply writes only HIGH-confidence matches into a currently
    BLANK Agreement_Name__c. MED / none are reported for human follow-up, never written.
Read-only ST + Vetro; --apply writes only Opportunity.Agreement_Name__c on the main org.
"""
import csv, sys, argparse
from pathlib import Path
from simple_salesforce import Salesforce

sys.path.insert(0, str(Path(r"C:\Users\cass\Work_Projects\SalesForce\scripts\analysis")))
from lookup_agree_names_for_unlinked import build_indexes, resolve, norm_state

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
CAND = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\2026-07-08-agreement-dup-candidates.csv")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    opp_ids = sorted({r["opp_id"] for r in csv.DictReader(CAND.open(encoding="utf-8"))
                      if r["bucket"] == "manual+ironclad"})
    idlist = "','".join(opp_ids)
    opps = sf.query_all(
        f"SELECT Id, Name, Property_Address__c, Property_State__c, Agreement_Name__c "
        f"FROM Opportunity WHERE Id IN ('{idlist}')")["records"]

    print("building ST + Vetro indexes...")
    vidx, by_house, by_state = build_indexes()
    print()

    writes = []
    for o in opps:
        st = norm_state(o["Property_State__c"])
        agree, src, conf = resolve(o["Name"], o["Property_Address__c"], st, vidx, by_house, by_state)
        cur = o["Agreement_Name__c"]
        action = "-"
        if conf == "HIGH" and not cur:
            action = "WILL WRITE"; writes.append((o["Id"], o["Name"], agree))
        elif cur:
            action = f"already set ({cur})"
        elif conf in ("MED",):
            action = "REVIEW (MED - not auto-written)"
        else:
            action = "no ST site - can't link"
        print(f"  {o['Name'][:30]:30} [{conf:4}] {str(o['Property_Address__c'])[:24]:24} "
              f"=> {agree[:40]:40} | {action}")

    print(f"\n{len(writes)} Opp(s) to backfill (HIGH + currently blank)")
    if not apply:
        print("DRY RUN — pass --apply to write Agreement_Name__c."); return

    print("\nwriting Agreement_Name__c...")
    for oid, name, agree in writes:
        sf.Opportunity.update(oid, {"Agreement_Name__c": agree})
        print(f"  {name}: Agreement_Name__c = {agree}")

    print("\npost-check:")
    chk = sf.query_all(f"SELECT Name, Agreement_Name__c FROM Opportunity WHERE Id IN ('{idlist}')")["records"]
    for c in chk:
        print(f"  {c['Name'][:32]:32} -> {c['Agreement_Name__c']}")

if __name__ == "__main__":
    main()
