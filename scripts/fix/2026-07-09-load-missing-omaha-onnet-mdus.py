"""
Load the 8 Omaha On-Net MDUs from Niraj's 227-row list that are genuinely absent from
Salesforce. Creates MDU/SFU Opportunities, Cat 1, stage Prospects, owned by the active
Melissa Baker.

Absence verified 2026-07-09 three ways, each with 4430 Redman Ave as a passing positive
control: all 4,144 Opportunities org-wide (no filter), all 18,161 Property_Locations, all
511 Accounts, plus a Name/Agreement_Name scan covering the 230 Opps with a blank
Property_Address__c.  Probe: scripts/_probes/2026-07-09-verify-omaha-missing-8.py

Existence + door counts confirmed against Vetro (hive_metastore.default.vetro_external_table),
keyed on `properties.agreename`. `properties.unitqty` is the literal string 'nan' and must
not be used; doors = distinct UNIT-bearing service_location addresses.

None of the 8 has an existing Property_Location, so none is linked (4430 Redman had one).

Dry-run by default; --apply creates the records + writes an audit log.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from lookup_agree_names_for_unlinked import house, st_tokens  # noqa: E402

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# Street-NAME tokens only. st_tokens already strips directionals and suffixes (N/S/St/Ave),
# and we drop the city/state so they cannot act as a free shared token. Matching on the raw
# last token means "N 24th St" -> "st", which matches "Westminster". That is how a naive
# guard flags 5711 W 92nd Ave, Westminster CO as a duplicate of 5711 N 24th St, Omaha.
PLACE_TOKENS = {"omaha", "ne", "nebraska", "usa", "us"}


def street_name_tokens(addr):
    return {t for t in st_tokens(addr) if not t.isdigit()} - PLACE_TOKENS

USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]

RT_MDU = "012WR00000Ra0mkYAB"       # RecordType MDU/SFU
OWNER = "005WR000003CD6DYAW"        # Melissa Baker (ACTIVE; her other User record is inactive)
OWNER_NAME = "Melissa Baker"
CLOSE = "2026-12-31"                # matches existing Omaha MDU Prospect convention

# units = Vetro door count (distinct UNIT-bearing addresses under the agreename).
# `sheet_units` = what Niraj's spreadsheet claimed, kept only to surface disagreement.
RECORDS = [
    dict(Name="4750 Lafayette Ave", agree="Omaha_MDU_4750 LAFAYETTE AVE",
         addr="4750 Lafayette Ave", zip="68132", units=23, sheet_units=23,
         note="Vetro addrstatus=serviceable (the other 7 are future_serviceable)"),
    dict(Name="Chalet Apartments", agree="Omaha_MDU_Chalet Apartments",
         addr="4728 Seward St", zip="68104", units=22, sheet_units=22,
         note="spans 4728 + 4730 Seward St; distinct from 'Chalet Izard' @ 4858 Izard"),
    dict(Name="5016 California St", agree="Omaha_MDU_5016 California St",
         addr="5016 California St", zip="68132", units=12, sheet_units=12, note=""),
    dict(Name="4314 N 65th St", agree="Omaha_MDU_4314 N 65th St",
         addr="4314 N 65th St", zip="68104", units=11, sheet_units=11,
         note="distinct from existing Opp 4313 N 65th St (opposite side of street)"),
    dict(Name="814 N 50th Ave", agree="Omaha_MDU_814 N 50th Ave",
         addr="814 N 50th Ave", zip="68132", units=8, sheet_units=9,
         note="Vetro=8 doors; its 9th tagged address is 807 N 50th ST, a different street"),
    dict(Name="914 Mercer Blvd", agree="Omaha_MDU_914 Mercer Blvd",
         addr="914 Mercer Blvd", zip="68131", units=8, sheet_units=8,
         note="Mercer Blvd absent from Property_Location master entirely"),
    dict(Name="Maple Villa Condominium", agree="Omaha_MDU_Maple Villa Condominium",
         addr="2723 N 93rd St", zip="68134", units=8, sheet_units=8,
         note="spans 2723 + 2725 N 93rd St; distinct from Lamplighter Apts @ 2715"),
    dict(Name="5711 N 24th St 6Plex", agree="Omaha_MDU_5711 N 24th St 6Plex",
         addr="5711 N 24th St", zip="68110", units=9, sheet_units=0,
         note="sheet said 0 doors (nan rollup bug); Vetro has 9 unit addrs, name implies 6"),
]


def payload(r):
    return dict(RecordTypeId=RT_MDU, OwnerId=OWNER, Name=r["Name"],
                Agreement_Name__c=r["agree"], Property_Address__c=r["addr"],
                Property_City__c="Omaha", Property_State__c="NE", Property_Zip__c=r["zip"],
                Property_Category__c="Cat 1", Units__c=r["units"],
                StageName="Prospects", CloseDate=CLOSE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    # safety 1: agree-name uniqueness (SF trap) - re-check live, not from the earlier probe
    # safety 2: nothing already sitting at this street address (same house # AND a shared
    #           street-NAME token, so 5711 N 24th St Omaha != 5711 W 92nd Ave Westminster)
    for r in RECORDS:
        r["_dup"] = sf.query(
            f"SELECT Id,Name FROM Opportunity WHERE Agreement_Name__c = '{r['agree']}'")["records"]
        h = house(r["addr"])
        want = street_name_tokens(r["addr"])
        cands = sf.query(
            f"SELECT Id,Name,Property_Address__c,Property_City__c FROM Opportunity "
            f"WHERE Property_Address__c LIKE '{h} %'")["records"]
        r["_addr_dup"] = [o for o in cands
                          if house(o["Property_Address__c"]) == h
                          and want & street_name_tokens(o["Property_Address__c"])]

    print(f"=== will create {len([r for r in RECORDS if not r['_dup'] and not r['_addr_dup']])} "
          f"of {len(RECORDS)} Opportunities ===\n")
    total = 0
    for r in RECORDS:
        block = []
        if r["_dup"]:
            block.append(f"AGREE-NAME EXISTS {r['_dup'][0]['Id']}")
        if r["_addr_dup"]:
            block.append(f"ADDRESS TAKEN by {r['_addr_dup'][0]['Name']}")
        flag = "  !! SKIP: " + "; ".join(block) if block else ""
        delta = "" if r["units"] == r["sheet_units"] else f"  (sheet said {r['sheet_units']})"
        if not block:
            total += r["units"]
        print(f"  {r['Name']:26} | {r['addr']:20} Omaha NE {r['zip']} | {r['units']:>3}u{delta}")
        print(f"  {'':26} | Cat 1 | Prospects | owner={OWNER_NAME} | no Property_Location{flag}")
        if r["note"]:
            print(f"  {'':26} | note: {r['note']}")
        print()
    print(f"total doors to be created: {total}")

    if not apply:
        print("\nDRY RUN - pass --apply to create these Opportunities.")
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = (Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
             / f"2026-07-09-load-omaha-onnet-mdus-{stamp}.csv")
    audit.parent.mkdir(parents=True, exist_ok=True)
    written = []
    print("\ncreating...")
    for r in RECORDS:
        if r["_dup"] or r["_addr_dup"]:
            print(f"  SKIP {r['Name']}")
            continue
        oid = sf.Opportunity.create(payload(r))["id"]
        written.append(dict(SF_Id=oid, Name=r["Name"], Agreement_Name=r["agree"],
                            Address=r["addr"], Zip=r["zip"], Units=r["units"],
                            Category="Cat 1", Stage="Prospects", Owner=OWNER_NAME,
                            Source="2026-07-09-load-missing-omaha-onnet-mdus.py",
                            Timestamp=datetime.now().isoformat(), Action="create"))
        print(f"  created {r['Name']:26} -> {oid}")
    if written:
        with audit.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(written[0].keys()))
            w.writeheader()
            w.writerows(written)
        print(f"\naudit log ({len(written)}) -> {audit}")
        print("rollback: delete the SF_Ids listed above")


if __name__ == "__main__":
    main()
