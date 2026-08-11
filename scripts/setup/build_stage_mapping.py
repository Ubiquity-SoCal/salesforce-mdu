"""
Build a mapping of Monday.com item IDs -> correct Salesforce stages.
Queries SF for Opportunities with Monday_Item_ID__c, then queries Monday.com
for each item's group title, and outputs a JSON mapping file.

Does NOT update Salesforce — mapping file is consumed by a separate update script.
"""

import json
import requests
from simple_salesforce import Salesforce
import os as _os

# --- Config ---
MONDAY_API_TOKEN = open(r"C:\Users\cass\Work_Projects\Monday.com\Monday.com_Key.txt").read().strip()
MONDAY_BOARD_ID = 3036443295

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

OUTPUT_PATH = r"C:\Users\cass\Work_Projects\SalesForce\stage_mapping.json"

# Monday group -> Salesforce stage
GROUP_TO_STAGE = {
    "Prospects": "Prospecting",
    "Under Contract": "Under Contract",
    "Ready for Engineering": "Ready for Engineering",
    "Under Construction": "Under Construction",
    "Pending Activation": "Activation",
    "Complete / Activated": "Closed Won",
    "Closed/Lost": "Closed Lost",
}

# --- Step 1: Query Salesforce for Opportunities with Monday_Item_ID__c ---
print("Connecting to Salesforce...")
sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_SECURITY_TOKEN)

query = """
    SELECT Id, Name, Monday_Item_ID__c, StageName
    FROM Opportunity
    WHERE Monday_Item_ID__c != null
"""
result = sf.query_all(query)
sf_opps = result["records"]
print(f"Found {len(sf_opps)} Salesforce Opportunities with Monday_Item_ID__c")

# Build lookup: monday_item_id -> SF record
sf_by_monday_id = {}
for opp in sf_opps:
    mid = str(opp["Monday_Item_ID__c"]).strip()
    sf_by_monday_id[mid] = {
        "sf_opp_id": opp["Id"],
        "sf_opp_name": opp["Name"],
        "current_sf_stage": opp["StageName"],
    }

monday_item_ids = list(sf_by_monday_id.keys())
print(f"Monday item IDs to look up: {len(monday_item_ids)}")

# --- Step 2: Query Monday.com for item group titles ---
# Monday API allows querying items by ID in batches
print("\nQuerying Monday.com for item groups...")

MONDAY_URL = "https://api.monday.com/v2"
headers = {
    "Authorization": MONDAY_API_TOKEN,
    "Content-Type": "application/json",
    "API-Version": "2024-10",
}

# Query in batches of 100 (Monday limits)
BATCH_SIZE = 100
monday_items = {}  # item_id -> group_title

for i in range(0, len(monday_item_ids), BATCH_SIZE):
    batch = monday_item_ids[i : i + BATCH_SIZE]
    ids_list = ", ".join(batch)

    query_gql = f"""
    {{
        items(ids: [{ids_list}]) {{
            id
            name
            group {{
                title
            }}
        }}
    }}
    """

    resp = requests.post(MONDAY_URL, json={"query": query_gql}, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        print(f"  Monday API errors: {data['errors']}")
        continue

    items = data.get("data", {}).get("items", [])
    for item in items:
        monday_items[str(item["id"])] = item["group"]["title"]

    print(f"  Batch {i // BATCH_SIZE + 1}: got {len(items)} items")

print(f"Retrieved group info for {len(monday_items)} Monday items")

# --- Step 3: Build the mapping ---
print("\nBuilding stage mapping...")

mapping = {}
unmapped_groups = set()
missing_from_monday = []
stage_change_counts = {}
already_correct = 0

for mid, sf_info in sf_by_monday_id.items():
    group_title = monday_items.get(mid)

    if group_title is None:
        missing_from_monday.append(mid)
        continue

    correct_stage = GROUP_TO_STAGE.get(group_title)

    if correct_stage is None:
        unmapped_groups.add(group_title)
        continue

    mapping[mid] = {
        "sf_opp_id": sf_info["sf_opp_id"],
        "sf_opp_name": sf_info["sf_opp_name"],
        "monday_group": group_title,
        "correct_sf_stage": correct_stage,
        "current_sf_stage": sf_info["current_sf_stage"],
        "needs_update": sf_info["current_sf_stage"] != correct_stage,
    }

    if sf_info["current_sf_stage"] == correct_stage:
        already_correct += 1
    else:
        key = f"{sf_info['current_sf_stage']} -> {correct_stage}"
        stage_change_counts[key] = stage_change_counts.get(key, 0) + 1

# --- Step 4: Write JSON ---
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(mapping, f, indent=2, ensure_ascii=False)

print(f"\nMapping written to: {OUTPUT_PATH}")

# --- Step 5: Summary ---
needs_update = sum(1 for v in mapping.values() if v["needs_update"])

print("\n" + "=" * 60)
print("STAGE MAPPING SUMMARY")
print("=" * 60)
print(f"Total SF Opps with Monday ID:   {len(sf_opps)}")
print(f"Matched to Monday groups:        {len(mapping)}")
print(f"Missing from Monday board:       {len(missing_from_monday)}")
if unmapped_groups:
    print(f"Unmapped Monday groups:          {unmapped_groups}")
print(f"Already at correct stage:        {already_correct}")
print(f"Need stage update:               {needs_update}")

if stage_change_counts:
    print(f"\nStage changes needed:")
    for change, count in sorted(stage_change_counts.items(), key=lambda x: -x[1]):
        print(f"  {change}: {count}")

if missing_from_monday:
    print(f"\nMonday IDs not found on board (may be deleted):")
    for mid in missing_from_monday[:10]:
        info = sf_by_monday_id[mid]
        print(f"  {mid} - {info['sf_opp_name']}")
    if len(missing_from_monday) > 10:
        print(f"  ... and {len(missing_from_monday) - 10} more")
