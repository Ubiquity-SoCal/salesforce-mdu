"""
Fix Opportunity owners in Salesforce.

The Monday.com import set most Opportunity owners to Cass Parker (the admin)
because the 'person' column value wasn't parsed correctly. This script:

1. Queries SF Opportunities that have a Monday_Item_ID__c
2. Queries Monday.com for the actual person assigned to each item
3. Resolves Monday person IDs to names via the users API
4. Matches names to SF Users (case-insensitive)
5. Updates OwnerId where it differs
"""

import json
import requests
from simple_salesforce import Salesforce

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

SF_USERNAME = "cass1@ubiquitygp.com"
SF_PASSWORD = "Karate88!"
SF_SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"


def monday_query(q):
    """Execute a Monday.com GraphQL query."""
    resp = requests.post(MONDAY_API_URL, json={"query": q}, headers=MONDAY_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        print(f"  Monday API errors: {data['errors']}")
    return data["data"]


def main():
    print("=" * 70)
    print("FIX OPPORTUNITY OWNERS")
    print("=" * 70)

    # ── Step 1: Connect to Salesforce and get Opportunities ───────────────
    print("\nConnecting to Salesforce...")
    sf = Salesforce(
        username=SF_USERNAME,
        password=SF_PASSWORD,
        security_token=SF_SECURITY_TOKEN,
    )
    print(f"  Connected to: {sf.sf_instance}")

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

    # Build lookup: monday_item_id -> list of SF opp records (may have dupes)
    opp_by_monday_id = {}
    for opp in sf_opps:
        mid = opp["Monday_Item_ID__c"].strip()
        opp_by_monday_id.setdefault(mid, []).append(opp)
    dupes = {k: v for k, v in opp_by_monday_id.items() if len(v) > 1}
    if dupes:
        print(f"  WARNING: {len(dupes)} Monday IDs map to multiple SF Opportunities (duplicates)")
        for mid, opps in dupes.items():
            for o in opps:
                print(f"    Monday ID {mid}: {o['Name']} ({o['Id']})")
    print(f"  Unique Monday Item IDs: {len(opp_by_monday_id)}")

    # ── Step 2: Get board columns to find the person column ID ────────────
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
        # Fallback: try "person"
        person_col_id = "person"
        print(f"  No people-type column found, falling back to id='person'")

    # ── Step 3: Get Monday.com users (ID -> name map) ────────────────────
    print("\nQuerying Monday.com users...")
    user_data = monday_query("""{
      users {
        id name email
      }
    }""")
    monday_users = {int(u["id"]): u["name"] for u in user_data["users"]}
    print(f"  Found {len(monday_users)} Monday.com users")
    for uid, uname in sorted(monday_users.items()):
        print(f"    {uid}: {uname}")

    # Alias map: Monday.com display names that don't match SF names exactly
    MONDAY_NAME_ALIASES = {
        "pankaj@ubiquitygp.com": "Pankaj Gulati",
        # Add more aliases here as needed
    }

    # ── Step 4: Fetch Monday items and extract person assignments ─────────
    print("\nFetching Opportunities board items from Monday.com...")
    monday_item_ids = list(opp_by_monday_id.keys())

    # Fetch all items with pagination
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
    monday_owner_map = {}  # monday_item_id -> owner_name (lowercase)
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
                # Take the first person
                person_id = persons[0].get("id")
                if person_id and int(person_id) in monday_users:
                    owner_name = monday_users[int(person_id)]
                    # Apply alias if the Monday name doesn't match SF
                    owner_name = MONDAY_NAME_ALIASES.get(owner_name, owner_name)
                    monday_owner_map[item_id] = owner_name
                    break

    print(f"  Matched {len(monday_owner_map)} items to Monday.com owners")

    # Check which SF Monday IDs weren't found in the board at all
    monday_board_ids = {item["id"] for item in all_items}
    not_in_board = [mid for mid in opp_by_monday_id if mid not in monday_board_ids]
    in_board_no_person = [mid for mid in opp_by_monday_id
                          if mid in monday_board_ids and mid not in monday_owner_map]
    print(f"  Monday IDs not found in board: {len(not_in_board)}")
    print(f"  In board but no person assigned: {len(in_board_no_person)}")

    # ── Step 5: Get Salesforce Users and build name -> SF User ID map ─────
    print("\nQuerying Salesforce Users (active)...")
    sf_users_result = sf.query_all(
        "SELECT Id, Name, IsActive FROM User WHERE IsActive = true"
    )
    sf_user_by_name = {}
    for u in sf_users_result["records"]:
        sf_user_by_name[u["Name"].lower()] = u["Id"]
        print(f"    {u['Name']:30s} -> {u['Id']}")

    # Also check for inactive users that might match unresolved names
    print("\n  Checking for inactive SF users named Brett Spivey or Chuck McNeely...")
    inactive_result = sf.query_all(
        "SELECT Id, Name, IsActive FROM User WHERE Name = 'Brett Spivey' OR Name = 'Chuck McNeely'"
    )
    for u in inactive_result["records"]:
        status = "ACTIVE" if u["IsActive"] else "INACTIVE"
        print(f"    Found: {u['Name']} ({status}) -> {u['Id']}")
        if u["IsActive"]:
            sf_user_by_name[u["Name"].lower()] = u["Id"]

    # ── Step 6: Compare and update ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("COMPARING OWNERS")
    print("=" * 70)

    # Build reverse lookup: SF user ID -> name for display
    sf_user_name_by_id = {}
    for u in sf_users_result["records"]:
        sf_user_name_by_id[u["Id"]] = u["Name"]

    updated = 0
    skipped_no_monday_owner = 0
    skipped_no_sf_match = 0
    skipped_already_correct = 0
    failed = 0
    unmatched_names = {}  # name -> count

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

            # SF IDs may differ in length (15 vs 18 char). Compare first 15.
            if current_owner_id[:15] == target_sf_user_id[:15]:
                skipped_already_correct += 1
                continue

            current_owner_name = sf_user_name_by_id.get(current_owner_id, current_owner_id)
            changes.append({
                "opp_id": sf_opp["Id"],
                "opp_name": opp_name,
                "monday_id": monday_id,
                "from_name": current_owner_name,
                "from_id": current_owner_id,
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
        return

    print(f"\n{'Opportunity':<45} {'From':<25} {'To':<25}")
    print("-" * 95)
    for c in changes:
        print(f"  {c['opp_name']:<43} {c['from_name']:<25} {c['to_name']:<25}")

    # Apply updates
    print(f"\nApplying {len(changes)} owner updates...")
    for c in changes:
        try:
            sf.Opportunity.update(c["opp_id"], {"OwnerId": c["to_id"]})
            updated += 1
            print(f"  OK: {c['opp_name']} -> {c['to_name']}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {c['opp_name']}: {e}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Opportunities checked:     {len(sf_opps)}")
    print(f"  Already correct:           {skipped_already_correct}")
    print(f"  Updated successfully:      {updated}")
    print(f"  Failed to update:          {failed}")
    print(f"  No Monday owner found:     {skipped_no_monday_owner}")
    print(f"  No SF user match:          {skipped_no_sf_match}")
    if unmatched_names:
        print(f"  Unmatched names:")
        for uname, cnt in sorted(unmatched_names.items()):
            print(f"    {uname}: {cnt} opps")
    print("=" * 70)


if __name__ == "__main__":
    main()
