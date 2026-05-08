"""
Backfill Submitted_to_Market__c and Submitted_to_FiberFirst__c for the 232
9-25 Campaign Opps based on the Excel tracker.

Rule: if the Excel row has a non-blank value in the date column, flip the
corresponding checkbox to True.

Usage:
  python backfill_submission_flags_925.py --dry-run
  python backfill_submission_flags_925.py
"""

import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from simple_salesforce import Salesforce

EXCEL_PATH = r"C:\Users\cass\OneDrive - Ubiquity Management\PMO_Projects - MDU 9-25 Units ROE Project\MDU 9 - 25 Units.xlsx"
SHEETS = ["Site Data", "TX Site Data"]
CAMPAIGN_ID = "701WR00001IwJYsYAN"
DRY_RUN = "--dry-run" in sys.argv

HEADERS_NEEDED = ["State", "AgreeName", "Assign to FF Sales Date", "Assign to Market to Field"]


def parse_excel(path, sheet_names):
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
        sheet_rid = {s.get("name"): s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                     for s in wb_tree.findall(".//s:sheet", ns)}
        with z.open("xl/_rels/workbook.xml.rels") as f:
            rels_tree = ET.parse(f)
        rid_to_file = {r.get("Id"): "xl/" + r.get("Target")
                       for r in rels_tree.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")}

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

        out = []
        for sheet_name in sheet_names:
            if sheet_name not in sheet_rid:
                continue
            with z.open(rid_to_file[sheet_rid[sheet_name]]) as f:
                sheet_tree = ET.parse(f)
            rows = {}
            for row_el in sheet_tree.findall(".//s:sheetData/s:row", ns):
                rn = int(row_el.get("r"))
                cells = {}
                for c in row_el.findall("s:c", ns):
                    cells[col_index(c.get("r"))] = cell_value(c)
                rows[rn] = cells
            sorted_rows = sorted(rows.keys())
            if not sorted_rows:
                continue
            headers = rows[sorted_rows[0]]
            header_map = {headers[k]: k for k in headers if headers[k]}
            for rn in sorted_rows[1:]:
                obj = {}
                for h in HEADERS_NEEDED:
                    idx = header_map.get(h)
                    obj[h] = rows[rn].get(idx, "") if idx is not None else ""
                    if obj[h] is None:
                        obj[h] = ""
                if obj["State"] and obj["AgreeName"]:
                    out.append(obj)
        return out


def main():
    print("=" * 70)
    print(f"Backfill submission flags on 9-25 Campaign Opps  ({'DRY RUN' if DRY_RUN else 'LIVE'})")
    print("=" * 70)

    rows = parse_excel(EXCEL_PATH, SHEETS)
    print(f"\nExcel rows: {len(rows)}")

    # Build per-key desired values (if any row for this key has a date, flag is true)
    excel = {}
    for r in rows:
        key = r["AgreeName"].strip().lower()
        ff = bool((r.get("Assign to FF Sales Date") or "").strip())
        mk = bool((r.get("Assign to Market to Field") or "").strip())
        cur = excel.get(key, {"ff": False, "mk": False})
        cur["ff"] = cur["ff"] or ff
        cur["mk"] = cur["mk"] or mk
        excel[key] = cur

    ff_excel = sum(1 for v in excel.values() if v["ff"])
    mk_excel = sum(1 for v in excel.values() if v["mk"])
    print(f"  Unique keys in Excel: {len(excel)}")
    print(f"  With 'Assign to FF Sales Date' populated: {ff_excel}")
    print(f"  With 'Assign to Market to Field' populated: {mk_excel}")

    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Hawaiian1984",
        security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
    )

    q = (f"SELECT Id, Agreement_Name__c, Submitted_to_Market__c, Submitted_to_FiberFirst__c "
         f"FROM Opportunity WHERE CampaignId = '{CAMPAIGN_ID}'")
    r = sf.query_all(q)
    sf_opps = r["records"]
    print(f"\nSF Opps on Campaign: {len(sf_opps)}")

    updates = []
    for opp in sf_opps:
        key = (opp["Agreement_Name__c"] or "").strip().lower()
        want = excel.get(key)
        if not want:
            continue
        patch = {}
        if bool(opp.get("Submitted_to_FiberFirst__c")) != want["ff"]:
            patch["Submitted_to_FiberFirst__c"] = want["ff"]
        if bool(opp.get("Submitted_to_Market__c")) != want["mk"]:
            patch["Submitted_to_Market__c"] = want["mk"]
        if patch:
            updates.append((opp["Id"], opp["Agreement_Name__c"], patch))

    print(f"\nWill update {len(updates)} Opps:")
    delta_ff = sum(1 for _, _, p in updates if "Submitted_to_FiberFirst__c" in p and p["Submitted_to_FiberFirst__c"])
    delta_mk = sum(1 for _, _, p in updates if "Submitted_to_Market__c" in p and p["Submitted_to_Market__c"])
    print(f"  setting Submitted_to_FiberFirst__c=True: {delta_ff}")
    print(f"  setting Submitted_to_Market__c=True:    {delta_mk}")

    for oid, name, p in updates[:15]:
        print(f"    {oid}  {name[:55]:55}  {p}")
    if len(updates) > 15:
        print(f"    ... and {len(updates) - 15} more")

    if DRY_RUN:
        print("\nDRY RUN — no writes. Re-run without --dry-run to apply.")
        return

    ok, errs = 0, []
    for oid, name, p in updates:
        try:
            sf.Opportunity.update(oid, p)
            ok += 1
        except Exception as e:
            errs.append((oid, name, str(e)))
    print(f"\nUpdated: {ok}")
    if errs:
        print(f"Errors: {len(errs)}")
        for e in errs[:10]:
            print(f"  {e[0]} {e[1]}: {e[2]}")


if __name__ == "__main__":
    main()
