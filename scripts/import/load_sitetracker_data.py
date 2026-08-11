from simple_salesforce import Salesforce
from datetime import datetime
import json

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_ST = _sf_creds("st")

_SF = _sf_creds()


# Connect to both orgs
sf_main = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
sf_st = Salesforce(username=_ST["username"], password=_ST["password"], security_token=_ST["token"])

# Step 1: Pull all MDU Fiber records from SiteTracker (not cancelled)
print("Pulling MDU Fiber data from SiteTracker...")
query = """SELECT Id, Name,
    Project__r.sitetracker__Site__r.Name,
    Project__r.sitetracker__Site__r.Monday_com_name__c,
    Project__r.sitetracker__Site__r.sitetracker__City__c,
    Project__r.sitetracker__Site__r.sitetracker__State__c,
    Project__r.sitetracker__Site__r.sitetracker__Site_Status__c,
    Project__r.sitetracker__Site__r.MDU_Site_Category__c,
    MDU_Build_Status__c,
    MDU_Activation_F__c,
    MDU_Activation_A__c,
    Premise_Access_License_PAL_A__c
    FROM MDU_Fiber__c
    WHERE Project__r.sitetracker__Site__r.sitetracker__Site_Type__c = 'MDU'
    AND Project__r.sitetracker__Project_Status__c != 'Cancelled'
    ORDER BY Name"""

st_records = []
result = sf_st.query(query)
st_records.extend(result['records'])
while not result['done']:
    result = sf_st.query_more(result['nextRecordsUrl'], True)
    st_records.extend(result['records'])

print(f"  Got {len(st_records)} MDU Fiber records from SiteTracker")

# Step 2: Get all Opportunities from main org for matching
print("Getting Opportunities from main org...")
opps = sf_main.query_all("SELECT Id, Name FROM Opportunity WHERE RecordType.Name = 'MDU'")
opp_map = {}
for o in opps['records']:
    name_lower = o['Name'].strip().lower()
    opp_map[name_lower] = o['Id']
print(f"  Got {len(opp_map)} MDU Opportunities")

# Step 3: Build records to insert
now_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
to_insert = []
matched = 0
unmatched = 0

for r in st_records:
    site = (r.get('Project__r') or {}).get('sitetracker__Site__r') or {}
    monday_name = site.get('Monday_com_name__c') or ''
    site_name = site.get('Name') or ''

    # Try to match to an Opportunity
    opp_id = None
    # Try monday name first
    if monday_name:
        opp_id = opp_map.get(monday_name.strip().lower())
    # Try site name (often has Market_MDU_Name format, extract the name part)
    if not opp_id and site_name:
        # Try full site name
        opp_id = opp_map.get(site_name.strip().lower())
        # Try extracting name after last underscore (e.g., Mesa_MDU_Dobson Bay Club HOA -> Dobson Bay Club HOA)
        if not opp_id and '_MDU_' in site_name:
            short_name = site_name.split('_MDU_', 1)[1]
            opp_id = opp_map.get(short_name.strip().lower())

    if opp_id:
        matched += 1
    else:
        unmatched += 1

    record = {
        'Name': r['Name'],  # Project number like P-002258
        'Site_Name__c': site_name,
        'Monday_Name__c': monday_name or site_name,
        'City__c': site.get('sitetracker__City__c'),
        'State__c': site.get('sitetracker__State__c'),
        'Site_Status__c': site.get('sitetracker__Site_Status__c'),
        'Build_Status__c': r.get('MDU_Build_Status__c'),
        'PAL_Signed_Date__c': r.get('Premise_Access_License_PAL_A__c'),
        'Activation_Forecast__c': r.get('MDU_Activation_F__c'),
        'Activation_Actual__c': r.get('MDU_Activation_A__c'),
        'MDU_Category__c': site.get('MDU_Site_Category__c'),
        'SiteTracker_Record_Id__c': r['Id'],
        'Last_Synced__c': now_str,
    }
    if opp_id:
        record['Opportunity__c'] = opp_id

    to_insert.append(record)

print(f"\n  Matched to Opportunities: {matched}")
print(f"  No match (standalone): {unmatched}")
print(f"  Total to insert: {len(to_insert)}")

# Step 4: Bulk insert into main org
print("\nInserting into main Salesforce org...")
batch_size = 200
success_count = 0
error_count = 0

for i in range(0, len(to_insert), batch_size):
    batch = to_insert[i:i+batch_size]
    # Use individual inserts for reliability
    for rec in batch:
        try:
            sf_main.SiteTracker_Project__c.create(rec)
            success_count += 1
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"  Error: {rec['Name']} - {e}")
    print(f"  Processed {min(i+batch_size, len(to_insert))}/{len(to_insert)} ({success_count} ok, {error_count} errors)")

print(f"\nDone! {success_count} SiteTracker projects loaded, {error_count} errors")
print(f"  {matched} linked to Opportunities, {unmatched} standalone")
