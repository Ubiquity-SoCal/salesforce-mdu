"""
Fix IronClad__c field-level security for System Administrator profile.
Grants read/edit access to all 60 custom fields + object CRUD.
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


USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# All 60 custom fields on IronClad__c
fields = [
    "IronClad_Id__c", "Record_Name__c", "Record_Type_IC__c", "Agree_Name__c",
    "Record_Id_IC__c", "Contract_Status__c", "Stage_IC__c",
    "Agreement_Date__c", "Effective_Date__c", "Expiration_Date__c", "Executed_Date__c",
    "Workflow_Created_Date__c", "Workflow_Completed_Date__c", "Last_Activity_Date_IC__c",
    "Last_Activity_Action__c", "Anniversary_Date__c", "Renewal_Opt_Out_Date__c",
    "Property_Name__c", "Property_Address__c", "Property_City__c", "Property_State__c",
    "Property_Group__c", "Property_Type__c", "MDU_or_BUS__c",
    "Number_of_Residential_Units__c", "Property_Postcode__c", "Property_Location__c",
    "Number_of_Units_ROE__c", "Parcel_Number__c",
    "Counterparty_Name__c", "Counterparty_Contact_Name__c", "Counterparty_Contact_Email__c",
    "Counterparty_Signer_Name__c", "Counterparty_Signer_Email__c", "Counterparty_Signer_Title__c",
    "Counterparty_Telephone__c", "Counterparty_Entity_Type__c", "Counterparty_Address__c",
    "Initial_Term_Length__c", "Renewal_Type__c", "Renewal_Term_Length__c",
    "Renewal_Opt_Out_Period__c", "Termination_Notice_Period__c",
    "Door_Fee__c", "Maximum_Door_Fee__c", "Contract_Value__c",
    "Revenue_Share_Pct__c", "Total_Build_Cost__c",
    "Execution_Method__c", "ISP__c", "Brownfield_Greenfield__c", "Build_Type__c",
    "Addendum_Signed__c",
    "Contract_Owner_IC__c", "External_Affair_Assignee__c", "Internal_Party__c",
    "Requestor__c", "EA_Market_Team_Leader__c",
    "Notes_IC__c", "Additional_Notes__c", "Attachment_Filenames__c",
    "Repository_Link__c", "Workflow_Link__c", "Last_Synced__c",
]

# Build field permissions XML
field_perms = ""
for f in fields:
    field_perms += f"""
        <fieldPermissions>
            <editable>true</editable>
            <field>IronClad__c.{f}</field>
            <readable>true</readable>
        </fieldPermissions>"""

profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <objectPermissions>
        <allowCreate>true</allowCreate>
        <allowDelete>true</allowDelete>
        <allowEdit>true</allowEdit>
        <allowRead>true</allowRead>
        <modifyAllRecords>true</modifyAllRecords>
        <object>IronClad__c</object>
        <viewAllRecords>true</viewAllRecords>
    </objectPermissions>
    <tabVisibilities>
        <tab>IronClad__c</tab>
        <visibility>DefaultOn</visibility>
    </tabVisibilities>
    {field_perms}
</Profile>"""

package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Admin</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""

print("Deploying field-level security for System Administrator...")

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", package_xml)
    zf.writestr("profiles/Admin.profile", profile_xml)

zip_bytes = buf.getvalue()
zip_b64 = base64.b64encode(zip_bytes).decode()

deploy_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/metadata/deployRequest"
deploy_body = {
    "deployOptions": {
        "checkOnly": False,
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
    exit(1)

deploy_id = resp.json().get("id")
print(f"Deploy ID: {deploy_id}")

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
        print("\nPermissions deployed! All 60 fields now visible to System Administrator.")
        break
    if status in ("Failed", "Canceled", "SucceededPartial"):
        details = result.get("deployResult", {}).get("details", {})
        failures = details.get("componentFailures", [])
        if isinstance(failures, dict):
            failures = [failures]
        for f in failures:
            print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        break

# Verify
print("\nVerifying field access...")
sf2 = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
desc = sf2.IronClad__c.describe()
custom_fields = [f for f in desc["fields"] if f["name"].endswith("__c")]
print(f"Custom fields now visible: {len(custom_fields)}")
for f in custom_fields[:10]:
    print(f"  {f['name']}")
if len(custom_fields) > 10:
    print(f"  ... and {len(custom_fields) - 10} more")
