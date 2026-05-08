"""
Create list views for IronClad__c object.
"""

import requests
import json
import time
import base64
import io
import zipfile
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# Common display columns for all views
COLUMNS = """
        <columns>IronClad_Id__c</columns>
        <columns>Record_Name__c</columns>
        <columns>Record_Type_IC__c</columns>
        <columns>Contract_Status__c</columns>
        <columns>Property_Name__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>Counterparty_Name__c</columns>
        <columns>Agreement_Date__c</columns>
        <columns>Expiration_Date__c</columns>
        <columns>MDU_or_BUS__c</columns>"""

views = []

# 1. All Records
views.append(("All_Records", "All Records", """
    <listViews>
        <fullName>All_Records</fullName>
        <label>All Records</label>
        <filterScope>Everything</filterScope>
        {columns}
    </listViews>"""))

# 2. PAL (Premises Access License)
views.append(("PAL_Agreements", "PAL Agreements", """
    <listViews>
        <fullName>PAL_Agreements</fullName>
        <label>PAL Agreements</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Record_Type_IC__c</field>
            <operation>equals</operation>
            <value>Premises Access License</value>
        </filters>
        {columns}
    </listViews>"""))

# 3. ROE (Right of Entry)
views.append(("ROE_Agreements", "ROE Agreements", """
    <listViews>
        <fullName>ROE_Agreements</fullName>
        <label>ROE Agreements</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Record_Type_IC__c</field>
            <operation>equals</operation>
            <value>Right of Entry Agreement</value>
        </filters>
        {columns}
    </listViews>"""))

# 4. EMA (Marketing Agreements - both exclusive and non-exclusive)
views.append(("Marketing_Agreements", "Marketing Agreements (EMA)", """
    <listViews>
        <fullName>Marketing_Agreements</fullName>
        <label>Marketing Agreements (EMA)</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Record_Type_IC__c</field>
            <operation>contains</operation>
            <value>Marketing Agreement</value>
        </filters>
        {columns}
    </listViews>"""))

# 5. Enterprise Service Agreements (BUS)
views.append(("Enterprise_Service", "Enterprise Service Agreements", """
    <listViews>
        <fullName>Enterprise_Service</fullName>
        <label>Enterprise Service Agreements</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Record_Type_IC__c</field>
            <operation>equals</operation>
            <value>FiberFirst Enterprise Service Agreement</value>
        </filters>
        {columns}
    </listViews>"""))

# 6. Bulk Services
views.append(("Bulk_Services", "Bulk Services Agreements", """
    <listViews>
        <fullName>Bulk_Services</fullName>
        <label>Bulk Services Agreements</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Record_Type_IC__c</field>
            <operation>equals</operation>
            <value>Bulk Services Agreement</value>
        </filters>
        {columns}
    </listViews>"""))

# 7. Active Contracts
views.append(("Active_Contracts", "Active Contracts", """
    <listViews>
        <fullName>Active_Contracts</fullName>
        <label>Active Contracts</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Contract_Status__c</field>
            <operation>equals</operation>
            <value>active</value>
        </filters>
        {columns}
    </listViews>"""))

# 8. Expiring Contracts
views.append(("Expiring_Contracts", "Expiring Contracts", """
    <listViews>
        <fullName>Expiring_Contracts</fullName>
        <label>Expiring Contracts</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Contract_Status__c</field>
            <operation>equals</operation>
            <value>expiring</value>
        </filters>
        {columns}
    </listViews>"""))

# 9. MDU Only
views.append(("MDU_Records", "MDU Records", """
    <listViews>
        <fullName>MDU_Records</fullName>
        <label>MDU Records</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>MDU_or_BUS__c</field>
            <operation>equals</operation>
            <value>MDU</value>
        </filters>
        {columns}
    </listViews>"""))

# 10. BUS Only
views.append(("BUS_Records", "BUS Records", """
    <listViews>
        <fullName>BUS_Records</fullName>
        <label>BUS Records</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>MDU_or_BUS__c</field>
            <operation>equals</operation>
            <value>BUS</value>
        </filters>
        {columns}
    </listViews>"""))

# Build the object XML with all list views
list_views_xml = ""
members_xml = ""
for api_name, label, template in views:
    list_views_xml += template.format(columns=COLUMNS)
    members_xml += f"        <members>IronClad__c.{api_name}</members>\n"

object_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>IronClad</label>
    <pluralLabel>IronClad Records</pluralLabel>
    <nameField>
        <label>IronClad Number</label>
        <displayFormat>IC-{{0000}}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ReadWrite</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    {list_views_xml}
</CustomObject>"""

package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>IronClad__c</members>
        <name>CustomObject</name>
    </types>
    <types>
{members_xml}        <name>ListView</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""

print(f"Deploying {len(views)} list views for IronClad__c...")

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", package_xml)
    zf.writestr("objects/IronClad__c.object", object_xml)

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
        print("\nList views deployed!")
        for api_name, label, _ in views:
            print(f"  - {label}")
        break
    if status in ("Failed", "Canceled", "SucceededPartial"):
        details = result.get("deployResult", {}).get("details", {})
        failures = details.get("componentFailures", [])
        if isinstance(failures, dict):
            failures = [failures]
        for f in failures:
            print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        break

print("\nDone!")
