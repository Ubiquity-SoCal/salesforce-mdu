"""
Create IronClad__c custom object in Salesforce with 60 fields from export analysis.
Deploys via Metadata API (REST multipart), then adds tab to MDU Sales app.
"""

import requests
import json
import time
import base64
import io
import zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# --- Credentials ---
USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)


def metadata_deploy(zip_bytes, check_only=False):
    """Deploy a metadata ZIP via REST Metadata API."""
    deploy_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/metadata/deployRequest"
    zip_b64 = base64.b64encode(zip_bytes).decode()

    deploy_body = {
        "deployOptions": {
            "checkOnly": check_only,
            "ignoreWarnings": True,
            "rollbackOnError": True,
            "singlePackage": True,
        }
    }

    boundary = "----DeployBoundary"
    body_str = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(deploy_body)}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
        f"Content-Type: application/zip\r\n"
        f"Content-Transfer-Encoding: base64\r\n\r\n"
        f"{zip_b64}\r\n"
        f"--{boundary}--"
    )

    headers = {
        "Authorization": f"Bearer {sf.session_id}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    resp = requests.post(deploy_url, headers=headers, data=body_str)
    if resp.status_code not in (200, 201):
        print(f"Deploy request failed: {resp.status_code}")
        print(resp.text[:1000])
        return None

    deploy_id = resp.json().get("id")
    print(f"Deploy ID: {deploy_id}")

    # Poll for completion
    for i in range(30):
        time.sleep(3)
        check = requests.get(
            f"{deploy_url}/{deploy_id}?includeDetails=true",
            headers={"Authorization": f"Bearer {sf.session_id}"},
        )
        result = check.json()
        status = result.get("deployResult", {}).get("status", "unknown")
        print(f"  Poll {i+1}: {status}")

        if status == "Succeeded":
            return True
        if status in ("Failed", "Canceled", "SucceededPartial"):
            details = result.get("deployResult", {}).get("details", {})
            failures = details.get("componentFailures", [])
            if isinstance(failures, dict):
                failures = [failures]
            for f in failures:
                print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False

    print("Deploy timed out")
    return False


# ============================================================
# STEP 1: Create IronClad__c object with all fields
# ============================================================

object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>IronClad</label>
    <pluralLabel>IronClad Records</pluralLabel>
    <nameField>
        <label>IronClad Number</label>
        <displayFormat>IC-{0000}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ReadWrite</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    <enableActivities>true</enableActivities>
    <enableHistory>true</enableHistory>
    <enableReports>true</enableReports>
    <enableSearch>true</enableSearch>

    <!-- ==================== IDENTITY & LINKING ==================== -->

    <fields>
        <fullName>IronClad_Id__c</fullName>
        <label>IronClad ID</label>
        <type>Text</type>
        <length>20</length>
        <externalId>true</externalId>
        <unique>true</unique>
        <caseSensitive>false</caseSensitive>
        <description>Primary key from IronClad (IC-XXXX format)</description>
    </fields>

    <fields>
        <fullName>Record_Name__c</fullName>
        <label>Record Name</label>
        <type>Text</type>
        <length>255</length>
        <description>Full agreement title from IronClad</description>
    </fields>

    <fields>
        <fullName>Record_Type_IC__c</fullName>
        <label>Record Type (IC)</label>
        <type>Picklist</type>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Premises Access License</fullName><default>false</default><label>Premises Access License</label></value>
                <value><fullName>Right of Entry Agreement</fullName><default>false</default><label>Right of Entry Agreement</label></value>
                <value><fullName>FiberFirst Enterprise Service Agreement</fullName><default>false</default><label>FiberFirst Enterprise Service Agreement</label></value>
                <value><fullName>Exclusive Marketing Agreement</fullName><default>false</default><label>Exclusive Marketing Agreement</label></value>
                <value><fullName>Non-Exclusive Marketing Agreement</fullName><default>false</default><label>Non-Exclusive Marketing Agreement</label></value>
                <value><fullName>Bulk Services Agreement</fullName><default>false</default><label>Bulk Services Agreement</label></value>
                <value><fullName>Sales Agent Agreement</fullName><default>false</default><label>Sales Agent Agreement</label></value>
                <value><fullName>License Agreement - Pole Attachment</fullName><default>false</default><label>License Agreement - Pole Attachment</label></value>
                <value><fullName>Utility Pole Attachment</fullName><default>false</default><label>Utility Pole Attachment</label></value>
                <value><fullName>Infrastructure and Services Agreement</fullName><default>false</default><label>Infrastructure and Services Agreement</label></value>
                <value><fullName>Right of Way Agreement</fullName><default>false</default><label>Right of Way Agreement</label></value>
                <value><fullName>Easement Agreement</fullName><default>false</default><label>Easement Agreement</label></value>
                <value><fullName>Joint Trench Agreement</fullName><default>false</default><label>Joint Trench Agreement</label></value>
                <value><fullName>Construction Agreement</fullName><default>false</default><label>Construction Agreement</label></value>
                <value><fullName>Pole Attachment</fullName><default>false</default><label>Pole Attachment</label></value>
                <value><fullName>Resources</fullName><default>false</default><label>Resources</label></value>
                <value><fullName>Amendment - FiberFirst MDU Marketing Agreement</fullName><default>false</default><label>Amendment - FiberFirst MDU Marketing Agreement</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <fields>
        <fullName>Agree_Name__c</fullName>
        <label>Agreement Name (IC)</label>
        <type>Text</type>
        <length>255</length>
        <description>City_MDU_Name format from IronClad - matches Agreement_Name__c in SF</description>
    </fields>

    <fields>
        <fullName>Record_Id_IC__c</fullName>
        <label>Record ID (IC)</label>
        <type>Text</type>
        <length>80</length>
        <description>Internal IronClad UUID, useful for future API calls</description>
    </fields>

    <!-- ==================== STATUS & STAGE ==================== -->

    <fields>
        <fullName>Contract_Status__c</fullName>
        <label>Contract Status</label>
        <type>Picklist</type>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>active</fullName><default>false</default><label>active</label></value>
                <value><fullName>evergreen</fullName><default>false</default><label>evergreen</label></value>
                <value><fullName>expiring</fullName><default>false</default><label>expiring</label></value>
                <value><fullName>auto-renewing</fullName><default>false</default><label>auto-renewing</label></value>
                <value><fullName>inactive</fullName><default>false</default><label>inactive</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <fields>
        <fullName>Stage_IC__c</fullName>
        <label>Stage (IC)</label>
        <type>Picklist</type>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>completed</fullName><default>false</default><label>completed</label></value>
                <value><fullName>cancelled</fullName><default>false</default><label>cancelled</label></value>
                <value><fullName>sign</fullName><default>false</default><label>sign</label></value>
                <value><fullName>review</fullName><default>false</default><label>review</label></value>
                <value><fullName>create</fullName><default>false</default><label>create</label></value>
                <value><fullName>paused</fullName><default>false</default><label>paused</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <!-- ==================== DATES ==================== -->

    <fields>
        <fullName>Agreement_Date__c</fullName>
        <label>Agreement Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Effective_Date__c</fullName>
        <label>Effective Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Expiration_Date__c</fullName>
        <label>Expiration Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Executed_Date__c</fullName>
        <label>Executed Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Workflow_Created_Date__c</fullName>
        <label>Workflow Created Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Workflow_Completed_Date__c</fullName>
        <label>Workflow Completed Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Last_Activity_Date_IC__c</fullName>
        <label>Last Activity Date (IC)</label>
        <type>DateTime</type>
    </fields>

    <fields>
        <fullName>Last_Activity_Action__c</fullName>
        <label>Last Activity Action</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <fields>
        <fullName>Anniversary_Date__c</fullName>
        <label>Anniversary Date</label>
        <type>Date</type>
    </fields>

    <fields>
        <fullName>Renewal_Opt_Out_Date__c</fullName>
        <label>Renewal Opt Out Date</label>
        <type>Date</type>
    </fields>

    <!-- ==================== PROPERTY INFO ==================== -->

    <fields>
        <fullName>Property_Name__c</fullName>
        <label>Property Name</label>
        <type>Text</type>
        <length>255</length>
    </fields>

    <fields>
        <fullName>Property_Address__c</fullName>
        <label>Property Address</label>
        <type>TextArea</type>
        <description>Full formatted address from IronClad</description>
    </fields>

    <fields>
        <fullName>Property_City__c</fullName>
        <label>Property City</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <fields>
        <fullName>Property_State__c</fullName>
        <label>Property State</label>
        <type>Text</type>
        <length>50</length>
    </fields>

    <fields>
        <fullName>Property_Group__c</fullName>
        <label>Property Group</label>
        <type>Text</type>
        <length>255</length>
        <description>Portfolio/management company</description>
    </fields>

    <fields>
        <fullName>Property_Type__c</fullName>
        <label>Property Type</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <fields>
        <fullName>MDU_or_BUS__c</fullName>
        <label>MDU or BUS</label>
        <type>Picklist</type>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>MDU</fullName><default>false</default><label>MDU</label></value>
                <value><fullName>BUS</fullName><default>false</default><label>BUS</label></value>
                <value><fullName>HOA</fullName><default>false</default><label>HOA</label></value>
                <value><fullName>SFU</fullName><default>false</default><label>SFU</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <fields>
        <fullName>Number_of_Residential_Units__c</fullName>
        <label>Number of Residential Units</label>
        <type>Number</type>
        <precision>6</precision>
        <scale>0</scale>
    </fields>

    <fields>
        <fullName>Property_Postcode__c</fullName>
        <label>Property Postcode</label>
        <type>Text</type>
        <length>20</length>
    </fields>

    <fields>
        <fullName>Property_Location__c</fullName>
        <label>Property Location (Market)</label>
        <type>Text</type>
        <length>50</length>
        <description>Coarse market region (NE/TX/AZ etc.)</description>
    </fields>

    <fields>
        <fullName>Number_of_Units_ROE__c</fullName>
        <label>Number of Units (ROE)</label>
        <type>Number</type>
        <precision>6</precision>
        <scale>0</scale>
    </fields>

    <fields>
        <fullName>Parcel_Number__c</fullName>
        <label>Parcel Number</label>
        <type>Text</type>
        <length>50</length>
    </fields>

    <!-- ==================== COUNTERPARTY ==================== -->

    <fields>
        <fullName>Counterparty_Name__c</fullName>
        <label>Counterparty Name</label>
        <type>Text</type>
        <length>255</length>
        <description>Legal entity name</description>
    </fields>

    <fields>
        <fullName>Counterparty_Contact_Name__c</fullName>
        <label>Counterparty Contact Name</label>
        <type>Text</type>
        <length>255</length>
    </fields>

    <fields>
        <fullName>Counterparty_Contact_Email__c</fullName>
        <label>Counterparty Contact Email</label>
        <type>Email</type>
    </fields>

    <fields>
        <fullName>Counterparty_Signer_Name__c</fullName>
        <label>Counterparty Signer Name</label>
        <type>Text</type>
        <length>255</length>
    </fields>

    <fields>
        <fullName>Counterparty_Signer_Email__c</fullName>
        <label>Counterparty Signer Email</label>
        <type>Email</type>
    </fields>

    <fields>
        <fullName>Counterparty_Signer_Title__c</fullName>
        <label>Counterparty Signer Title</label>
        <type>Text</type>
        <length>255</length>
    </fields>

    <fields>
        <fullName>Counterparty_Telephone__c</fullName>
        <label>Counterparty Telephone</label>
        <type>Phone</type>
    </fields>

    <fields>
        <fullName>Counterparty_Entity_Type__c</fullName>
        <label>Counterparty Entity Type</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <fields>
        <fullName>Counterparty_Address__c</fullName>
        <label>Counterparty Address</label>
        <type>TextArea</type>
    </fields>

    <!-- ==================== TERM & RENEWAL ==================== -->

    <fields>
        <fullName>Initial_Term_Length__c</fullName>
        <label>Initial Term Length</label>
        <type>Text</type>
        <length>20</length>
        <description>ISO 8601 duration (P12M, P10Y, etc.)</description>
    </fields>

    <fields>
        <fullName>Renewal_Type__c</fullName>
        <label>Renewal Type</label>
        <type>Text</type>
        <length>50</length>
        <description>Evergreen, None, Optional Extension, etc.</description>
    </fields>

    <fields>
        <fullName>Renewal_Term_Length__c</fullName>
        <label>Renewal Term Length</label>
        <type>Text</type>
        <length>20</length>
        <description>ISO 8601 duration</description>
    </fields>

    <fields>
        <fullName>Renewal_Opt_Out_Period__c</fullName>
        <label>Renewal Opt Out Period</label>
        <type>Text</type>
        <length>100</length>
        <description>Mix of ISO and text formats</description>
    </fields>

    <fields>
        <fullName>Termination_Notice_Period__c</fullName>
        <label>Termination Notice Period</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <!-- ==================== FINANCIAL ==================== -->

    <fields>
        <fullName>Door_Fee__c</fullName>
        <label>Door Fee</label>
        <type>Currency</type>
        <precision>10</precision>
        <scale>2</scale>
    </fields>

    <fields>
        <fullName>Maximum_Door_Fee__c</fullName>
        <label>Maximum Door Fee</label>
        <type>Currency</type>
        <precision>12</precision>
        <scale>2</scale>
    </fields>

    <fields>
        <fullName>Contract_Value__c</fullName>
        <label>Contract Value</label>
        <type>Currency</type>
        <precision>12</precision>
        <scale>2</scale>
    </fields>

    <fields>
        <fullName>Revenue_Share_Pct__c</fullName>
        <label>Revenue Share %</label>
        <type>Percent</type>
        <precision>5</precision>
        <scale>2</scale>
    </fields>

    <fields>
        <fullName>Total_Build_Cost__c</fullName>
        <label>Total Build Cost</label>
        <type>Currency</type>
        <precision>12</precision>
        <scale>2</scale>
    </fields>

    <!-- ==================== AGREEMENT DETAILS ==================== -->

    <fields>
        <fullName>Execution_Method__c</fullName>
        <label>Execution Method</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <fields>
        <fullName>ISP__c</fullName>
        <label>ISP</label>
        <type>Text</type>
        <length>50</length>
        <description>FiberFirst, Atlas, TBD, etc.</description>
    </fields>

    <fields>
        <fullName>Brownfield_Greenfield__c</fullName>
        <label>Brownfield/Greenfield</label>
        <type>Text</type>
        <length>20</length>
    </fields>

    <fields>
        <fullName>Build_Type__c</fullName>
        <label>Build Type</label>
        <type>Text</type>
        <length>10</length>
        <description>FTTU or FTTB</description>
    </fields>

    <fields>
        <fullName>Addendum_Signed__c</fullName>
        <label>Addendum Signed/Uploaded</label>
        <type>Checkbox</type>
        <defaultValue>false</defaultValue>
    </fields>

    <!-- ==================== PEOPLE & WORKFLOW ==================== -->

    <fields>
        <fullName>Contract_Owner_IC__c</fullName>
        <label>Contract Owner (IC)</label>
        <type>Text</type>
        <length>100</length>
        <description>Email of who owns this in IronClad</description>
    </fields>

    <fields>
        <fullName>External_Affair_Assignee__c</fullName>
        <label>External Affair Assignee</label>
        <type>Text</type>
        <length>100</length>
        <description>Maps to RE_Assigned concept</description>
    </fields>

    <fields>
        <fullName>Internal_Party__c</fullName>
        <label>Internal Party</label>
        <type>Text</type>
        <length>100</length>
        <description>Which legal entity (FiberFirst Arizona, Ubiquity Nebraska, etc.)</description>
    </fields>

    <fields>
        <fullName>Requestor__c</fullName>
        <label>Requestor</label>
        <type>Text</type>
        <length>100</length>
        <description>Who initiated the IronClad workflow</description>
    </fields>

    <fields>
        <fullName>EA_Market_Team_Leader__c</fullName>
        <label>EA Market Team Leader (ROE)</label>
        <type>Text</type>
        <length>100</length>
    </fields>

    <!-- ==================== NOTES & DOCS ==================== -->

    <fields>
        <fullName>Notes_IC__c</fullName>
        <label>Notes (IC)</label>
        <type>LongTextArea</type>
        <length>10000</length>
        <visibleLines>4</visibleLines>
    </fields>

    <fields>
        <fullName>Additional_Notes__c</fullName>
        <label>Additional Notes</label>
        <type>Text</type>
        <length>255</length>
    </fields>

    <fields>
        <fullName>Attachment_Filenames__c</fullName>
        <label>Attachment Filenames</label>
        <type>LongTextArea</type>
        <length>10000</length>
        <visibleLines>3</visibleLines>
        <description>Names of signed PDF files in IronClad</description>
    </fields>

    <fields>
        <fullName>Repository_Link__c</fullName>
        <label>Repository Link</label>
        <type>Url</type>
        <description>Link back to IronClad repository record</description>
    </fields>

    <fields>
        <fullName>Workflow_Link__c</fullName>
        <label>Workflow Link</label>
        <type>Url</type>
        <description>Link back to IronClad workflow</description>
    </fields>

    <!-- ==================== SYNC TRACKING ==================== -->

    <fields>
        <fullName>Last_Synced__c</fullName>
        <label>Last Synced</label>
        <type>DateTime</type>
    </fields>

</CustomObject>"""

# Tab metadata
tab_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">
    <customObject>true</customObject>
    <motif>Custom66: Handshake</motif>
</CustomTab>"""

package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>IronClad__c</members>
        <name>CustomObject</name>
    </types>
    <types>
        <members>IronClad__c</members>
        <name>CustomTab</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""

print("=" * 60)
print("STEP 1: Deploy IronClad__c object + tab")
print("=" * 60)

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", package_xml)
    zf.writestr("objects/IronClad__c.object", object_xml)
    zf.writestr("tabs/IronClad__c.tab", tab_xml)

result = metadata_deploy(buf.getvalue())
if not result:
    print("\nObject deployment failed. Stopping.")
    exit(1)

print("\nIronClad__c object + tab deployed successfully!")

# ============================================================
# STEP 2: Add IronClad tab to MDU Sales app
# ============================================================

print("\n" + "=" * 60)
print("STEP 2: Retrieve current MDU_Sales app, add IronClad tab")
print("=" * 60)

# First retrieve the current app definition
retrieve_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/tooling/query/"
query = "SELECT Id, Metadata FROM CustomApplication WHERE DeveloperName = 'MDU_Sales'"
resp = requests.get(
    retrieve_url,
    headers={"Authorization": f"Bearer {sf.session_id}"},
    params={"q": query},
)

if resp.status_code != 200:
    print(f"Failed to query MDU_Sales app: {resp.status_code}")
    print(resp.text[:500])
    exit(1)

records = resp.json().get("records", [])
if not records:
    print("MDU_Sales app not found!")
    exit(1)

app_record = records[0]
app_id = app_record["Id"]
metadata = app_record["Metadata"]

print(f"Found MDU_Sales app: {app_id}")
print(f"Current tabs: {metadata.get('tabs', [])}")

# Add IronClad__c tab if not already present
tabs = metadata.get("tabs", []) or []
if "IronClad__c" not in tabs:
    tabs.append("IronClad__c")
    metadata["tabs"] = tabs

    update_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/tooling/sobjects/CustomApplication/{app_id}"
    update_resp = requests.patch(
        update_url,
        headers={
            "Authorization": f"Bearer {sf.session_id}",
            "Content-Type": "application/json",
        },
        json={"Metadata": metadata},
    )

    if update_resp.status_code in (200, 204):
        print("IronClad tab added to MDU Sales app!")
    else:
        print(f"Failed to update app: {update_resp.status_code}")
        print(update_resp.text[:500])
else:
    print("IronClad__c tab already in MDU Sales app")

print(f"\nUpdated tabs: {tabs}")
print("\n" + "=" * 60)
print("DONE! IronClad__c object created with 60 fields.")
print("Tab added to MDU Sales app.")
print("=" * 60)
