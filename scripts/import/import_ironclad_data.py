"""
Import IronClad export data into IronClad__c Salesforce object.
1,057 records, 60 fields (all Y + M columns from analysis).
Uses IronClad_Id__c as external ID for upsert (safe to re-run).
"""

import openpyxl
import re
from datetime import datetime
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# --- Credentials ---
USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# --- Load export ---
EXPORT_PATH = "C:/Users/cass/Work_Projects/IronClad/data/input/exports/ironclad_export_2026-08-18_153235_all.xlsx"

print("Loading export file...")
wb = openpyxl.load_workbook(EXPORT_PATH, read_only=True)
ws = wb["export"]

rows = list(ws.iter_rows(values_only=True))
headers = list(rows[0])
data_rows = [r for r in rows[1:] if any(v is not None for v in r[:5])]
print(f"Loaded {len(data_rows)} records with {len(headers)} columns")


def col(row, name):
    """Get column value by header name."""
    try:
        idx = headers.index(name)
        val = row[idx] if idx < len(row) else None
        if val is not None and isinstance(val, str):
            val = val.strip()
            if val == "":
                return None
        return val
    except (ValueError, IndexError):
        return None


def parse_date(val):
    """Parse date string to YYYY-MM-DD format for Salesforce."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    val = str(val).strip()
    if not val:
        return None
    # Handle ISO format dates
    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"]:
        try:
            return datetime.strptime(val[:10], fmt[:8] if len(val) < 11 else fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Just return first 10 chars if it looks like a date
    if re.match(r"\d{4}-\d{2}-\d{2}", val):
        return val[:10]
    return None


def parse_datetime(val):
    """Parse datetime string for Salesforce DateTime fields."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    val = str(val).strip()
    if not val:
        return None
    # Try common formats
    for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(val, fmt).isoformat()
        except ValueError:
            continue
    # Fall back to date only
    d = parse_date(val)
    if d:
        return d + "T00:00:00"
    return None


def parse_currency(val):
    """Parse currency string like '$10000' to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip().replace("$", "").replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None


def parse_percent(val):
    """Parse percent value (stored as 10 meaning 10%, SF wants 10.0)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except ValueError:
        return None


def parse_int(val):
    """Parse integer value."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    try:
        return int(str(val).strip())
    except ValueError:
        return None


def safe_text(val, max_len=255):
    """Truncate text to max length."""
    if val is None:
        return None
    val = str(val).strip()
    if not val:
        return None
    return val[:max_len]


def parse_bool(val):
    """Parse boolean from True/False/Yes/No string."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "yes", "1")


# --- Build records ---
print("\nMapping fields...")
records = []
skipped = 0

for i, row in enumerate(data_rows):
    ic_id = col(row, "Ironclad Id")
    if not ic_id:
        skipped += 1
        continue

    record = {
        # Identity & Linking
        "IronClad_Id__c": safe_text(ic_id, 20),
        "Record_Name__c": safe_text(col(row, "Record Name")),
        "Record_Type_IC__c": safe_text(col(row, "Record Type")),
        "Agree_Name__c": safe_text(col(row, "AgreeName")),
        "Record_Id_IC__c": safe_text(col(row, "Record Id"), 80),
        # Status & Stage
        "Contract_Status__c": safe_text(col(row, "Contract Status"), 50),
        "Stage_IC__c": safe_text(col(row, "Stage"), 50),
        # Dates
        "Agreement_Date__c": parse_date(col(row, "Agreement Date")),
        "Effective_Date__c": parse_date(col(row, "Effective Date")),
        "Expiration_Date__c": parse_date(col(row, "Expiration Date")),
        "Executed_Date__c": parse_date(col(row, "Executed Date")),
        "Workflow_Created_Date__c": parse_date(col(row, "Workflow Created Date")),
        "Workflow_Completed_Date__c": parse_date(col(row, "Workflow Completed Date")),
        "Last_Activity_Date_IC__c": parse_datetime(col(row, "Last Activity Date")),
        "Last_Activity_Action__c": safe_text(col(row, "Last Activity Action"), 100),
        "Anniversary_Date__c": parse_date(col(row, "Anniversary Date")),
        "Renewal_Opt_Out_Date__c": parse_date(col(row, "Renewal Opt Out Date")),
        # Property Info
        "Property_Name__c": safe_text(col(row, "Property Name")),
        "Property_Address__c": safe_text(col(row, "Property Address"), 255),
        "Property_City__c": safe_text(col(row, "Property Address Locality"), 100),
        "Property_State__c": safe_text(col(row, "Property Address Region"), 50),
        "Property_Group__c": safe_text(col(row, "Property Group")),
        "Property_Type__c": safe_text(col(row, "Property Type"), 100),
        "MDU_or_BUS__c": safe_text(col(row, "MDU or BUS"), 10),
        "Number_of_Residential_Units__c": parse_int(col(row, "Number of Residential Units")),
        "Property_Postcode__c": safe_text(col(row, "Property Address Postcode"), 20),
        "Property_Location__c": safe_text(col(row, "Property Location"), 50),
        "Number_of_Units_ROE__c": parse_int(col(row, "Number of Units (ROE)")),
        "Parcel_Number__c": safe_text(col(row, "Parcel Number"), 50),
        # Counterparty
        "Counterparty_Name__c": safe_text(col(row, "Counterparty Name")),
        "Counterparty_Contact_Name__c": safe_text(col(row, "Counterparty Contact Name")),
        "Counterparty_Contact_Email__c": safe_text(col(row, "Counterparty Contact Email")),
        "Counterparty_Signer_Name__c": safe_text(col(row, "Counterparty Signer Name")),
        "Counterparty_Signer_Email__c": safe_text(col(row, "Counterparty Signer Email")),
        "Counterparty_Signer_Title__c": safe_text(col(row, "Counterparty Signer Title")),
        "Counterparty_Telephone__c": safe_text(col(row, "Counterparty Telephone Number"), 40),
        "Counterparty_Entity_Type__c": safe_text(col(row, "Counterparty Entity Type"), 100),
        "Counterparty_Address__c": safe_text(col(row, "Counterparty Address"), 255),
        # Term & Renewal
        "Initial_Term_Length__c": safe_text(col(row, "Initial Term Length"), 20),
        "Renewal_Type__c": safe_text(col(row, "Renewal Type"), 50),
        "Renewal_Term_Length__c": safe_text(col(row, "Renewal Term Length"), 20),
        "Renewal_Opt_Out_Period__c": safe_text(col(row, "Renewal Opt Out Period"), 100),
        "Termination_Notice_Period__c": safe_text(col(row, "Termination Notice Period (Duration)"), 100),
        # Financial
        "Door_Fee__c": parse_currency(col(row, "Door Fee")),
        "Maximum_Door_Fee__c": parse_currency(col(row, "Maximum Door Fee")),
        "Contract_Value__c": parse_currency(col(row, "Contract Value")),
        "Revenue_Share_Pct__c": parse_percent(col(row, "revenue share %")),
        "Total_Build_Cost__c": parse_currency(col(row, "Total Build Cost")),
        # Agreement Details
        "Execution_Method__c": safe_text(col(row, "Execution Method"), 100),
        "ISP__c": safe_text(col(row, "ISP"), 50),
        "Brownfield_Greenfield__c": safe_text(col(row, "Brownfield/Greenfield"), 20),
        "Build_Type__c": safe_text(col(row, "Build Type"), 10),
        "Addendum_Signed__c": parse_bool(col(row, "Addendum Signed/Uploaded")),
        # People & Workflow
        "Contract_Owner_IC__c": safe_text(col(row, "Contract Owner"), 100),
        "External_Affair_Assignee__c": safe_text(col(row, "External Affair Assignee "), 100),
        "Internal_Party__c": safe_text(col(row, "Internal Party"), 100),
        "Requestor__c": safe_text(col(row, "Requestor"), 100),
        "EA_Market_Team_Leader__c": safe_text(col(row, "EA Market Team Leader (ROE)"), 100),
        # Notes & Docs
        "Notes_IC__c": safe_text(col(row, "Notes"), 10000),
        "Additional_Notes__c": safe_text(col(row, "Additional Notes")),
        "Attachment_Filenames__c": safe_text(col(row, "Attachment Filenames"), 10000),
        "Repository_Link__c": None,  # Will handle hyperlinks below
        "Workflow_Link__c": None,    # Will handle hyperlinks below
        # Sync tracking
        "Last_Synced__c": datetime.utcnow().isoformat(),
    }

    # Handle Repository Link and Workflow Link - they're hyperlinks in Excel
    # The export shows "Link to Repository" / "Link to Workflow" as display text
    # but the actual URLs are in the hyperlinks. Since openpyxl read_only mode
    # doesn't preserve hyperlinks, we'll construct them from the IronClad ID.
    # IronClad repository URLs follow: https://ironcladapp.com/records/{record_id}
    record_id = col(row, "Record Id")
    workflow_id = col(row, "Workflow Id")
    if record_id:
        # Clean the record_id (remove 'workflow:' prefix if present for repo link)
        clean_id = str(record_id).replace("workflow:", "")
        record["Repository_Link__c"] = f"https://ironcladapp.com/records/{clean_id}"
    if workflow_id:
        record["Workflow_Link__c"] = f"https://ironcladapp.com/workflow/{workflow_id}"

    # Remove None values to avoid sending nulls for empty fields
    record = {k: v for k, v in record.items() if v is not None}

    records.append(record)

print(f"Mapped {len(records)} records ({skipped} skipped - no IronClad ID)")

# --- Upsert to Salesforce ---
print("\n" + "=" * 60)
print("IMPORTING TO SALESFORCE")
print("=" * 60)

BATCH_SIZE = 200
success_count = 0
error_count = 0
errors = []

for batch_start in range(0, len(records), BATCH_SIZE):
    batch = records[batch_start : batch_start + BATCH_SIZE]
    batch_num = batch_start // BATCH_SIZE + 1
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} records)...")

    try:
        results = sf.bulk.IronClad__c.upsert(batch, "IronClad_Id__c", batch_size=BATCH_SIZE)
        for j, r in enumerate(results):
            if r.get("success"):
                success_count += 1
            else:
                error_count += 1
                ic_id = batch[j].get("IronClad_Id__c", "?")
                err_msg = str(r.get("errors", "unknown"))
                errors.append(f"{ic_id}: {err_msg}")
                if error_count <= 10:
                    print(f"  ERROR: {ic_id}: {err_msg[:200]}")
    except Exception as e:
        print(f"  Bulk upsert failed: {e}")
        print("  Falling back to individual upserts...")
        for rec in batch:
            try:
                sf.IronClad__c.upsert(f"IronClad_Id__c/{rec['IronClad_Id__c']}", rec)
                success_count += 1
            except Exception as e2:
                error_count += 1
                ic_id = rec.get("IronClad_Id__c", "?")
                err_msg = str(e2)[:200]
                errors.append(f"{ic_id}: {err_msg}")
                if error_count <= 10:
                    print(f"  ERROR: {ic_id}: {err_msg}")

    print(f"  Running total: {success_count} success, {error_count} errors")

# --- Summary ---
print("\n" + "=" * 60)
print("IMPORT COMPLETE")
print("=" * 60)
print(f"Total records: {len(records)}")
print(f"Success: {success_count}")
print(f"Errors: {error_count}")

if errors:
    print(f"\nFirst 20 errors:")
    for e in errors[:20]:
        print(f"  {e}")

    # Save full error log
    with open("C:/Users/cass/Work_Projects/IronClad/import_errors.txt", "w") as f:
        f.write(f"IronClad Import Errors - {datetime.now()}\n")
        f.write(f"Total: {error_count} errors out of {len(records)} records\n\n")
        for e in errors:
            f.write(f"{e}\n")
    print(f"\nFull error log: IronClad/import_errors.txt")

print("\nDone!")
