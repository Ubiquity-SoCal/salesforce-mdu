"""
Migration Phase 2 — Import Opportunities from Monday.com
==========================================================
Maps 3,238 Monday.com items to Salesforce Opportunities with:
  - Stage mapping (Group + Sales Stage → SF Stage)
  - Owner mapping (priority: Chuck, Melissa, Brett, Taylor)
  - Field mapping per approved column analysis
  - Loss_Reason/Hold_Reason/Sales_Status population
  - MDU Record Type assignment
"""

import json
import time
import csv
from datetime import datetime, date
from simple_salesforce import Salesforce

# ── Config ──────────────────────────────────────────────────────────────
USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"

MDU_RECORD_TYPE_ID = "012WR00000Ra0mkYAB"

# SF User IDs for owner mapping
OWNER_MAP = {
    "chuck mcneely": "005WR00000CXIX7YAP",
    "brett spivey": "005WR00000CXEZyYAP",
    "taylor mauney": "005WR000009SCtuYAG",
    "melissa baker": "005WR000003CD6DYAW",
}
PRIORITY_OWNERS = ["chuck mcneely", "melissa baker", "brett spivey", "taylor mauney"]
DEFAULT_OWNER = "005WR000002ieYTYAY"  # Cass Parker

# ── Stage Mapping ────────────────────────────────────────────────────────
# Sales Stage (status column) takes priority over Group
SALES_STAGE_TO_SF = {
    "Closed Lost": "Closed Lost",
    "On Hold": "On Hold",
    "Contract(s) in Progress": "Contract Negotiations",
    "Assigned to Market Team": "Prospecting",
    "Lead": "Prospecting",
}

GROUP_TO_SF = {
    "Prospects": "Prospecting",
    "Under Contract": "Under Contract",
    "Ready for Engineering": "Under Contract",
    "Under Construction": "Under Contract",
    "Complete / Activated": "Under Contract",
    "Closed/Lost": "Closed Lost",
}

# ── Loss Reason Mapping ─────────────────────────────────────────────────
STATUS1_TO_LOSS_REASON = {
    "Existing Fiber": "Existing Fiber",
    "Existing Bulk": "Existing Contract",
    "Existing EMA": "Existing Contract",
    "Chose Another Provider": "Chose Another Provider",
    "Owner Rejected Offer": "Not Interested",
    "Unserviceable": "Unserviceable",
    "Lumen Rejected": "Not Interested",
    "Low Return": "Other",
    "Under 25": "Other",
    "No Contact Info": "No Contact Info",
}


def get_col(item, col_id):
    """Get column text value, handling None."""
    for cv in item.get("column_values", []):
        if cv["id"] == col_id:
            return (cv.get("text") or "").strip()
    return ""


def get_col_value(item, col_id):
    """Get raw column value JSON."""
    for cv in item.get("column_values", []):
        if cv["id"] == col_id:
            raw = cv.get("value")
            if raw and isinstance(raw, str):
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            return raw
    return None


def resolve_owner(owner_text):
    """Map Monday.com owner string to SF User ID."""
    if not owner_text:
        return DEFAULT_OWNER

    owner_lower = owner_text.lower()

    # Check priority owners first
    for name in PRIORITY_OWNERS:
        if name in owner_lower:
            return OWNER_MAP[name]

    return DEFAULT_OWNER


def map_stage(item):
    """Map Monday.com group + status to SF Stage, Sales_Status, Loss_Reason, Hold_Reason."""
    group = item["group"]["title"]
    sales_stage = get_col(item, "status")   # Sales Stage column
    status1 = get_col(item, "status1")      # Status column

    sf_stage = None
    sales_status = None
    loss_reason = None
    hold_reason = None

    # Sales Stage takes priority over Group
    if sales_stage in SALES_STAGE_TO_SF:
        sf_stage = SALES_STAGE_TO_SF[sales_stage]
    else:
        sf_stage = GROUP_TO_SF.get(group, "Prospecting")

    # Sales Status for Prospecting items
    if sf_stage == "Prospecting":
        if status1 == "Contact Pending":
            sales_status = "Contact Pending"
        elif status1 == "Reached Out - Pending Response":
            sales_status = "Reached Out - Pending Response"

    # Loss Reason for Closed Lost
    if sf_stage == "Closed Lost":
        loss_reason = STATUS1_TO_LOSS_REASON.get(status1, "Other")

    # Hold Reason for On Hold
    if sf_stage == "On Hold":
        hold_reason = "Other"  # No granular hold data in Monday.com

    return sf_stage, sales_status, loss_reason, hold_reason


def parse_address(item):
    """Parse address from location column + text fallbacks."""
    location_val = get_col_value(item, "location")
    address = ""
    city = get_col(item, "text4")       # City column
    state = get_col(item, "text6")      # State column
    zipcode = get_col(item, "text27")   # Zip Code column

    if location_val and isinstance(location_val, dict):
        address = location_val.get("address", "") or ""
        if not city:
            city_val = location_val.get("city", "")
            if isinstance(city_val, dict):
                city = city_val.get("long_name", "") or city_val.get("short_name", "") or ""
            elif isinstance(city_val, str):
                city = city_val
        if not state:
            state_val = location_val.get("state", location_val.get("country_short", ""))
            if isinstance(state_val, dict):
                state = state_val.get("long_name", "") or state_val.get("short_name", "") or ""
            elif isinstance(state_val, str):
                state = state_val

    # Fall back to full location text
    loc_text = get_col(item, "location")
    if loc_text and not address:
        address = loc_text

    # Ensure all are strings
    address = str(address) if address else ""
    city = str(city) if city else ""
    state = str(state) if state else ""
    zipcode = str(zipcode) if zipcode else ""

    return address, city, state, zipcode


def parse_date(date_str):
    """Parse date string to YYYY-MM-DD format."""
    if not date_str:
        return None
    # Monday.com dates are typically YYYY-MM-DD
    try:
        d = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d")
        return d.strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def build_opportunity(item, account_map):
    """Build SF Opportunity record from Monday.com item."""
    sf_stage, sales_status, loss_reason, hold_reason = map_stage(item)

    owner_text = get_col(item, "person")
    owner_id = resolve_owner(owner_text)

    address, city, state, zipcode = parse_address(item)

    units_text = get_col(item, "numbers5")
    units = None
    if units_text:
        try:
            units = float(units_text.replace(",", ""))
        except ValueError:
            pass

    # CloseDate logic
    close_date = parse_date(get_col(item, "date_mm0wzyrd"))  # Projected Close Date
    if not close_date:
        close_date = parse_date(get_col(item, "date0"))  # PAL Signed Date
    if not close_date:
        close_date = parse_date(get_col(item, "date1"))  # Deal creation date
    if not close_date:
        close_date = "2026-12-31"  # Default

    # Portfolio and Management Company lookups
    portfolio_text = get_col(item, "text8")
    mgmt_text = get_col(item, "text3")
    portfolio_id = account_map.get(portfolio_text.lower().strip()) if portfolio_text else None
    mgmt_id = account_map.get(mgmt_text.lower().strip()) if mgmt_text else None

    record = {
        "Name": item["name"].strip()[:120],  # SF max 120 chars
        "StageName": sf_stage,
        "CloseDate": close_date,
        "OwnerId": owner_id,
        "RecordTypeId": MDU_RECORD_TYPE_ID,
        "Monday_Item_ID__c": str(item["id"]),
    }

    # Optional fields
    if units is not None:
        record["Units__c"] = units
    if address:
        record["Property_Address__c"] = address[:255]
    if city:
        record["Property_City__c"] = city[:255]
    if state:
        record["Property_State__c"] = state[:255]
    if zipcode:
        record["Property_Zip__c"] = zipcode[:20]

    category = get_col(item, "dropdown4__1")
    if category:
        record["Property_Category__c"] = category[:255]

    prop_type = get_col(item, "dropdown3")
    if prop_type:
        record["Property_Type__c"] = prop_type[:255]

    build_type = get_col(item, "dropdown4")
    if build_type:
        record["Build_Type__c"] = build_type[:255]

    prosp_isp = get_col(item, "dropdown__1")
    if prosp_isp:
        record["Prospective_ISP__c"] = prosp_isp[:255]

    conf_isp = get_col(item, "dropdown6")
    if conf_isp:
        record["Confirmed_ISP__c"] = conf_isp[:255]

    incumbent = get_col(item, "text5")
    if incumbent:
        record["Incumbent_Provider__c"] = incumbent[:255]

    agree_name = get_col(item, "text6__1")
    if agree_name:
        record["Agreement_Name__c"] = agree_name[:255]

    if sales_status:
        record["Sales_Status__c"] = sales_status
    if loss_reason:
        record["Loss_Reason__c"] = loss_reason
    if hold_reason:
        record["Hold_Reason__c"] = hold_reason

    if portfolio_id:
        record["Portfolio__c"] = portfolio_id
    if mgmt_id:
        record["Management_Company__c"] = mgmt_id

    return record


def main():
    print("Migration Phase 2 - Import Opportunities")
    print("=" * 60)

    # Connect
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("Connected to Salesforce")

    # Load Monday.com data
    with open(r"C:/Users/cass/Work_Projects/Monday.com/full_archive/opportunities_full_archive.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    print(f"Loaded {len(items)} items from Monday.com archive")

    # Build account lookup for Portfolio/Mgmt Company matching
    accounts = sf.query_all("SELECT Id, Name FROM Account")
    account_map = {rec["Name"].lower().strip(): rec["Id"] for rec in accounts["records"]}
    print(f"Loaded {len(account_map)} accounts for lookup matching")

    # Check for existing Monday.com-imported Opps (dedup by Monday_Item_ID__c)
    existing = sf.query_all(
        "SELECT Monday_Item_ID__c FROM Opportunity WHERE Monday_Item_ID__c != null"
    )
    existing_ids = {rec["Monday_Item_ID__c"] for rec in existing["records"]}
    print(f"Existing Monday.com Opps in SF: {len(existing_ids)}")

    # Build records
    to_import = []
    to_skip = []
    stage_counts = {}

    for item in items:
        monday_id = str(item["id"])
        if monday_id in existing_ids:
            to_skip.append(monday_id)
            continue

        record = build_opportunity(item, account_map)
        to_import.append(record)

        stage = record["StageName"]
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    print(f"\nTo import: {len(to_import)}")
    print(f"To skip (already imported): {len(to_skip)}")
    print("\nStage distribution:")
    for stage, count in sorted(stage_counts.items(), key=lambda x: -x[1]):
        print(f"  {stage}: {count}")

    # Import in batches of 200 (SF bulk limit per API call)
    BATCH_SIZE = 200
    total_created = 0
    total_failed = 0
    errors = []
    start_time = time.time()

    print(f"\nImporting {len(to_import)} opportunities in batches of {BATCH_SIZE}...")

    for batch_start in range(0, len(to_import), BATCH_SIZE):
        batch = to_import[batch_start : batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(to_import) + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            results = sf.bulk.Opportunity.insert(batch, batch_size=BATCH_SIZE)
            for i, result in enumerate(results):
                if result.get("success"):
                    total_created += 1
                else:
                    total_failed += 1
                    item_name = batch[i].get("Name", "?")
                    err_msg = str(result.get("errors", "unknown"))
                    errors.append((item_name, err_msg))
        except Exception as e:
            # Fall back to individual inserts for this batch
            print(f"  Batch {batch_num} bulk insert failed: {e}")
            print(f"  Falling back to individual inserts...")
            for rec in batch:
                try:
                    result = sf.Opportunity.create(rec)
                    if result.get("success"):
                        total_created += 1
                    else:
                        total_failed += 1
                        errors.append((rec.get("Name", "?"), str(result)))
                except Exception as e2:
                    total_failed += 1
                    errors.append((rec.get("Name", "?"), str(e2)))

        elapsed = time.time() - start_time
        rate = total_created / elapsed if elapsed > 0 else 0
        print(
            f"  Batch {batch_num}/{total_batches}: "
            f"{total_created} created, {total_failed} failed "
            f"({elapsed:.0f}s, {rate:.0f}/s)"
        )

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"IMPORT COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Created: {total_created}")
    print(f"  Failed:  {total_failed}")
    print(f"  Skipped: {len(to_skip)}")
    print(f"  Time:    {elapsed:.0f}s")

    if errors:
        print(f"\n  First 20 errors:")
        for name, err in errors[:20]:
            print(f"    {name}: {err}")

        # Write full error log
        with open("migration_opp_errors.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Error"])
            for name, err in errors:
                writer.writerow([name, err])
        print(f"  Full error log: migration_opp_errors.csv")

    # Verify
    final_count = sf.query("SELECT COUNT() FROM Opportunity WHERE RecordType.Name = 'MDU'")
    print(f"\n  Total MDU Opportunities in SF: {final_count['totalSize']}")


if __name__ == "__main__":
    main()
