"""
Import sample data from Monday.com into Salesforce for beta testing.

Steps:
  1. Create custom fields on Opportunity (if missing)
  2. Import Accounts (27 items)
  3. Import Contacts (132 items) linked to Accounts
  4. Import ~50 Opportunities from select groups
"""

import json
import re
import sys
import time
import requests
from simple_salesforce import Salesforce, SalesforceError
import os as _os

# ── Monday.com config ─────────────────────────────────────────────────────

MONDAY_API_URL = "https://api.monday.com/v2"
with open(r"C:\Users\cass\Work_Projects\Monday.com\Monday.com_Key.txt") as f:
    MONDAY_TOKEN = f.read().strip()
MONDAY_HEADERS = {
    "Authorization": MONDAY_TOKEN,
    "Content-Type": "application/json",
    "API-Version": "2024-10",
}

BOARD_ACCOUNTS = "3036443514"
BOARD_CONTACTS = "3036443425"
BOARD_OPPS = "3036443295"

# ── Salesforce config ─────────────────────────────────────────────────────

# Salesforce config -- read from the gitignored SalesForce/api/ creds file.
# Never hardcode the password here: this file is tracked in git.
def _sf_creds():
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       "..", "..", "api", "Salesforce_Credentials.txt")
    _c = {}
    with open(_p) as _f:
        for _line in _f:
            if ":" in _line:
                _k, _v = _line.split(":", 1)
                _c[_k.strip()] = _v.strip()
    return _c


_SF = _sf_creds()
SF_USERNAME = _SF["Username"]
SF_PASSWORD = _SF["Password"]
SF_SECURITY_TOKEN = _SF["Security Token"]

# ── Monday.com helpers ────────────────────────────────────────────────────

def monday_query(q):
    """Execute a Monday.com GraphQL query."""
    resp = requests.post(MONDAY_API_URL, json={"query": q}, headers=MONDAY_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        print(f"  Monday API errors: {data['errors']}")
    return data["data"]


def fetch_all_items(board_id):
    """Fetch all items from a Monday.com board, handling pagination."""
    items = []
    data = monday_query(f"""{{
      boards(ids: {board_id}) {{
        items_page(limit: 500) {{
          cursor
          items {{
            id name
            group {{ id title }}
            column_values {{ id text value type }}
          }}
        }}
      }}
    }}""")
    page = data["boards"][0]["items_page"]
    items.extend(page["items"])
    cursor = page["cursor"]

    while cursor:
        data = monday_query(f"""{{
      next_items_page(limit: 500, cursor: "{cursor}") {{
        cursor
        items {{
          id name
          group {{ id title }}
          column_values {{ id text value type }}
        }}
      }}
    }}""")
        page = data["next_items_page"]
        items.extend(page["items"])
        cursor = page["cursor"]

    return items


def get_col_text(item, col_id):
    """Get the text value of a column from a Monday item."""
    for cv in item["column_values"]:
        if cv["id"] == col_id:
            return (cv.get("text") or "").strip()
    return ""


def get_col_value(item, col_id):
    """Get the parsed JSON value of a column from a Monday item."""
    for cv in item["column_values"]:
        if cv["id"] == col_id:
            raw = cv.get("value")
            if raw and raw != "null":
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    return raw
            return None
    return None


# ── Salesforce helpers ────────────────────────────────────────────────────

def ensure_custom_fields(sf):
    """Create custom fields on Opportunity if they don't already exist."""
    # Check which custom fields exist
    desc = sf.Opportunity.describe()
    existing = {f["name"] for f in desc["fields"]}

    fields_to_create = {
        "Units__c": ("Number", "Units", 10, 0),
        "Property_Address__c": ("Text", "Property Address", 255, None),
        "Property_City__c": ("Text", "Property City", 100, None),
        "Property_State__c": ("Text", "Property State", 50, None),
        "Property_Zip__c": ("Text", "Property Zip", 20, None),
        "Property_Type__c": ("Text", "Property Type", 100, None),
        "Property_Category__c": ("Text", "Property Category", 50, None),
        "Build_Type__c": ("Text", "Build Type", 100, None),
        "Prospective_ISP__c": ("Text", "Prospective ISP", 255, None),
        "Confirmed_ISP__c": ("Text", "Confirmed ISP", 255, None),
        "Monday_Item_ID__c": ("Text", "Monday Item ID", 50, None),
    }

    created = []
    skipped = []
    for api_name, (ftype, label, length, scale) in fields_to_create.items():
        if api_name in existing:
            skipped.append(api_name)
            continue

        # Use Tooling API to create custom field
        if ftype == "Number":
            metadata = {
                "FullName": f"Opportunity.{api_name}",
                "Metadata": {
                    "label": label,
                    "type": "Number",
                    "precision": length,
                    "scale": scale,
                    "externalId": api_name == "Monday_Item_ID__c",
                    "unique": api_name == "Monday_Item_ID__c",
                },
            }
        else:
            metadata = {
                "FullName": f"Opportunity.{api_name}",
                "Metadata": {
                    "label": label,
                    "type": "Text",
                    "length": length,
                    "externalId": api_name == "Monday_Item_ID__c",
                    "unique": api_name == "Monday_Item_ID__c",
                },
            }

        try:
            result = sf.restful(
                "tooling/sobjects/CustomField",
                method="POST",
                json=metadata,
            )
            created.append(api_name)
            print(f"  Created custom field: {api_name}")
        except SalesforceError as e:
            # If it already exists or there's a duplicate, skip
            if "DUPLICATE" in str(e) or "already exists" in str(e).lower():
                skipped.append(api_name)
            else:
                print(f"  WARNING: Could not create {api_name}: {e}")

    if created:
        print(f"  Created {len(created)} custom fields: {', '.join(created)}")
    if skipped:
        print(f"  Already existed: {len(skipped)} fields")

    # Set Field-Level Security for System Administrator profile
    all_fields = list(fields_to_create.keys())
    _set_field_level_security(sf, all_fields)

    # Small pause for metadata to propagate
    if created:
        print("  Waiting 10s for metadata propagation...")
        time.sleep(10)

    return created, skipped


def _set_field_level_security(sf, field_api_names):
    """Grant read/edit access on custom fields to the System Administrator profile."""
    try:
        profile = sf.query(
            "SELECT Id FROM Profile WHERE Name = 'System Administrator'"
        )
        if not profile["records"]:
            print("  WARNING: Could not find System Administrator profile for FLS")
            return
        profile_id = profile["records"][0]["Id"]
        perm_set = sf.query(
            f"SELECT Id FROM PermissionSet WHERE ProfileId = '{profile_id}'"
        )
        if not perm_set["records"]:
            return
        perm_set_id = perm_set["records"][0]["Id"]

        fls_set = 0
        for api_name in field_api_names:
            try:
                sf.FieldPermissions.create({
                    "ParentId": perm_set_id,
                    "SobjectType": "Opportunity",
                    "Field": f"Opportunity.{api_name}",
                    "PermissionsEdit": True,
                    "PermissionsRead": True,
                })
                fls_set += 1
            except SalesforceError:
                pass  # already set or other non-critical error
        if fls_set:
            print(f"  Set FLS on {fls_set} new fields")
    except Exception as e:
        print(f"  WARNING: FLS setup failed: {e}")


def parse_name(full_name):
    """Split a full name into first and last name."""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return "", "Unknown"
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


# ── SF User mapping ──────────────────────────────────────────────────────

SF_USER_MAP = {
    "pankaj gulati": "005Hs00000Eo9rcIAB",
    "ken carter": "005WR00000153G1YAI",
    "cass parker": "005WR000002ieYTYAY",
    "jake stebbins": "005WR000002nvjxYAA",
    "greg dial": "005WR000002uhFdYAI",
    "lucas dixon": "005WR000002zi6DYAQ",
    "tanya friese": "005WR0000030R1hYAE",
    "rosemarie shortino": "005WR0000030R9lYAE",
    "justin barry": "005WR0000030RCzYAM",
    "kevin sheets": "005WR0000036jGrYAI",
    "melissa baker": "005WR000003CD6DYAW",
    "john fetter": "005WR000003CD7pYAG",
    "scott avanzo": "005WR000003CDZFYA4",
    "jose varela": "005WR000003CDarYAG",
    "david wild": "005WR000003CDfhYAG",
    "jerry lumpkin": "005WR000003CDhJYAW",
    "shane lowry": "005WR000003CDkXYAW",
    "zak dubree": "005WR000003PXwjYAG",
    "craig rodriguez": "005WR000003ZYWXYA4",
    "warren nunley": "005WR000003aLsDYAU",
    "craig birch": "005WR000003dFofYAE",
    "jacob goering": "005WR000003flNpYAI",
    "julian harrell": "005WR000005Ln7hYAC",
    "niraj patel": "005WR000008V4VoYAK",
    "kevin reyes": "005WR000008VPf5YAG",
    "eric dana": "005WR000009NOZ8YAO",
    "taylor mauney": "005WR000009SCtuYAG",
    "jamie doyle": "005WR000009mRITYA2",
    # Monday.com names that may differ
    "chuck mcneely": None,  # not in SF
}

# Stage mapping from Monday group to SF stage
STAGE_MAP = {
    "Prospects": "Prospecting",
    "Under Contract": "Negotiation",
    "Ready for Engineering": "Qualification",
    "Under Construction": "Qualification",
    "Pending Activation": "Qualification",
    "Complete / Activated": "Closed Won",
    "Closed/Lost": "Closed Lost",
}


# ── Main import logic ────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("MONDAY.COM -> SALESFORCE SAMPLE DATA IMPORT")
    print("=" * 70)

    # Connect to Salesforce
    print("\nConnecting to Salesforce...")
    sf = Salesforce(
        username=SF_USERNAME,
        password=SF_PASSWORD,
        security_token=SF_SECURITY_TOKEN,
    )
    print(f"  Connected to: {sf.sf_instance}")

    # ── Step 0: Ensure custom fields exist ────────────────────────────────
    print("\n--- Step 0: Ensuring custom fields on Opportunity ---")
    ensure_custom_fields(sf)

    # ── Step 1: Import Accounts ───────────────────────────────────────────
    print("\n--- Step 1: Importing Accounts from Monday.com ---")
    print("Fetching Accounts board...")
    acct_items = fetch_all_items(BOARD_ACCOUNTS)
    print(f"  Found {len(acct_items)} items")

    acct_created = 0
    acct_failed = 0
    acct_map = {}  # monday item name (lower) -> SF Account Id
    acct_id_map = {}  # monday item id -> SF Account Id

    for item in acct_items:
        name = item["name"].strip()
        if not name:
            continue

        acct_type = get_col_text(item, "status")  # Type column
        monday_id = item["id"]

        description_parts = [f"Monday ID: {monday_id}"]
        if acct_type:
            description_parts.append(f"Type: {acct_type}")

        # Map Monday type to SF Industry if possible
        industry_map = {
            "REIT": "Real Estate",
            "Client": "Technology",
            "Vendor": "Construction",
            "Contractor": "Construction",
            "ISP": "Telecommunications",
        }
        industry = None
        for key, val in industry_map.items():
            if key.lower() in acct_type.lower():
                industry = val
                break

        record = {
            "Name": name[:255],
            "Description": "\n".join(description_parts),
        }
        if industry:
            record["Industry"] = industry

        try:
            result = sf.Account.create(record)
            sf_id = result["id"]
            acct_map[name.lower()] = sf_id
            acct_id_map[monday_id] = sf_id
            acct_created += 1
        except SalesforceError as e:
            print(f"  FAIL Account '{name}': {e}")
            acct_failed += 1

    print(f"  Accounts created: {acct_created}, failed: {acct_failed}")

    # ── Step 2: Import Contacts ───────────────────────────────────────────
    print("\n--- Step 2: Importing Contacts from Monday.com ---")
    print("Fetching Contacts board...")
    contact_items = fetch_all_items(BOARD_CONTACTS)
    print(f"  Found {len(contact_items)} items")

    contact_created = 0
    contact_failed = 0
    contact_no_account = 0

    for item in contact_items:
        name = item["name"].strip()
        if not name:
            continue

        first_name, last_name = parse_name(name)
        phone = get_col_text(item, "phone0")
        email = get_col_text(item, "email")
        title = get_col_text(item, "title5")  # dropdown Title
        contact_type = get_col_text(item, "status")  # Type
        company = get_col_text(item, "text8")  # Company text
        monday_id = item["id"]

        # Try to match company to an Account
        account_id = None
        if company:
            # Exact match first (case insensitive)
            account_id = acct_map.get(company.lower())
            if not account_id:
                # Fuzzy: check if company name is contained in any account name
                for acct_name_lower, acct_sf_id in acct_map.items():
                    if (company.lower() in acct_name_lower
                            or acct_name_lower in company.lower()):
                        account_id = acct_sf_id
                        break

        if not account_id and company:
            contact_no_account += 1

        # Contact has no Description field; use Department for Monday ID
        dept_text = f"Monday ID: {monday_id}"

        record = {
            "FirstName": first_name[:40] if first_name else None,
            "LastName": last_name[:80],
            "Department": dept_text[:80],
        }
        if phone:
            record["Phone"] = phone[:40]
        if email:
            record["Email"] = email[:80]
        if title:
            record["Title"] = title[:128]
        elif contact_type:
            record["Title"] = contact_type[:128]
        if account_id:
            record["AccountId"] = account_id

        # Remove None values
        record = {k: v for k, v in record.items() if v is not None}

        try:
            sf.Contact.create(record)
            contact_created += 1
        except SalesforceError as e:
            print(f"  FAIL Contact '{name}': {e}")
            contact_failed += 1

    print(f"  Contacts created: {contact_created}, failed: {contact_failed}")
    print(f"  Contacts with no account match: {contact_no_account}")

    # ── Step 3: Import Opportunities ──────────────────────────────────────
    print("\n--- Step 3: Importing Opportunities from Monday.com ---")
    print("Fetching Opportunities board...")
    all_opp_items = fetch_all_items(BOARD_OPPS)
    print(f"  Found {len(all_opp_items)} total items")

    # Group items by group title
    groups = {}
    for item in all_opp_items:
        g = item["group"]["title"]
        groups.setdefault(g, []).append(item)

    print("  Group counts:")
    for g, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        print(f"    {g:<40} {len(items):>5}")

    # Select items per the requested distribution
    target = {
        "Prospects": 20,
        "Under Contract": 10,
        "Ready for Engineering": 5,
        "Under Construction": 5,
        "Complete / Activated": 5,
        "Closed/Lost": 5,
    }

    selected = []
    for group_name, count in target.items():
        pool = groups.get(group_name, [])
        if not pool:
            # Try partial match
            for g in groups:
                if group_name.lower() in g.lower():
                    pool = groups[g]
                    break
        take = pool[:count]
        selected.extend(take)
        print(f"  Selected {len(take)} from '{group_name}' (available: {len(pool)})")

    print(f"  Total selected: {len(selected)}")

    # Re-read Opportunity describe to get updated fields
    opp_desc = sf.Opportunity.describe()
    opp_field_names = {f["name"] for f in opp_desc["fields"]}

    opp_created = 0
    opp_failed = 0
    opp_unmapped = set()

    for item in selected:
        name = item["name"].strip()
        if not name:
            continue

        monday_id = item["id"]
        group_title = item["group"]["title"]
        stage = STAGE_MAP.get(group_title, "Prospecting")

        # Parse location column for address
        location_val = get_col_value(item, "location")
        address_text = get_col_text(item, "location")
        loc_city = ""
        loc_state = ""
        loc_zip = ""
        loc_address = address_text

        if isinstance(location_val, dict):
            # Extract structured address parts
            street = location_val.get("street", {})
            if isinstance(street, dict):
                loc_address = street.get("long_name", address_text)
            city = location_val.get("city", {})
            if isinstance(city, dict):
                loc_city = city.get("long_name", "")
            state = location_val.get("state", {})
            if isinstance(state, dict):
                loc_state = state.get("short_name", "")
            zipcode = location_val.get("zipcode", {})
            if isinstance(zipcode, dict):
                loc_zip = zipcode.get("long_name", "")

        # Override with explicit text columns if populated
        city_text = get_col_text(item, "text4")
        state_text = get_col_text(item, "text6")
        zip_text = get_col_text(item, "text27")
        if city_text:
            loc_city = city_text
        if state_text:
            loc_state = state_text
        if zip_text:
            loc_zip = zip_text

        units = get_col_text(item, "numbers5")
        prop_type = get_col_text(item, "status3")
        mdu_sfu = get_col_text(item, "dropdown3")
        build_type_text = get_col_text(item, "label")  # Brownfield/Greenfield
        if not build_type_text:
            build_type_text = get_col_text(item, "dropdown4")  # Build Type
        prosp_isp = get_col_text(item, "dropdown__1")
        conf_isp = get_col_text(item, "dropdown6")
        category = get_col_text(item, "dropdown4__1")
        owner_name = get_col_text(item, "person")

        # Close date
        close_date_text = get_col_text(item, "date_mm0wzyrd")
        if close_date_text and re.match(r"\d{4}-\d{2}-\d{2}", close_date_text):
            close_date = close_date_text[:10]
        elif stage in ("Closed Won", "Closed Lost"):
            close_date = "2026-01-01"
        else:
            close_date = "2026-12-31"

        # For closed stages, ensure close date is in the past
        if stage in ("Closed Won", "Closed Lost") and close_date > "2026-03-10":
            close_date = "2026-01-01"

        # Owner mapping
        owner_id = None
        if owner_name:
            owner_id = SF_USER_MAP.get(owner_name.lower())

        # Build description with unmapped fields
        desc_parts = []
        if category:
            desc_parts.append(f"Category: {category}")
        comments = get_col_text(item, "text")
        if comments:
            desc_parts.append(f"Comments: {comments}")
        portfolio = get_col_text(item, "text8")
        if portfolio:
            desc_parts.append(f"Portfolio: {portfolio}")
        mgmt = get_col_text(item, "text3")
        if mgmt:
            desc_parts.append(f"Management Co: {mgmt}")

        record = {
            "Name": name[:120],
            "StageName": stage,
            "CloseDate": close_date,
        }

        # Add custom fields if they exist on the object
        if "Monday_Item_ID__c" in opp_field_names:
            record["Monday_Item_ID__c"] = str(monday_id)
        if "Units__c" in opp_field_names and units:
            try:
                record["Units__c"] = float(units)
            except ValueError:
                pass
        if "Property_Address__c" in opp_field_names and loc_address:
            record["Property_Address__c"] = loc_address[:255]
        if "Property_City__c" in opp_field_names and loc_city:
            record["Property_City__c"] = loc_city[:100]
        if "Property_State__c" in opp_field_names and loc_state:
            record["Property_State__c"] = loc_state[:50]
        if "Property_Zip__c" in opp_field_names and loc_zip:
            record["Property_Zip__c"] = loc_zip[:20]
        if "Property_Type__c" in opp_field_names and prop_type:
            record["Property_Type__c"] = prop_type[:100]
        if "Property_Category__c" in opp_field_names and mdu_sfu:
            record["Property_Category__c"] = mdu_sfu[:50]
        if "Build_Type__c" in opp_field_names and build_type_text:
            record["Build_Type__c"] = build_type_text[:100]
        if "Prospective_ISP__c" in opp_field_names and prosp_isp:
            record["Prospective_ISP__c"] = prosp_isp[:255]
        if "Confirmed_ISP__c" in opp_field_names and conf_isp:
            record["Confirmed_ISP__c"] = conf_isp[:255]

        # Track unmapped custom fields
        custom_attempted = [
            "Monday_Item_ID__c", "Units__c", "Property_Address__c",
            "Property_City__c", "Property_State__c", "Property_Zip__c",
            "Property_Type__c", "Property_Category__c", "Build_Type__c",
            "Prospective_ISP__c", "Confirmed_ISP__c",
        ]
        for f in custom_attempted:
            if f not in opp_field_names:
                opp_unmapped.add(f)

        # If custom fields not available, stuff into Description
        if opp_unmapped:
            extra = []
            if "Monday_Item_ID__c" not in opp_field_names:
                extra.append(f"Monday ID: {monday_id}")
            if "Units__c" not in opp_field_names and units:
                extra.append(f"Units: {units}")
            if "Property_Address__c" not in opp_field_names and loc_address:
                extra.append(f"Address: {loc_address}")
            if "Property_City__c" not in opp_field_names and loc_city:
                extra.append(f"City: {loc_city}")
            if "Property_State__c" not in opp_field_names and loc_state:
                extra.append(f"State: {loc_state}")
            if "Property_Zip__c" not in opp_field_names and loc_zip:
                extra.append(f"Zip: {loc_zip}")
            if "Property_Type__c" not in opp_field_names and prop_type:
                extra.append(f"Property Type: {prop_type}")
            if "Property_Category__c" not in opp_field_names and mdu_sfu:
                extra.append(f"MDU/SFU/MHP: {mdu_sfu}")
            if "Build_Type__c" not in opp_field_names and build_type_text:
                extra.append(f"Build Type: {build_type_text}")
            if "Prospective_ISP__c" not in opp_field_names and prosp_isp:
                extra.append(f"Prospective ISP: {prosp_isp}")
            if "Confirmed_ISP__c" not in opp_field_names and conf_isp:
                extra.append(f"Confirmed ISP: {conf_isp}")
            desc_parts = extra + desc_parts

        if desc_parts:
            record["Description"] = "\n".join(desc_parts)[:32000]

        if owner_id:
            record["OwnerId"] = owner_id

        try:
            sf.Opportunity.create(record)
            opp_created += 1
        except SalesforceError as e:
            print(f"  FAIL Opp '{name}': {e}")
            opp_failed += 1

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("IMPORT SUMMARY")
    print("=" * 70)
    print(f"  Accounts:      {acct_created} created, {acct_failed} failed")
    print(f"  Contacts:      {contact_created} created, {contact_failed} failed")
    print(f"                 ({contact_no_account} contacts had no Account match)")
    print(f"  Opportunities: {opp_created} created, {opp_failed} failed")
    if opp_unmapped:
        print(f"\n  WARNING: These custom fields could not be created on Opportunity")
        print(f"  (data was stored in Description field as fallback):")
        for f in sorted(opp_unmapped):
            print(f"    - {f}")
    print(f"\n  Total records created: {acct_created + contact_created + opp_created}")
    print("=" * 70)


if __name__ == "__main__":
    main()
