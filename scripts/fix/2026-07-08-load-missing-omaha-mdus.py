"""
Load the 3 Omaha MDUs from the Vetro fiber list that are genuinely absent from
Salesforce (verified 2026-07-08: no existing Opp at these addresses under any name).
Creates fresh MDU/SFU Opportunities, Cat 1, owned by the active NE rep, stage Prospects.
4430 Redman links to its existing Property_Location.

Dry-run by default; --apply creates the records + writes an audit log.
"""
import argparse, csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
RT_MDU = "012WR00000Ra0mkYAB"          # RecordType MDU/SFU
OWNER = "005WR000003CD6DYAW"           # Melissa Baker (active record; her other User is inactive) - per Koa 2026-07-08
OWNER_NAME = "Melissa Baker"
CLOSE = "2026-12-31"                    # matches existing Omaha MDU Prospect convention

RECORDS = [
    dict(Name="4430 Redman Ave", agree="Omaha_MDU_4430 Redman Ave",
         addr="4430 Redman Avenue", zip="68111", units=9,
         location="a01WR00000tUtiyYAC"),  # existing Property_Location
    dict(Name="Blondo Crest Apartments", agree="Omaha_MDU_Blondo Crest Apartments",
         addr="7906 Blondo St", zip="68134", units=21, location=None),
    dict(Name="Colonial Court Apartments", agree="Omaha_MDU_Colonial Court Apartments",
         addr="4918 Ames Avenue", zip="68104", units=23, location=None),
]

def payload(r):
    p = dict(RecordTypeId=RT_MDU, OwnerId=OWNER, Name=r["Name"],
             Agreement_Name__c=r["agree"], Property_Address__c=r["addr"],
             Property_City__c="Omaha", Property_State__c="NE", Property_Zip__c=r["zip"],
             Property_Category__c="Cat 1", Units__c=r["units"],
             StageName="Prospects", CloseDate=CLOSE)
    if r["location"]:
        p["Property_Location__c"] = r["location"]
    return p

def main():
    apply = argparse.ArgumentParser(); apply.add_argument("--apply", action="store_true")
    apply = apply.parse_args().apply
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    # safety: re-confirm agree name not already taken (uniqueness trap)
    for r in RECORDS:
        dup = sf.query(f"SELECT Id,Name FROM Opportunity WHERE Agreement_Name__c = '{r['agree']}'")["records"]
        r["_dup"] = dup

    print("=== will create ===")
    for r in RECORDS:
        flag = " !! AGREE-NAME ALREADY EXISTS - SKIP" if r["_dup"] else ""
        print(f"  {r['Name']:26} | {r['addr']:22} Omaha NE {r['zip']} | {r['units']:>3}u | Cat 1 | Prospects | "
              f"owner={OWNER_NAME} | loc={'yes' if r['location'] else '-'}{flag}")

    if not apply:
        print("\nDRY RUN - pass --apply to create these Opportunities.")
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs") / f"2026-07-08-load-omaha-mdus-{stamp}.csv"
    audit.parent.mkdir(parents=True, exist_ok=True)
    written = []
    print("\ncreating...")
    for r in RECORDS:
        if r["_dup"]:
            print(f"  SKIP {r['Name']} (agree name exists: {r['_dup'][0]['Id']})"); continue
        res = sf.Opportunity.create(payload(r))
        oid = res["id"]
        written.append(dict(SF_Id=oid, Name=r["Name"], Agreement_Name=r["agree"],
                            Address=r["addr"], Units=r["units"], Category="Cat 1",
                            Stage="Prospects", Owner=OWNER_NAME,
                            Source="2026-07-08-load-missing-omaha-mdus.py",
                            Timestamp=datetime.now().isoformat(), Action="create"))
        print(f"  created {r['Name']:26} -> {oid}")
    with audit.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(written[0].keys())); w.writeheader(); w.writerows(written)
    print(f"\naudit log ({len(written)}) -> {audit}")

if __name__ == "__main__":
    main()
