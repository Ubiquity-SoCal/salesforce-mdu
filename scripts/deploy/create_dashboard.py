from simple_salesforce import Salesforce
import requests, json

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

# Step 1: Create report folder via Folders API
print("Creating MDU report folder...")
resp = requests.post(
    f'https://{sf.sf_instance}/services/data/v59.0/folders',
    headers=headers,
    json={
        "name": "MDU Sales Reports",
        "developerName": "MDU_Sales_Reports",
        "accessType": "Public",
        "type": "Report"
    }
)
print(f'  Folder: {resp.status_code}')
if resp.status_code in (200, 201):
    folder_id = resp.json().get('id')
else:
    print(f'  {resp.text[:300]}')
    # Try finding existing
    resp2 = requests.get(f'{sf.base_url}query/?q=SELECT+Id,Name,DeveloperName+FROM+Folder+WHERE+DeveloperName=%27MDU_Sales_Reports%27', headers=headers)
    recs = resp2.json().get('records', [])
    if recs:
        folder_id = recs[0]['Id']
    else:
        folder_id = None
print(f'  Folder ID: {folder_id}')

# Step 2: Create dashboard folder
print("Creating MDU dashboard folder...")
resp = requests.post(
    f'https://{sf.sf_instance}/services/data/v59.0/folders',
    headers=headers,
    json={
        "name": "MDU Sales Dashboards",
        "developerName": "MDU_Sales_Dashboards",
        "accessType": "Public",
        "type": "Dashboard"
    }
)
print(f'  Dashboard folder: {resp.status_code}')
if resp.status_code in (200, 201):
    dash_folder_id = resp.json().get('id')
else:
    print(f'  {resp.text[:300]}')
    resp2 = requests.get(f'{sf.base_url}query/?q=SELECT+Id,Name,DeveloperName+FROM+Folder+WHERE+DeveloperName=%27MDU_Sales_Dashboards%27', headers=headers)
    recs = resp2.json().get('records', [])
    dash_folder_id = recs[0]['Id'] if recs else None
print(f'  Dashboard Folder ID: {dash_folder_id}')

# Step 3: Describe the Opportunity report type to get correct field names
print("\nDescribing Opportunity report type...")
desc = requests.get(f'{sf.base_url}analytics/report-types/Opportunity', headers=headers)
fields = desc.json().get('reportExtendedMetadata', {}).get('detailColumnInfo', {})
# Find Units field name
for k, v in fields.items():
    if 'unit' in k.lower() or 'unit' in v.get('label', '').lower():
        print(f'  Found: {k} = {v["label"]}')

def create_report(name, report_def):
    resp = requests.post(f'{sf.base_url}analytics/reports', headers=headers, json=report_def)
    print(f'  {name}: {resp.status_code}')
    if resp.status_code in (200, 201):
        report_id = resp.json().get('attributes', {}).get('reportId')
        print(f'    ID: {report_id}')
        return report_id
    else:
        print(f'    {resp.text[:400]}')
        return None

print("\nCreating reports...")

# Report 1: Opps by Stage
r1 = create_report("Opps by Stage", {
    "reportMetadata": {
        "name": "MDU Opportunities by Stage",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "SUMMARY",
        "detailColumns": ["OPPORTUNITY_NAME", "ACCOUNT_NAME", "Opportunity.Units__c", "Opportunity.Property_State__c"],
        "groupingsDown": [
            {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["RowCount", "s!Opportunity.Units__c"],
        "reportBooleanFilter": None,
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

# Report 2: Opps by Owner
r2 = create_report("Opps by Owner", {
    "reportMetadata": {
        "name": "MDU Opportunities by Owner",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "SUMMARY",
        "detailColumns": ["OPPORTUNITY_NAME", "STAGE_NAME", "Opportunity.Units__c"],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["RowCount", "s!Opportunity.Units__c"],
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

# Report 3: Opps by State
r3 = create_report("Opps by State", {
    "reportMetadata": {
        "name": "MDU Opportunities by State",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "SUMMARY",
        "detailColumns": ["OPPORTUNITY_NAME", "STAGE_NAME", "Opportunity.Units__c", "Opportunity.Property_City__c"],
        "groupingsDown": [
            {"name": "Opportunity.Property_State__c", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["RowCount", "s!Opportunity.Units__c"],
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

# Report 4: Units by Stage (for donut/bar chart)
r4 = create_report("Units by Stage", {
    "reportMetadata": {
        "name": "MDU Units by Stage",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "SUMMARY",
        "detailColumns": ["OPPORTUNITY_NAME", "Opportunity.Units__c"],
        "groupingsDown": [
            {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["s!Opportunity.Units__c"],
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

# Report 5: Stage by Owner matrix
r5 = create_report("Stage x Owner Matrix", {
    "reportMetadata": {
        "name": "MDU Stage by Owner",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "MATRIX",
        "detailColumns": ["Opportunity.Units__c"],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "groupingsAcross": [
            {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["RowCount"],
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

# Report 6: SiteTracker Coverage
r6 = create_report("SiteTracker Coverage", {
    "reportMetadata": {
        "name": "MDU SiteTracker Coverage",
        "reportType": {"type": "Opportunity"},
        "reportFormat": "SUMMARY",
        "detailColumns": ["OPPORTUNITY_NAME", "STAGE_NAME", "Opportunity.SiteTracker_Project_ID__c"],
        "groupingsDown": [
            {"name": "Opportunity.In_SiteTracker__c", "sortOrder": "Asc", "dateGranularity": "NONE"}
        ],
        "aggregates": ["RowCount"],
        "reportFilters": [
            {"column": "RECORDTYPE", "operator": "equals", "value": "MDU"}
        ],
        "standardDateFilter": {"durationValue": "CUSTOM", "column": "CLOSE_DATE"},
        "folderId": folder_id
    }
})

report_ids = {
    'by_stage': r1, 'by_owner': r2, 'by_state': r3,
    'units_stage': r4, 'stage_owner': r5, 'st_coverage': r6,
    'folder_id': folder_id, 'dash_folder_id': dash_folder_id
}
print(f'\n{json.dumps(report_ids, indent=2)}')

with open('C:/Users/cass/Work_Projects/SalesForce/report_ids.json', 'w') as f:
    json.dump(report_ids, f, indent=2)
