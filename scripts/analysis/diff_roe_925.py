"""
Diff 9-25 Units Excel vs Salesforce.

Read-only. Produces:
  - Net-new rows in Excel not in SF (insert candidates)
  - Rows in SF matching Excel with field drift (update candidates)
  - SF Opps that look like 9-25 imports but are no longer in the Excel

Match key: Agreement_Name__c (case/space-insensitive) — same as import script.
"""

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date
from collections import Counter, defaultdict
from simple_salesforce import Salesforce

EXCEL_PATH = r"C:\Users\cass\OneDrive - Ubiquity Management\PMO_Projects - MDU 9-25 Units ROE Project\MDU 9 - 25 Units.xlsx"
SHEETS = ["Site Data", "TX Site Data"]
OUTPUT = r"C:\Users\cass\Work_Projects\SalesForce\scripts\analysis\roe_925_diff.json"

RE_ASSIGNED_MAP = {
    "RS": "005WR0000030R9lYAE",
    "TF": "005WR0000030R1hYAE",
    "JB": "005WR0000030RCzYAM",
}
RE_ID_TO_INITIALS = {v: k for k, v in RE_ASSIGNED_MAP.items()}

STAGE_MAP = {
    "Completed": "ROE Secured",
    "Engaged": "Prospecting",
    "Proposal Sent": "Prospecting",
    "Pending Signature": "Prospecting",
    "Research Required": "Prospecting",
    "Data Issue": "Prospecting",
    "Assigned FiberFirst": "Prospecting",
    "Closed - Lost": "Closed Lost",
    "Closed - Market Reviewed": "Closed Lost",
}

STAGE_AHEAD_OF_ROE = {"Contract Negotiations", "Under Contract", "Under Construction", "Ready for Eng", "Activation", "Closed Won"}

LOSS_REASON_MAP = {
    "Existing Fiber": "Existing Fiber",
    "Not Interested": "Not Interested",
    "Contact Info": "No Contact Info",
    "Existing Contract": "Existing Contract",
    "Other": "Other",
}

COMMON_HEADERS = [
    "State", "AgreeName", "Address", "Units", "Active Units",
    "FDH Activation Date", "City", "RE Assigned", "ROE Executed Date",
    "PAL Executed Date", "RE Status", "Closed Date", "Closed Bucket",
    "Closed Notes", "Existing Fiber Provider", "Off Hold/Exp Date",
    "Notes", "Management Company", "Owner/Property Contact",
]


def parse_excel(path, sheet_names):
    all_rows = []
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
        wb_ns = {
            "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        sheet_rid = {}
        for sheet_el in wb_tree.findall(".//s:sheet", wb_ns):
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

        for sheet_name in sheet_names:
            if sheet_name not in sheet_rid:
                continue
            rid = sheet_rid[sheet_name]
            sheet_file = rid_to_file[rid]
            with z.open(sheet_file) as f:
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
            header_row = sorted_rows[0]
            headers = rows[header_row]
            header_map = {headers[k]: k for k in headers if headers[k]}
            for rn in sorted_rows[1:]:
                obj = {"Source": sheet_name}
                for h in COMMON_HEADERS:
                    col_idx = header_map.get(h)
                    if col_idx is not None and col_idx in rows[rn]:
                        obj[h] = rows[rn][col_idx] or ""
                    else:
                        obj[h] = ""
                if obj["State"] and obj["AgreeName"]:
                    all_rows.append(obj)
    return all_rows


def excel_date_to_str(val):
    if not val:
        return None
    try:
        serial = int(float(val))
        dt = datetime(1899, 12, 30) + timedelta(days=serial)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None


def norm(s):
    return (s or "").strip().lower()


def excel_expected_stage_and_reason(row):
    re_status = row["RE Status"].strip()
    stage = STAGE_MAP.get(re_status, "Prospecting")
    loss_reason = None
    if stage == "Closed Lost":
        bucket = row.get("Closed Bucket", "").strip()
        loss_reason = LOSS_REASON_MAP.get(bucket)
    return stage, loss_reason


def main():
    print("=" * 70)
    print("ROE 9-25 Units — Excel vs Salesforce DIFF (read-only)")
    print("=" * 70)

    # 1. Excel
    print(f"\n1. Reading Excel: {EXCEL_PATH}")
    rows = parse_excel(EXCEL_PATH, SHEETS)
    print(f"   Rows: {len(rows)}")
    excel_by_key = {norm(r["AgreeName"]): r for r in rows}
    # Detect duplicate Agreement Names within Excel
    dupe_keys = [k for k, c in Counter(norm(r["AgreeName"]) for r in rows).items() if c > 1]
    if dupe_keys:
        print(f"   WARN: {len(dupe_keys)} duplicate Agreement Names within Excel (first 5): {dupe_keys[:5]}")

    # 2. Salesforce
    print("\n2. Connecting to Salesforce...")
    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Hawaiian1984",
        security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
    )

    soql = (
        "SELECT Id, Name, Agreement_Name__c, StageName, CloseDate, "
        "OwnerId, RE_Assigned__c, Loss_Reason__c, Units__c, "
        "Property_State__c, Property_City__c, Property_Address__c "
        "FROM Opportunity "
        "WHERE RecordType.Name = 'MDU' AND Agreement_Name__c != null"
    )
    result = sf.query_all(soql)
    sf_records = result["records"]
    print(f"   SF MDU Opps with Agreement_Name__c: {len(sf_records)}")

    sf_by_key = {}
    for r in sf_records:
        sf_by_key.setdefault(norm(r["Agreement_Name__c"]), []).append(r)

    # 3. Categorize
    new_in_excel = []        # in Excel, not in SF  → INSERT candidates
    matched = []             # in both              → UPDATE candidates (maybe)
    orphan_in_sf = []        # in SF but not Excel (limited to 9-25 heuristic)
    excel_dupes_in_sf = []   # Agreement name appears multiple times in SF

    for key, erow in excel_by_key.items():
        sf_rows = sf_by_key.get(key)
        if not sf_rows:
            new_in_excel.append(erow)
        elif len(sf_rows) > 1:
            excel_dupes_in_sf.append({"key": key, "count": len(sf_rows), "ids": [r["Id"] for r in sf_rows]})
            matched.append((erow, sf_rows[0]))
        else:
            matched.append((erow, sf_rows[0]))

    # 4. Field-level drift on matched rows
    drift = []
    for erow, srow in matched:
        expected_stage, expected_loss = excel_expected_stage_and_reason(erow)
        expected_re_initials = erow["RE Assigned"].strip().upper() or None
        current_re_initials = RE_ID_TO_INITIALS.get(srow.get("RE_Assigned__c") or "", None)

        try:
            expected_units = int(float(erow["Units"])) if erow["Units"] else None
        except (ValueError, TypeError):
            expected_units = None
        current_units = int(srow["Units__c"]) if srow.get("Units__c") is not None else None

        changes = {}
        # Stage: if Excel expects ROE Secured but SF is already further along the pipeline,
        # that's progression (ST/Monday sync) not drift. Don't flag.
        if srow["StageName"] != expected_stage:
            if expected_stage == "ROE Secured" and srow["StageName"] in STAGE_AHEAD_OF_ROE:
                pass  # SF advanced past ROE Secured. Not drift.
            else:
                changes["StageName"] = {"sf": srow["StageName"], "excel": expected_stage, "source_re_status": erow["RE Status"]}
        # Loss Reason: only flag when Excel has a specific mapped reason that differs.
        # Don't overwrite existing SF values when Excel has no bucket.
        if expected_loss and (srow.get("Loss_Reason__c") or None) != expected_loss:
            changes["Loss_Reason__c"] = {"sf": srow.get("Loss_Reason__c"), "excel": expected_loss, "source_bucket": erow.get("Closed Bucket")}
        if expected_re_initials and expected_re_initials in RE_ASSIGNED_MAP:
            if current_re_initials != expected_re_initials:
                changes["RE_Assigned__c"] = {"sf": current_re_initials, "excel": expected_re_initials}
        if expected_units is not None and current_units != expected_units:
            changes["Units__c"] = {"sf": current_units, "excel": expected_units}

        if changes:
            drift.append({
                "sf_id": srow["Id"],
                "agreement_name": srow["Agreement_Name__c"],
                "state": erow["State"],
                "excel_re_status": erow["RE Status"],
                "changes": changes,
            })

    # 5. SF Opps that claim 9-25 origin but Excel no longer has them
    excel_keys = set(excel_by_key.keys())
    for key, recs in sf_by_key.items():
        if key in excel_keys:
            continue
        # heuristic: SF owner = Melissa Baker (9-25 import owner)
        for r in recs:
            if r.get("OwnerId") == "005WR000003CD6DYAW":
                orphan_in_sf.append({
                    "sf_id": r["Id"],
                    "agreement_name": r["Agreement_Name__c"],
                    "stage": r["StageName"],
                    "state": r.get("Property_State__c"),
                })

    # 6. Summary print
    print("\n" + "=" * 70)
    print("DIFF SUMMARY")
    print("=" * 70)
    print(f"  Excel rows:                        {len(rows)}")
    print(f"  SF MDU Opps (all):                 {len(sf_records)}")
    print(f"  Matched (Excel <-> SF):            {len(matched)}")
    print(f"  New in Excel (INSERT candidates):  {len(new_in_excel)}")
    print(f"  Drift on matched (UPDATE cands):   {len(drift)}")
    print(f"  SF orphans (Melissa-owned only):   {len(orphan_in_sf)}")
    print(f"  Excel->SF name dupes (>1 match):   {len(excel_dupes_in_sf)}")

    # Drift breakdown by field
    drift_field_counts = Counter()
    for d in drift:
        for f in d["changes"].keys():
            drift_field_counts[f] += 1
    print("\n  Drift by field:")
    for f, c in drift_field_counts.most_common():
        print(f"    {f}: {c}")

    # New rows by state
    new_by_state = Counter(r["State"].strip() for r in new_in_excel)
    print("\n  New-in-Excel by state:")
    for s, c in new_by_state.most_common():
        print(f"    {s}: {c}")

    # 7. Save full JSON
    out = {
        "generated": datetime.now().isoformat(),
        "counts": {
            "excel_rows": len(rows),
            "sf_mdu_opps": len(sf_records),
            "matched": len(matched),
            "new_in_excel": len(new_in_excel),
            "drift": len(drift),
            "orphan_in_sf": len(orphan_in_sf),
        },
        "new_in_excel": new_in_excel,
        "drift": drift,
        "orphan_in_sf": orphan_in_sf,
        "excel_dupes_in_sf": excel_dupes_in_sf,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nFull diff written to: {OUTPUT}")


if __name__ == "__main__":
    main()
