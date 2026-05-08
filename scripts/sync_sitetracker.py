import sys
from simple_salesforce import Salesforce
from datetime import datetime, timezone

# Force unbuffered output so SSE receives lines immediately
sys.stdout.reconfigure(line_buffering=True)

# Connect to both orgs
print("[INFO] Connecting to main Salesforce org...")
sf_main = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Karate88!',
    security_token='Ktc1n9mLmD9vwEcVcl45q0iAD'
)

print("[INFO] Connecting to SiteTracker org...")
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='Hawaiian84',
    security_token='fe2pen6ceQeqGhWXhBeOIjqP'
)

# Step 1: Pull all MDU Fiber records from SiteTracker (not cancelled)
print("[INFO] Pulling MDU Fiber data from SiteTracker...")
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
    AND Project__r.sitetracker__Site__r.sitetracker__Site_Status__c != 'Cancelled'
    AND MDU_Build_Status__c != null
    ORDER BY Name"""

st_records = []
result = sf_st.query(query)
st_records.extend(result['records'])
while not result['done']:
    result = sf_st.query_more(result['nextRecordsUrl'], True)
    st_records.extend(result['records'])

print(f"[INFO] Pulled {len(st_records)} MDU Fiber records from SiteTracker")

# Step 2: Build records for upsert
now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
to_upsert = []

for r in st_records:
    site = (r.get('Project__r') or {}).get('sitetracker__Site__r') or {}
    monday_name = site.get('Monday_com_name__c') or ''
    site_name = site.get('Name') or ''

    record = {
        'Name': r['Name'],
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
    to_upsert.append(record)

print(f"[INFO] Total to upsert: {len(to_upsert)}")

# Step 3: Upsert into main org using SiteTracker_Record_Id__c as external ID
# Does NOT touch Opportunity__c — that link is managed manually in SF
print("[INFO] Upserting into main Salesforce org...")
total = len(to_upsert)
created_count = 0
updated_count = 0
error_count = 0

for i, rec in enumerate(to_upsert):
    st_id = rec.pop('SiteTracker_Record_Id__c')
    try:
        result = sf_main.SiteTracker_Project__c.upsert(
            f"SiteTracker_Record_Id__c/{st_id}", rec
        )
        if isinstance(result, int):
            updated_count += 1
        else:
            created_count += 1
    except Exception as e:
        error_count += 1
        print(f"[ERROR] {rec.get('Name', 'unknown')} - {e}")

    if (i + 1) % 25 == 0 or (i + 1) == total:
        print(f"[PROGRESS] {i + 1}/{total}")

if error_count > 0:
    print(f"[ERROR] Completed with {error_count} errors. {created_count} added, {updated_count} updated, {error_count} failed")
else:
    print(f"[SUCCESS] Done! {created_count} added, {updated_count} updated, 0 errors")
