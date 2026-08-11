from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

report_folder_id = '00lWR000005rBnFYAU'
dash_folder_id = '00lWR000005rBorYAE'

# Step 1: Get report developer names (Metadata API needs these, not IDs)
print("Step 1: Getting report developer names...")
resp = sf.query("SELECT Id, DeveloperName, Name, FolderName FROM Report WHERE FolderName = 'MDU Sales Reports' ORDER BY Name")
reports_info = {}
for r in resp['records']:
    print(f"  {r['DeveloperName']} ({r['Name']}) - {r['Id']}")
    reports_info[r['DeveloperName']] = r['Id']

# Map our reports
# We need the developer names - let's query by ID
report_ids = {
    'by_stage': '00OWR00000GeN372AF',
    'by_owner': '00OWR00000GeK5G2AV',
    'by_state': '00OWR00000GeN4j2AF',
    'units_stage': '00OWR00000GeN6L2AV',
    'stage_owner': '00OWR00000GeN7x2AF',
    'st_coverage': '00OWR00000GeN9Z2AV',
}
id_list = "','".join(report_ids.values())
resp = sf.query(f"SELECT Id, DeveloperName FROM Report WHERE Id IN ('{id_list}')")
id_to_devname = {}
for r in resp['records']:
    id_to_devname[r['Id'][:15]] = r['DeveloperName']
    print(f"  {r['Id']} -> {r['DeveloperName']}")

# Map back
dev_names = {}
for key, rid in report_ids.items():
    dev_names[key] = id_to_devname.get(rid[:15], rid)

# Need folder dev name for full report reference
folder_query = sf.query("SELECT Id, DeveloperName FROM Folder WHERE Id = '00lWR000005rBnFYAU'")
folder_devname = folder_query['records'][0]['DeveloperName'] if folder_query['records'] else 'MDU_Sales_Reports'
print(f"Report folder dev name: {folder_devname}")

# Prefix with folder name
for key in dev_names:
    dev_names[key] = f"{folder_devname}/{dev_names[key]}"

print(f"\nFull report refs: {json.dumps(dev_names, indent=2)}")

# Step 2: Deploy Dashboard via Metadata API
print("\nStep 2: Deploying MDU Sales Dashboard...")

# Dashboard filter needs column from EACH component report
# Each component needs a dashboardFilterColumns entry mapping filter index -> report column
def bar_component(header, report, use_units=False, grouping='BucketField_STAGE_NAME'):
    if use_units:
        summary = """            <chartSummary>
                <aggregate>Sum</aggregate>
                <axisBinding>y</axisBinding>
                <column>Opportunity.Units__c</column>
            </chartSummary>"""
    else:
        summary = """            <chartSummary>
                <axisBinding>y</axisBinding>
                <column>RowCount</column>
            </chartSummary>"""
    return f"""        <components>
            <autoselectColumnsFromReport>false</autoselectColumnsFromReport>
            <chartAxisRange>Auto</chartAxisRange>
{summary}
            <componentType>Bar</componentType>
            <dashboardFilterColumns>
                <column>FULL_NAME</column>
            </dashboardFilterColumns>
            <displayUnits>Auto</displayUnits>
            <drillEnabled>false</drillEnabled>
            <drillToDetailEnabled>false</drillToDetailEnabled>
            <enableHover>true</enableHover>
            <expandOthers>false</expandOthers>
            <groupingColumn>{grouping}</groupingColumn>
            <header>{header}</header>
            <legendPosition>Bottom</legendPosition>
            <report>{report}</report>
            <showPercentage>false</showPercentage>
            <showValues>true</showValues>
            <sortBy>RowLabelAscending</sortBy>
            <useReportChart>false</useReportChart>
        </components>"""

def donut_component(header, report, use_units=False, grouping='BucketField_STAGE_NAME'):
    if use_units:
        summary = """            <chartSummary>
                <aggregate>Sum</aggregate>
                <axisBinding>y</axisBinding>
                <column>Opportunity.Units__c</column>
            </chartSummary>"""
    else:
        summary = """            <chartSummary>
                <axisBinding>y</axisBinding>
                <column>RowCount</column>
            </chartSummary>"""
    return f"""        <components>
            <autoselectColumnsFromReport>false</autoselectColumnsFromReport>
            <chartAxisRange>Auto</chartAxisRange>
{summary}
            <componentType>Donut</componentType>
            <dashboardFilterColumns>
                <column>FULL_NAME</column>
            </dashboardFilterColumns>
            <displayUnits>Auto</displayUnits>
            <drillEnabled>false</drillEnabled>
            <drillToDetailEnabled>false</drillToDetailEnabled>
            <enableHover>true</enableHover>
            <expandOthers>false</expandOthers>
            <groupingColumn>{grouping}</groupingColumn>
            <header>{header}</header>
            <legendPosition>Bottom</legendPosition>
            <report>{report}</report>
            <showPercentage>true</showPercentage>
            <showValues>true</showValues>
            <sortBy>RowLabelAscending</sortBy>
            <useReportChart>false</useReportChart>
        </components>"""

# Layout:
# Left column: Record Counts (by Stage bar, by Owner bar, by State bar)
# Middle column: Unit Counts (Units by Stage donut, Units by Owner bar, Units by State bar)
# Right column: SiteTracker Coverage donut, Stage x Owner matrix bar

dash_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Dashboard xmlns="http://soap.sforce.com/2006/04/metadata">
    <backgroundEndColor>#FFFFFF</backgroundEndColor>
    <backgroundFadeDirection>Diagonal</backgroundFadeDirection>
    <backgroundStartColor>#FFFFFF</backgroundStartColor>
    <dashboardFilters>
        <dashboardFilterOptions>
            <operator>equals</operator>
            <values></values>
        </dashboardFilterOptions>
        <name>Opportunity Owner</name>
    </dashboardFilters>
    <dashboardType>SpecifiedUser</dashboardType>
    <isGridLayout>false</isGridLayout>
    <leftSection>
        <columnSize>Medium</columnSize>
{bar_component("Record Count by Stage", dev_names['by_stage'], use_units=False, grouping='STAGE_NAME')}
{bar_component("Record Count by Owner", dev_names['by_owner'], use_units=False, grouping='FULL_NAME')}
{bar_component("Record Count by State", dev_names['by_state'], use_units=False, grouping='Opportunity.Property_State__c')}
    </leftSection>
    <middleSection>
        <columnSize>Medium</columnSize>
{donut_component("Units by Stage", dev_names['units_stage'], use_units=True, grouping='STAGE_NAME')}
{bar_component("Units by Owner", dev_names['by_owner'], use_units=True, grouping='FULL_NAME')}
{bar_component("Units by State", dev_names['by_state'], use_units=True, grouping='Opportunity.Property_State__c')}
    </middleSection>
    <rightSection>
        <columnSize>Medium</columnSize>
{donut_component("SiteTracker Coverage", dev_names['st_coverage'], use_units=False, grouping='Opportunity.In_SiteTracker__c')}
{bar_component("Stage by Owner", dev_names['stage_owner'], use_units=False, grouping='FULL_NAME')}
    </rightSection>
    <runningUser>cass1@ubiquitygp.com</runningUser>
    <textColor>#000000</textColor>
    <title>MDU Sales Dashboard</title>
    <titleColor>#000000</titleColor>
    <titleSize>12</titleSize>
</Dashboard>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales_Dashboards/MDU_Sales_Dashboard</members>
        <name>Dashboard</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('dashboards/MDU_Sales_Dashboards/MDU_Sales_Dashboard.dashboard', dash_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f'{sf.base_url}metadata/deployRequest'
deploy_body = {'deployOptions': {'checkOnly': False, 'ignoreWarnings': True, 'rollbackOnError': True, 'singlePackage': True}}
boundary = '----DeployBoundary'
body_str = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
    f'{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
    f'Content-Type: application/zip\r\n'
    f'Content-Transfer-Encoding: base64\r\n\r\n'
    f'{zip_b64}\r\n'
    f'--{boundary}--'
)

resp = requests.post(deploy_url, headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}, data=body_str)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
        time.sleep(3)
        check = requests.get(f'{deploy_url}/{deploy_id}?includeDetails=true', headers={'Authorization': f'Bearer {sf.session_id}'})
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict): failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            elif status == 'Succeeded':
                dash_query = sf.query("SELECT Id FROM Dashboard WHERE DeveloperName = 'MDU_Sales_Dashboard' LIMIT 1")
                if dash_query['records']:
                    dash_id = dash_query['records'][0]['Id']
                    print(f'\nDashboard ID: {dash_id}')
                    print(f'URL: https://{sf.sf_instance}/lightning/r/Dashboard/{dash_id}/view')
            break
else:
    print(resp.text[:500])
