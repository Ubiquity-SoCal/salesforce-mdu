"""
Delete the 6 MANUAL duplicate Agreement__c records confirmed by
_probes/2026-07-08-agreement-dup-pattern-scan.py. Each of these 6 Opportunities
carries one manual ROE/PAL record and an IronClad-synced twin of the same type;
we keep the IronClad record (authoritative: IC link + status) and delete the manual.

Safety:
  * dry-run by default; pass --apply to actually delete.
  * snapshots ALL 12 records (both sides of every pair, every field) to CSV first.
  * before each delete, re-verifies live: target has NO IronClad_ID__c, its sibling
    under the same Opp+Type DOES, and the Opp holds exactly those 2 agreements.
    Any mismatch -> skip that record and report (never force).
Read the candidates CSV produced by the scan for the record list.
"""
import csv, sys, argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
CAND = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\2026-07-08-agreement-dup-candidates.csv")
OUTDIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    rows = [r for r in csv.DictReader(CAND.open(encoding="utf-8"))
            if r["bucket"] == "manual+ironclad"]
    by_opp = defaultdict(list)
    for r in rows:
        by_opp[r["opp_id"]].append(r)

    # build delete plan: manual (no IC) is target, IC one is keeper
    # NOTE: in the scan CSV, column "agr_name" holds the real 18-char Id and
    # column "agr_id" holds the AGR-#### Name (they were written swapped).
    plan = []  # (opp_id, opp_name, type, target_agr_id, target_agr_name, keeper_agr_id)
    for opp, grp in by_opp.items():
        man = [r for r in grp if not r["ironclad_id"]]
        ic  = [r for r in grp if r["ironclad_id"]]
        if len(grp) == 2 and len(man) == 1 and len(ic) == 1:
            plan.append((opp, grp[0]["opp_name"], grp[0]["agr_type"],
                         man[0]["agr_name"], man[0]["agr_id"], ic[0]["agr_name"]))
        else:
            print(f"!! SKIP {grp[0]['opp_name']}: unexpected shape "
                  f"({len(man)} manual / {len(ic)} IC) - not a clean pair")
    print(f"delete plan: {len(plan)} manual records\n")

    # ---- snapshot every involved record, all fields ----
    all_ids = [p[3] for p in plan] + [p[5] for p in plan]
    fields = [f["name"] for f in sf.Agreement__c.describe()["fields"]]
    idlist = "','".join(all_ids)
    snap = sf.query_all(f"SELECT {','.join(fields)} FROM Agreement__c WHERE Id IN ('{idlist}')")["records"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapfile = OUTDIR / f"2026-07-08-agreement-dup-snapshot-{stamp}.csv"
    with snapfile.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in snap:
            w.writerow({k: rec.get(k) for k in fields})
    print(f"snapshot ({len(snap)} records) -> {snapfile}\n")

    # ---- per-record live verification ----
    confirmed = []
    for opp, oppname, typ, tgt, tgtname, keeper in plan:
        t = sf.Agreement__c.get(tgt)
        k = sf.Agreement__c.get(keeper)
        siblings = sf.query_all(
            f"SELECT Id, IronClad_ID__c FROM Agreement__c "
            f"WHERE Opportunity__c='{opp}' AND Agreement_Type__c='{typ}'")["records"]
        ok = (not t["IronClad_ID__c"]) and bool(k["IronClad_ID__c"]) \
             and k["Agreement_Type__c"] == typ and len(siblings) == 2
        flag = "OK" if ok else "*** VERIFY FAILED - SKIP ***"
        print(f"  [{flag}] {oppname[:30]:30} {typ}  del {tgtname}({tgt}) "
              f"keep {k['Name']}(IC:{k['IronClad_ID__c']})")
        if ok:
            confirmed.append((tgt, oppname, tgtname))

    print(f"\n{len(confirmed)}/{len(plan)} records verified for deletion")
    if not apply:
        print("\nDRY RUN — pass --apply to delete the verified records."); return

    print("\napplying deletes...")
    for tgt, oppname, tgtname in confirmed:
        sf.Agreement__c.delete(tgt)
        print(f"  deleted {tgtname} ({tgt})  [{oppname}]")

    # ---- post-verify: each opp now has 1 agreement of that type ----
    print("\npost-check Agreement_Count__c:")
    for opp, oppname, typ, *_ in plan:
        o = sf.Opportunity.get(opp)
        print(f"  {oppname[:32]:32} Agreement_Count__c = {o.get('Agreement_Count__c')}")

if __name__ == "__main__":
    main()
