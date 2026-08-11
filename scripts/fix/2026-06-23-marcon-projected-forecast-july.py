"""
Per Melissa: set a projected forecast of end-of-July on the 7 MarCon portfolio opps.
Sets Opportunity.Projected_Close_Date__c = 2026-07-31 (the team's forecast field;
standard CloseDate is NOT touched). Audited + idempotent.

Usage:  python ...py          # DRY RUN
        python ...py --apply
"""
import sys, csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


APPLY = "--apply" in sys.argv
sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])

FORECAST = "2026-07-31"
SOURCE = "2026-06-23-marcon-projected-forecast-july.py"
TS = datetime.now().isoformat()

OPPS = {
    "006WR00000xvWR0YAM": "4810-4812 Capital Ave",
    "006WR00000xv174YAA": "The Wakeley Pointe",
    "006WR00000wkA8yYAE": "78th Place Apartments (78th Street)",
    "006WR00000xwGATYA2": "California Place",
    "006WR00000wkBToYAM": "Orchard Park Apartments",
    "006WR00000wkBTuYAM": "Indian Hills Village Apartments",
    "006WR00000wk1ERYAY": "Indian Hills Terrace (Indian Hills Village Court)",
}
ids = "(" + ",".join(f"'{i}'" for i in OPPS) + ")"
opps = sf.query("SELECT Id, Name, StageName, Projected_Close_Date__c "
                "FROM Opportunity WHERE Id IN " + ids)["records"]

print(f"\n{'APPLYING' if APPLY else 'DRY RUN'} — set Projected_Close_Date__c = {FORECAST}\n")
audit = []
for o in opps:
    oid, nm = o["Id"], OPPS.get(o["Id"], o["Name"])
    before = o.get("Projected_Close_Date__c")
    if before == FORECAST:
        print(f"  skip (already {FORECAST}): {nm}")
        continue
    print(f"  [{'DID' if APPLY else 'WOULD'}] {nm:48} {before} -> {FORECAST}   (stage: {o['StageName']})")
    audit.append(("UPDATE", oid, nm, "Projected_Close_Date__c", before, FORECAST))
    if APPLY:
        sf.Opportunity.update(oid, {"Projected_Close_Date__c": FORECAST})

if audit:
    out = Path("SalesForce/data/output/audit_logs")
    out.mkdir(parents=True, exist_ok=True)
    suffix = "applied" if APPLY else "dryrun"
    fp = out / f"marcon_projected_forecast_{suffix}_{datetime.now():%Y%m%dT%H-%M-%S}.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Action", "SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp"])
        for r in audit:
            w.writerow([*r, SOURCE, TS])
    print(f"\nAudit log: {fp}  ({len(audit)} rows)")

print(f"\n{'APPLIED' if APPLY else 'DRY RUN — re-run with --apply'}.")
