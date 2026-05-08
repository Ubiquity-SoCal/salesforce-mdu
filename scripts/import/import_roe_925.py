"""
ROE 9-25 Units → Salesforce MDU Opportunity Import
Re-runnable: reads Excel fresh, skips records already in SF by Agreement_Name__c.
"""

import sys
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import date, datetime, timedelta
from simple_salesforce import Salesforce

# ── Config ──────────────────────────────────────────────────────────────────
EXCEL_PATH = r"C:\Users\cass\OneDrive - Ubiquity Management\PMO_Projects - MDU 9-25 Units ROE Project\MDU 9 - 25 Units.xlsx"
SHEETS = ["Site Data", "TX Site Data"]
DRY_RUN = "--dry-run" in sys.argv  # Pass --dry-run to preview without pushing

MDU_RECORD_TYPE_ID = "012WR00000Ra0mkYAB"
MELISSA_BAKER_ID = "005WR000003CD6DYAW"

# RE Assigned initials → SF User ID (for RE_Assigned__c lookup field)
RE_ASSIGNED_MAP = {
    "RS": "005WR0000030R9lYAE",  # Rosemarie Shortino
    "TF": "005WR0000030R1hYAE",  # Tanya Friese
    "JB": "005WR0000030RCzYAM",  # Justin Barry
}

# RE Status → SF Stage
STAGE_MAP = {
    "Completed": "Under Contract",
    "Engaged": "Prospecting",
    "Proposal Sent": "Prospecting",
    "Pending Signature": "Prospecting",
    "Research Required": "Prospecting",
    "Data Issue": "Prospecting",
    "Assigned FiberFirst": "Prospecting",
    "Closed - Lost": "Closed Lost",
    "Closed - Market Reviewed": "Closed Lost",
}

# Closed Bucket → Loss_Reason__c
LOSS_REASON_MAP = {
    "Existing Fiber": "Existing Fiber",
    "Not Interested": "Not Interested",
    "Contact Info": "No Contact Info",
    "Existing Contract": "Existing Contract",
    "Other": "Other",
}

STATE_EXPAND = {
    "AZ": "Arizona",
    "TX": "Texas",
    "NE": "Nebraska",
    "CO": "Colorado",
    "CA": "California",
}

# Common headers present in both sheets
COMMON_HEADERS = [
    "State", "AgreeName", "Address", "Units", "Active Units",
    "FDH Activation Date", "City", "RE Assigned", "ROE Executed Date",
    "PAL Executed Date", "RE Status", "Closed Date", "Closed Bucket",
    "Closed Notes", "Existing Fiber Provider", "Off Hold/Exp Date",
    "Notes", "Management Company", "Owner/Property Contact",
]


# ── Excel Parser ────────────────────────────────────────────────────────────
def parse_excel(path, sheet_names):
    """Parse .xlsx by reading ZIP/XML directly (no COM/Excel dependency)."""
    all_rows = []

    with zipfile.ZipFile(path, 'r') as z:
        # Shared strings
        with z.open("xl/sharedStrings.xml") as f:
            ss_tree = ET.parse(f)
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings = []
        for si in ss_tree.findall(".//s:si", ns):
            parts = []
            # Simple <t> text
            t = si.find("s:t", ns)
            if t is not None and t.text:
                parts.append(t.text)
            # Rich text <r><t>
            for r in si.findall("s:r", ns):
                rt = r.find("s:t", ns)
                if rt is not None and rt.text:
                    parts.append(rt.text)
            strings.append("".join(parts))

        # Workbook (sheet name → rId)
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

        # Rels (rId → file path)
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
                print(f"  WARNING: Sheet '{sheet_name}' not found, skipping")
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
                # Skip blank rows
                if obj["State"] and obj["AgreeName"]:
                    all_rows.append(obj)

    return all_rows


# ── Salesforce Mapping ──────────────────────────────────────────────────────
def excel_date_to_str(val):
    """Convert Excel serial date number to YYYY-MM-DD string."""
    if not val:
        return None
    try:
        serial = int(float(val))
        dt = datetime(1899, 12, 30) + timedelta(days=serial)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        # Try parsing as date string
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None


def build_opportunity(row):
    """Map an ROE Excel row to a Salesforce Opportunity record."""
    agree_name = row["AgreeName"].strip()
    re_status = row["RE Status"].strip()
    stage = STAGE_MAP.get(re_status, "Prospecting")
    state_full = STATE_EXPAND.get(row["State"].strip(), row["State"].strip())

    opp = {
        "Name": agree_name[:120],  # SF max 120 chars
        "RecordTypeId": MDU_RECORD_TYPE_ID,
        "StageName": stage,
        "OwnerId": MELISSA_BAKER_ID,
        "Agreement_Name__c": agree_name[:255],
        "Property_Address__c": row["Address"].strip()[:255],
        "Property_City__c": row["City"].strip()[:255],
        "Property_State__c": state_full[:255],
    }

    # Units
    try:
        opp["Units__c"] = int(float(row["Units"]))
    except (ValueError, TypeError):
        pass

    # RE Assigned (lookup field)
    re_initials = row["RE Assigned"].strip().upper()
    if re_initials in RE_ASSIGNED_MAP:
        opp["RE_Assigned__c"] = RE_ASSIGNED_MAP[re_initials]

    # Close Date (required field)
    if stage == "Closed Lost":
        close_date = excel_date_to_str(row.get("Closed Date", ""))
        opp["CloseDate"] = close_date or date.today().strftime("%Y-%m-%d")
    elif stage == "Under Contract":
        roe_date = excel_date_to_str(row.get("ROE Executed Date", ""))
        opp["CloseDate"] = roe_date or date.today().strftime("%Y-%m-%d")
    else:
        # Open opportunities — set to end of year
        opp["CloseDate"] = f"{date.today().year}-12-31"

    # Loss Reason (Closed Lost only)
    if stage == "Closed Lost":
        bucket = row.get("Closed Bucket", "").strip()
        loss_reason = LOSS_REASON_MAP.get(bucket)
        if loss_reason:
            opp["Loss_Reason__c"] = loss_reason

    return opp


def build_note_content(row):
    """Build a combined note from the ROE spreadsheet data."""
    parts = []

    parts.append(f"Source: ROE 9-25 Units Tracker ({row['Source']})")
    parts.append(f"RE Status: {row['RE Status']}")

    if row.get("Closed Bucket"):
        parts.append(f"Closed Bucket: {row['Closed Bucket']}")
    if row.get("Closed Notes"):
        parts.append(f"Closed Notes: {row['Closed Notes']}")
    if row.get("Existing Fiber Provider"):
        parts.append(f"Existing Fiber Provider: {row['Existing Fiber Provider']}")
    if row.get("FDH Activation Date"):
        fdh = excel_date_to_str(row["FDH Activation Date"])
        if not fdh:
            fdh = row["FDH Activation Date"]
        parts.append(f"FDH Activation Date: {fdh}")
    if row.get("ROE Executed Date"):
        roe_dt = excel_date_to_str(row["ROE Executed Date"])
        if not roe_dt:
            roe_dt = row["ROE Executed Date"]
        parts.append(f"ROE Executed Date: {roe_dt}")
    if row.get("PAL Executed Date"):
        pal_dt = excel_date_to_str(row["PAL Executed Date"])
        if not pal_dt:
            pal_dt = row["PAL Executed Date"]
        parts.append(f"PAL Executed Date: {pal_dt}")
    if row.get("Active Units"):
        parts.append(f"Active Units: {row['Active Units']}")
    if row.get("Management Company"):
        parts.append(f"Management Company: {row['Management Company']}")
    if row.get("Owner/Property Contact"):
        parts.append(f"Owner/Property Contact: {row['Owner/Property Contact']}")
    if row.get("Notes"):
        parts.append(f"\nNotes:\n{row['Notes']}")

    return "\n".join(parts)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("ROE 9-25 Units -> Salesforce MDU Opportunity Import")
    print(f"Mode: {'DRY RUN (preview only)' if DRY_RUN else 'LIVE IMPORT'}")
    print("=" * 60)

    # Step 1: Parse Excel
    print(f"\n1. Reading Excel: {EXCEL_PATH}")
    all_rows = parse_excel(EXCEL_PATH, SHEETS)
    print(f"   Total records from Excel: {len(all_rows)}")

    # Step 2: Connect to Salesforce and get existing Agreement_Name__c values
    print("\n2. Connecting to Salesforce...")
    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Karate88!",
        security_token="Ktc1n9mLmD9vwEcVcl45q0iAD",
    )

    result = sf.query_all(
        "SELECT Agreement_Name__c FROM Opportunity "
        "WHERE RecordType.Name = 'MDU' AND Agreement_Name__c != null"
    )
    existing_agrees = {r["Agreement_Name__c"].strip().lower() for r in result["records"]}
    print(f"   Existing MDU Opps with Agreement_Name__c: {len(existing_agrees)}")

    # Step 3: Filter to net-new records
    new_rows = []
    skipped = []
    for row in all_rows:
        agree = row["AgreeName"].strip().lower()
        if agree in existing_agrees:
            skipped.append(row)
        else:
            new_rows.append(row)

    print(f"\n3. Dedup results:")
    print(f"   Already in SF (skipped): {len(skipped)}")
    print(f"   New (to import): {len(new_rows)}")

    if not new_rows:
        print("\n   Nothing new to import. Done!")
        return

    # Step 4: Build SF records
    opps = []
    notes_data = []
    for row in new_rows:
        opp = build_opportunity(row)
        opps.append(opp)
        note_content = build_note_content(row)
        if note_content:
            notes_data.append({
                "agree_name": row["AgreeName"].strip(),
                "content": note_content,
            })

    # Stage breakdown
    from collections import Counter
    stage_counts = Counter(o["StageName"] for o in opps)
    print(f"\n4. Import breakdown by stage:")
    for stage, count in stage_counts.most_common():
        print(f"   {stage}: {count}")

    state_counts = Counter(o["Property_State__c"] for o in opps)
    print(f"\n   By state:")
    for state, count in state_counts.most_common():
        print(f"   {state}: {count}")

    if DRY_RUN:
        print("\n-- DRY RUN -- Sample records (first 5):")
        for i, opp in enumerate(opps[:5]):
            print(f"\n   #{i+1}: {opp['Name']}")
            for k, v in opp.items():
                if k != "Name":
                    print(f"      {k}: {v}")
        print(f"\n   ... and {len(opps)-5} more")
        print("\n   Run without --dry-run to import.")
        return

    # Step 5: Create Opportunities
    print(f"\n5. Creating {len(opps)} Opportunities...")
    created = 0
    errors = []
    opp_id_map = {}  # agree_name → SF Id

    for i, opp in enumerate(opps):
        try:
            result = sf.Opportunity.create(opp)
            opp_id = result["id"]
            opp_id_map[opp["Agreement_Name__c"]] = opp_id
            created += 1
            if (i + 1) % 25 == 0:
                print(f"   Created {i+1}/{len(opps)}...")
        except Exception as e:
            errors.append({"opp": opp["Name"], "error": str(e)})

    print(f"   Created: {created}")
    if errors:
        print(f"   Errors: {len(errors)}")
        for err in errors[:10]:
            print(f"     {err['opp']}: {err['error']}")

    # Step 6: Create ContentNotes for each opportunity
    print(f"\n6. Creating notes for {len(notes_data)} Opportunities...")
    notes_created = 0
    notes_errors = []

    for nd in notes_data:
        opp_id = opp_id_map.get(nd["agree_name"])
        if not opp_id:
            continue
        try:
            import base64
            # Create ContentNote
            note_body = base64.b64encode(nd["content"].encode("utf-8")).decode("utf-8")
            note = sf.ContentNote.create({
                "Title": f"ROE 9-25 Tracker Data - {nd['agree_name'][:80]}",
                "Content": note_body,
            })
            note_id = note["id"]

            # Link to Opportunity
            sf.ContentDocumentLink.create({
                "ContentDocumentId": note_id,
                "LinkedEntityId": opp_id,
                "ShareType": "V",
                "Visibility": "AllUsers",
            })
            notes_created += 1
        except Exception as e:
            notes_errors.append({"name": nd["agree_name"], "error": str(e)})

    print(f"   Notes created: {notes_created}")
    if notes_errors:
        print(f"   Note errors: {len(notes_errors)}")
        for err in notes_errors[:5]:
            print(f"     {err['name']}: {err['error']}")

    # Summary
    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print(f"  Opportunities created: {created}")
    print(f"  Notes attached: {notes_created}")
    print(f"  Errors: {len(errors) + len(notes_errors)}")
    print("=" * 60)

    # Save error log if any
    if errors or notes_errors:
        with open("C:/Users/cass/Work_Projects/SalesForce/roe_925_import_errors.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Type", "Name", "Error"])
            for err in errors:
                writer.writerow(["Opportunity", err["opp"], err["error"]])
            for err in notes_errors:
                writer.writerow(["Note", err["name"], err["error"]])
        print("  Error log: SalesForce/roe_925_import_errors.csv")


if __name__ == "__main__":
    main()
