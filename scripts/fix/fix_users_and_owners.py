"""
Fix Users, Duplicates, and Owners in Salesforce.

Task 1: Create inactive/non-login users for Brett Spivey and Chuck McNeely
Task 2: Delete duplicate Opportunities (by Monday_Item_ID__c)
Task 3: Re-run owner fix using Monday.com person assignments
"""

import json
import requests
from collections import defaultdict
from simple_salesforce import Salesforce
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

# ── Users to create ───────────────────────────────────────────────────────

USERS_TO_CREATE = [
    {
        "FirstName": "Brett",
        "LastName": "Spivey",
        "Email": "bspivey@ubiquitygp.com",
        "Username": "bspivey@ubiquitygp.com.mdu",
        "Alias": "bspive",
    },
    {
        "FirstName": "Chuck",
        "LastName": "McNeely",
        "Email": "cmcneely@ubiquitygp.com",
        "Username": "cmcneely@ubiquitygp.com.mdu",
        "Alias": "cmcnee",
    },
]

# Alias map: Monday.com display names that don't match SF names exactly
MONDAY_NAME_ALIASES = {
    "pankaj@ubiquitygp.com": "Pankaj Gulati",
}


def monday_query(q):
    """Execute a Monday.com GraphQL query."""
    resp = requests.post(MONDAY_API_URL, json={"query": q}, headers=MONDAY_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        print(f"  Monday API errors: {data['errors']}")
    return data["data"]


def connect_sf():
    """Connect to Salesforce and return the client."""
    print("Connecting to Salesforce...")
    sf = Salesforce(
        username=SF_USERNAME,
        password=SF_PASSWORD,
        security_token=SF_SECURITY_TOKEN,
    )
    print(f"  Connected to: {sf.sf_instance}")
    return sf


# ═════════════════════════════════════════════════════════════════════════
# TASK 1: Create Users
# ═════════════════════════════════════════════════════════════════════════

def task1_create_users(sf):
    print("\n" + "=" * 70)
    print("TASK 1: CREATE SALESFORCE USERS")
    print("=" * 70)

    created = []
    skipped = []

    # Check if users already exist
    for user_def in USERS_TO_CREATE:
        full_name = f"{user_def['FirstName']} {user_def['LastName']}"
        print(f"\nChecking if '{full_name}' already exists...")
        result = sf.query(
            f"SELECT Id, Name, IsActive, Username FROM User "
            f"WHERE FirstName = '{user_def['FirstName']}' "
            f"AND LastName = '{user_def['LastName']}'"
        )
        if result["totalSize"] > 0:
            for u in result["records"]:
                status = "Active" if u["IsActive"] else "Inactive"
                print(f"  Already exists: {u['Name']} ({status}) - {u['Username']} -> {u['Id']}")
            skipped.append(full_name)
            continue

        # Also check by username
        result2 = sf.query(
            f"SELECT Id, Name, IsActive FROM User "
            f"WHERE Username = '{user_def['Username']}'"
        )
        if result2["totalSize"] > 0:
            for u in result2["records"]:
                print(f"  Username already taken: {u['Name']} -> {u['Id']}")
            skipped.append(full_name)
            continue

    if skipped and len(skipped) == len(USERS_TO_CREATE):
        print("\n  All users already exist. Skipping creation.")
        return

    # Get Profile ID for Standard User (or Minimum Access)
    print("\nQuerying for available Profiles...")
    profiles = sf.query(
        "SELECT Id, Name FROM Profile WHERE Name = 'Standard User' "
        "OR Name = 'Minimum Access - Salesforce' ORDER BY Name"
    )
    if profiles["totalSize"] == 0:
        print("  ERROR: No suitable profile found!")
        return
    profile_id = profiles["records"][0]["Id"]
    profile_name = profiles["records"][0]["Name"]
    print(f"  Using profile: {profile_name} ({profile_id})")

    # Create each user
    for user_def in USERS_TO_CREATE:
        full_name = f"{user_def['FirstName']} {user_def['LastName']}"
        if full_name in skipped:
            continue

        record = {
            "FirstName": user_def["FirstName"],
            "LastName": user_def["LastName"],
            "Email": user_def["Email"],
            "Username": user_def["Username"],
            "Alias": user_def["Alias"],
            "ProfileId": profile_id,
            "EmailEncodingKey": "UTF-8",
            "LanguageLocaleKey": "en_US",
            "LocaleSidKey": "en_US",
            "TimeZoneSidKey": "America/Chicago",
            "IsActive": True,
        }

        print(f"\n  Creating user: {full_name}...")
        try:
            result = sf.User.create(
                record,
                headers={"Sforce-Auto-Assign": "false"}
            )
            if result.get("success"):
                print(f"    SUCCESS: {full_name} -> {result['id']}")
                created.append(full_name)
            else:
                print(f"    FAILED: {result}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\n  TASK 1 SUMMARY: Created {len(created)}, Skipped {len(skipped)}")
    for name in created:
        print(f"    Created: {name}")
    for name in skipped:
        print(f"    Skipped (already exists): {name}")


# ═════════════════════════════════════════════════════════════════════════
# TASK 2: Delete Duplicate Opportunities
# ═════════════════════════════════════════════════════════════════════════

def task2_delete_duplicates(sf):
    print("\n" + "=" * 70)
    print("TASK 2: DELETE DUPLICATE OPPORTUNITIES")
    print("=" * 70)

    print("\nQuerying Opportunities with Monday_Item_ID__c...")
    result = sf.query_all(
        "SELECT Id, Name, Monday_Item_ID__c, CreatedDate "
        "FROM Opportunity WHERE Monday_Item_ID__c != null "
        "ORDER BY CreatedDate ASC"
    )
    opps = result["records"]
    print(f"  Found {len(opps)} Opportunities with Monday Item IDs")

    # Group by Monday_Item_ID__c
    groups = defaultdict(list)
    for opp in opps:
        mid = opp["Monday_Item_ID__c"].strip()
        groups[mid].append(opp)

    # Find duplicates (groups with more than 1)
    dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}

    if not dupe_groups:
        print("  No duplicates found!")
        return 0

    print(f"\n  Found {len(dupe_groups)} Monday IDs with duplicate Opportunities:")
    to_delete = []
    for mid, opp_list in dupe_groups.items():
        # Already sorted by CreatedDate ASC, keep the first (oldest)
        keep = opp_list[0]
        delete_these = opp_list[1:]
        print(f"\n  Monday ID {mid}: {len(opp_list)} records")
        print(f"    KEEP:   {keep['Name']} ({keep['Id']}) created {keep['CreatedDate']}")
        for d in delete_these:
            print(f"    DELETE: {d['Name']} ({d['Id']}) created {d['CreatedDate']}")
            to_delete.append(d["Id"])

    print(f"\n  Deleting {len(to_delete)} duplicate Opportunities...")
    deleted = 0
    failed = 0
    for opp_id in to_delete:
        try:
            sf.Opportunity.delete(opp_id)
            deleted += 1
        except Exception as e:
            failed += 1
            print(f"    FAIL deleting {opp_id}: {e}")

    print(f"\n  TASK 2 SUMMARY: Deleted {deleted} duplicates, Failed {failed}")
    return deleted


# ═════════════════════════════════════════════════════════════════════════
# TASK 3: Fix Opportunity Owners
# ═════════════════════════════════════════════════════════════════════════

def task3_fix_owners(sf):
    print("\n" + "=" * 70)
    print("TASK 3: FIX OPPORTUNITY OWNERS")
    print("=" * 70)

    # ── Query SF Opportunities ────────────────────────────────────────────
    print("\nQuerying Opportunities with Monday_Item_ID__c...")
    result = sf.query_all(
        "SELECT Id, Name, Monday_Item_ID__c, OwnerId FROM Opportunity "
        "WHERE Monday_Item_ID__c != null"
    )
    sf_opps = result["records"]
    print(f"  Found {len(sf_opps)} Opportunities with Monday Item IDs")

    if not sf_opps:
        print("  Nothing to fix.")
        return

    opp_by_monday_id = {}
    for opp in sf_opps:
        mid = opp["Monday_Item_ID__c"].strip()
        opp_by_monday_id.setdefault(mid, []).append(opp)
    print(f"  Unique Monday Item IDs: {len(opp_by_monday_id)}")

    # ── Get Monday.com board columns ──────────────────────────────────────
    print("\nQuerying Monday.com board columns...")
    col_data = monday_query(f"""{{
      boards(ids: {BOARD_OPPS}) {{
        columns {{ id title type }}
      }}
    }}""")
    columns = col_data["boards"][0]["columns"]
    person_col_id = None
    for col in columns:
        if col["type"] in ("people", "multiple-person"):
            person_col_id = col["id"]
            print(f"  Found people column: '{person_col_id}' (title: {col['title']})")
    if not person_col_id:
        person_col_id = "person"
        print(f"  No people-type column found, falling back to id='person'")

    # ── Get Monday.com users ──────────────────────────────────────────────
    print("\nQuerying Monday.com users...")
    user_data = monday_query("""{
      users {
        id name email
      }
    }""")
    monday_users = {int(u["id"]): u["name"] for u in user_data["users"]}
    print(f"  Found {len(monday_users)} Monday.com users")

    # ── Fetch Monday items with person column ─────────────────────────────
    print("\nFetching Opportunities board items from Monday.com...")
    all_items = []
    data = monday_query(f"""{{
      boards(ids: {BOARD_OPPS}) {{
        items_page(limit: 500) {{
          cursor
          items {{
            id name
            column_values(ids: ["{person_col_id}"]) {{ id value text }}
          }}
        }}
      }}
    }}""")
    page = data["boards"][0]["items_page"]
    all_items.extend(page["items"])
    cursor = page["cursor"]

    while cursor:
        data = monday_query(f"""{{
      next_items_page(limit: 500, cursor: "{cursor}") {{
        cursor
        items {{
          id name
          column_values(ids: ["{person_col_id}"]) {{ id value text }}
        }}
      }}
    }}""")
        page = data["next_items_page"]
        all_items.extend(page["items"])
        cursor = page["cursor"]

    print(f"  Fetched {len(all_items)} total Monday items")

    # Build monday_item_id -> owner name
    monday_owner_map = {}
    for item in all_items:
        item_id = item["id"]
        if item_id not in opp_by_monday_id:
            continue
        for cv in item["column_values"]:
            raw = cv.get("value")
            if not raw or raw == "null":
                continue
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            persons = parsed.get("personsAndTeams", [])
            if persons:
                person_id = persons[0].get("id")
                if person_id and int(person_id) in monday_users:
                    owner_name = monday_users[int(person_id)]
                    owner_name = MONDAY_NAME_ALIASES.get(owner_name, owner_name)
                    monday_owner_map[item_id] = owner_name
                    break

    print(f"  Matched {len(monday_owner_map)} items to Monday.com owners")

    # ── Get ALL Salesforce Users (active) ─────────────────────────────────
    print("\nQuerying Salesforce Users...")
    sf_users_result = sf.query_all(
        "SELECT Id, Name, IsActive FROM User WHERE IsActive = true"
    )
    sf_user_by_name = {}
    sf_user_name_by_id = {}
    for u in sf_users_result["records"]:
        sf_user_by_name[u["Name"].lower()] = u["Id"]
        sf_user_name_by_id[u["Id"]] = u["Name"]
        print(f"    {u['Name']:30s} -> {u['Id']}")

    # ── Compare and update ────────────────────────────────────────────────
    print(f"\n  Comparing owners...")

    updated = 0
    skipped_no_monday_owner = 0
    skipped_no_sf_match = 0
    skipped_already_correct = 0
    failed = 0
    unmatched_names = {}
    changes = []

    for monday_id, sf_opp_list in opp_by_monday_id.items():
        for sf_opp in sf_opp_list:
            opp_name = sf_opp["Name"]
            current_owner_id = sf_opp["OwnerId"]

            if monday_id not in monday_owner_map:
                skipped_no_monday_owner += 1
                continue

            monday_owner_name = monday_owner_map[monday_id]
            target_sf_user_id = sf_user_by_name.get(monday_owner_name.lower())

            if not target_sf_user_id:
                skipped_no_sf_match += 1
                unmatched_names[monday_owner_name] = unmatched_names.get(monday_owner_name, 0) + 1
                continue

            if current_owner_id[:15] == target_sf_user_id[:15]:
                skipped_already_correct += 1
                continue

            current_owner_name = sf_user_name_by_id.get(current_owner_id, current_owner_id)
            changes.append({
                "opp_id": sf_opp["Id"],
                "opp_name": opp_name,
                "from_name": current_owner_name,
                "to_name": monday_owner_name,
                "to_id": target_sf_user_id,
            })

    print(f"\n  Changes to make: {len(changes)}")
    print(f"  Already correct: {skipped_already_correct}")
    print(f"  No Monday owner found: {skipped_no_monday_owner}")
    print(f"  No SF user match: {skipped_no_sf_match}")
    if unmatched_names:
        print(f"  Unmatched Monday names:")
        for uname, cnt in sorted(unmatched_names.items()):
            print(f"    {uname}: {cnt} opps")

    if not changes:
        print("\n  No changes needed!")
        return 0, skipped_already_correct, skipped_no_sf_match, unmatched_names

    print(f"\n  {'Opportunity':<45} {'From':<25} {'To':<25}")
    print("  " + "-" * 95)
    for c in changes:
        print(f"  {c['opp_name']:<45} {c['from_name']:<25} {c['to_name']:<25}")

    print(f"\n  Applying {len(changes)} owner updates...")
    for c in changes:
        try:
            sf.Opportunity.update(c["opp_id"], {"OwnerId": c["to_id"]})
            updated += 1
            print(f"    OK: {c['opp_name']} -> {c['to_name']}")
        except Exception as e:
            failed += 1
            print(f"    FAIL: {c['opp_name']}: {e}")

    print(f"\n  TASK 3 SUMMARY:")
    print(f"    Updated:          {updated}")
    print(f"    Failed:           {failed}")
    print(f"    Already correct:  {skipped_already_correct}")
    print(f"    No Monday owner:  {skipped_no_monday_owner}")
    print(f"    No SF user match: {skipped_no_sf_match}")

    return updated, skipped_already_correct, skipped_no_sf_match, unmatched_names


# ═════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("SALESFORCE: FIX USERS, DUPLICATES, AND OWNERS")
    print("=" * 70)

    sf = connect_sf()

    # Task 1: Create users
    task1_create_users(sf)

    # Task 2: Delete duplicates
    dupes_deleted = task2_delete_duplicates(sf)

    # Task 3: Fix owners
    task3_fix_owners(sf)

    print("\n" + "=" * 70)
    print("ALL TASKS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
