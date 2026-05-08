"""
Create the "9-25 MDU ROE Project" Campaign and link all matched 9-25 Opps to it.

- Idempotent on Campaign (skips create if already exists by Name).
- Skips Opps that already have this CampaignId set.
- Dry-run flag previews.

Usage:
  python assign_campaign_roe_925.py --dry-run
  python assign_campaign_roe_925.py
"""

import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from simple_salesforce import Salesforce

EXCEL_PATH = r"C:\Users\cass\OneDrive - Ubiquity Management\PMO_Projects - MDU 9-25 Units ROE Project\MDU 9 - 25 Units.xlsx"
SHEETS = ["Site Data", "TX Site Data"]
DRY_RUN = "--dry-run" in sys.argv

CAMPAIGN_CONFIG = {
    "Name": "9-25 MDU ROE Project",
    "Type": "Other",
    "Status": "In Progress",
    "IsActive": True,
    "StartDate": "2026-01-01",
    "Description": (
        "Tracks the 234 MDU 9-25 Units ROE Project properties imported from "
        "the MDU 9 - 25 Units.xlsx tracker (Site Data + TX Site Data sheets). "
        "RE team pursues ROEs on 9-25 unit properties in AZ, NE, and TX."
    ),
}

COMMON_HEADERS = ["State", "AgreeName"]


def parse_excel_agree_names(path, sheet_names):
    with zipfile.ZipFile(path, 'r') as z:
        with z.open("xl/sharedStrings.xml") as f:
            ss_tree = ET.parse(f)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings = []
        for si in ss_tree.findall(".//s:si", ns):
            parts = []
            t = si.find("s:t", ns)
            if t is not None and t.text:
                parts.append(t.text)
            for r in si.findall("s:r", ns):
                rt = r.find("s:t", ns)
                if rt is not None and rt.text:
                    parts.append(rt.text)
            strings.append("".join(parts))
        with z.open("xl/workbook.xml") as f:
            wb_tree = ET.parse(f)
        sheet_rid = {}
        for sheet_el in wb_tree.findall(".//s:sheet", ns):
            name = sheet_el.get("name")
            rid = sheet_el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            sheet_rid[name] = rid
        with z.open("xl/_rels/workbook.xml.rels") as f:
            rels_tree = ET.parse(f)
        rid_to_file = {}
        for rel in rels_tree.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
            rid_to_file[rel.get("Id")] = "xl/" + rel.get("Target")

        def col_index(ref):
            col = re.sub(r'[0-9]', '', ref)
            idx = 0
            for c in col:
                idx = idx * 26 + (ord(c) - 64)
            return idx - 1

        def cell_value(cell_el):
            v_el = cell_el.find("s:v", ns)
            val = v_el.text if v_el is not None else None
            if cell_el.get("t") == "s" and val is not None:
                return strings[int(val)]
            return val

        names = set()
        total_rows = 0
        for sheet_name in sheet_names:
            if sheet_name not in sheet_rid:
                continue
            with z.open(rid_to_file[sheet_rid[sheet_name]]) as f:
                sheet_tree = ET.parse(f)
            rows = {}
            for row_el in sheet_tree.findall(".//s:sheetData/s:row", ns):
                row_num = int(row_el.get("r"))
                cells = {}
                for cell_el in row_el.findall("s:c", ns):
                    ci = col_index(cell_el.get("r"))
                    cells[ci] = cell_value(cell_el)
                rows[row_num] = cells
            sorted_rows = sorted(rows.keys())
            if not sorted_rows:
                continue
            headers = rows[sorted_rows[0]]
            header_map = {headers[k]: k for k in headers if headers[k]}
            for rn in sorted_rows[1:]:
                state_idx = header_map.get("State")
                agree_idx = header_map.get("AgreeName")
                state = rows[rn].get(state_idx, "") if state_idx is not None else ""
                agree = rows[rn].get(agree_idx, "") if agree_idx is not None else ""
                if state and agree:
                    total_rows += 1
                    names.add(agree.strip().lower())
        return names, total_rows


def main():
    print("=" * 70)
    print(f"Assign Campaign '9-25 MDU ROE Project'  ({'DRY RUN' if DRY_RUN else 'LIVE'})")
    print("=" * 70)

    agree_keys, excel_row_count = parse_excel_agree_names(EXCEL_PATH, SHEETS)
    print(f"\nExcel rows: {excel_row_count}")
    print(f"Unique Agreement Names: {len(agree_keys)}")

    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Hawaiian1984",
        security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
    )

    # Campaign: find or create
    print(f"\nLooking up Campaign '{CAMPAIGN_CONFIG['Name']}'...")
    existing = sf.query(
        f"SELECT Id, Name, Status, Type, IsActive FROM Campaign "
        f"WHERE Name = '{CAMPAIGN_CONFIG['Name']}' LIMIT 1"
    )
    if existing["totalSize"]:
        campaign_id = existing["records"][0]["Id"]
        print(f"  Found existing: {campaign_id}")
    else:
        if DRY_RUN:
            print("  Would CREATE Campaign with config:")
            for k, v in CAMPAIGN_CONFIG.items():
                print(f"    {k}: {v}")
            campaign_id = "<new>"
        else:
            result = sf.Campaign.create(CAMPAIGN_CONFIG)
            campaign_id = result["id"]
            print(f"  Created: {campaign_id}")

    # Pull matching SF Opps
    print("\nQuerying SF MDU Opps with Agreement_Name__c...")
    result = sf.query_all(
        "SELECT Id, Name, Agreement_Name__c, CampaignId FROM Opportunity "
        "WHERE RecordType.Name = 'MDU' AND Agreement_Name__c != null"
    )
    sf_by_key = {}
    for r in result["records"]:
        sf_by_key.setdefault(r["Agreement_Name__c"].strip().lower(), []).append(r)

    # Match
    matched_opps = []
    unmatched = []
    for key in agree_keys:
        recs = sf_by_key.get(key, [])
        if recs:
            matched_opps.extend(recs)
        else:
            unmatched.append(key)

    print(f"  Matched Opps: {len(matched_opps)}")
    print(f"  Excel keys with no SF match: {len(unmatched)}")
    for k in unmatched[:10]:
        print(f"    - {k}")

    # Figure out who still needs linking
    to_update = [o for o in matched_opps if o.get("CampaignId") != campaign_id]
    already_linked = len(matched_opps) - len(to_update)
    print(f"\n  Already linked to this Campaign: {already_linked}")
    print(f"  Will link: {len(to_update)}")

    if DRY_RUN:
        print("\nDRY RUN — not updating. Re-run without --dry-run to push.")
        return

    if not to_update:
        print("\nNothing to link. Done.")
        return

    print(f"\nLinking {len(to_update)} Opps...")
    ok, errors = 0, []
    for i, opp in enumerate(to_update, 1):
        try:
            sf.Opportunity.update(opp["Id"], {"CampaignId": campaign_id})
            ok += 1
            if i % 50 == 0:
                print(f"  {i}/{len(to_update)}...")
        except Exception as e:
            errors.append((opp["Id"], opp.get("Name"), str(e)))

    print(f"\nLinked: {ok}")
    if errors:
        print(f"Errors: {len(errors)}")
        for eid, name, err in errors[:10]:
            print(f"  {eid} {name}: {err}")

    print(f"\nCampaign Id: {campaign_id}")
    print(f"Campaign URL: https://fun-power-747.lightning.force.com/lightning/r/Campaign/{campaign_id}/view")


if __name__ == "__main__":
    main()
