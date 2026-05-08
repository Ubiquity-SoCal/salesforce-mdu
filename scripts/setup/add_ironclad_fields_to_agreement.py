"""
Add IronClad Stage and Contract Status fields to Agreement__c,
then populate from matched IronClad__c records.
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


def metadata_deploy(zip_bytes):
    deploy_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/metadata/deployRequest"
    zip_b64 = base64.b64encode(zip_bytes).decode()
    deploy_body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
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
    headers = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
    resp = requests.post(deploy_url, headers=headers, data=body_str)
    if resp.status_code not in (200, 201):
        print(f"Deploy failed: {resp.status_code} - {resp.text[:500]}")
        return False
    deploy_id = resp.json().get("id")
    for i in range(30):
        time.sleep(3)
        check = requests.get(f"{deploy_url}/{deploy_id}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"})
        result = check.json()
        status = result.get("deployResult", {}).get("status", "unknown")
        print(f"  Poll {i+1}: {status}")
        if status == "Succeeded":
            return True
        if status in ("Failed", "Canceled", "SucceededPartial"):
            for f in (result.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    return False


# Step 1: Check if fields already exist
desc = sf.Agreement__c.describe()
existing = [f["name"] for f in desc["fields"]]

fields_xml = ""
new_fields = []

if "IronClad_Stage__c" not in existing:
    fields_xml += """
    <fields>
        <fullName>IronClad_Stage__c</fullName>
        <label>IronClad Stage</label>
        <type>Text</type>
        <length>50</length>
        <description>Workflow stage from IronClad (completed, sign, review, etc.)</description>
    </fields>"""
    new_fields.append("IronClad_Stage__c")
else:
    print("IronClad_Stage__c already exists")

if "IronClad_Contract_Status__c" not in existing:
    fields_xml += """
    <fields>
        <fullName>IronClad_Contract_Status__c</fullName>
        <label>IronClad Contract Status</label>
        <type>Text</type>
        <length>50</length>
        <description>Contract status from IronClad (active, evergreen, expiring, etc.)</description>
    </fields>"""
    new_fields.append("IronClad_Contract_Status__c")
else:
    print("IronClad_Contract_Status__c already exists")

if fields_xml:
    print(f"Deploying {len(new_fields)} new fields on Agreement__c...")

    obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label>
    <pluralLabel>Agreements</pluralLabel>
    <nameField>
        <label>Agreement Number</label>
        <displayFormat>AGR-{{0000}}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ControlledByParent</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    {fields_xml}
</CustomObject>"""

    pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Agreement__c</members><name>CustomObject</name></types>
    <version>{API_VERSION}</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg_xml)
        zf.writestr("objects/Agreement__c.object", obj_xml)

    if not metadata_deploy(buf.getvalue()):
        print("Field deployment failed!")
        exit(1)

    # Grant FLS
    field_perms = ""
    for f in new_fields:
        field_perms += f"""
        <fieldPermissions>
            <editable>true</editable>
            <field>Agreement__c.{f}</field>
            <readable>true</readable>
        </fieldPermissions>"""

    profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    {field_perms}
</Profile>"""

    pkg2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Admin</members><name>Profile</name></types>
    <version>{API_VERSION}</version>
</Package>"""

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg2)
        zf.writestr("profiles/Admin.profile", profile_xml)

    print("Granting field access...")
    metadata_deploy(buf2.getvalue())

# Step 2: Populate from matched IronClad records
print("\nPopulating IronClad Stage and Contract Status on matched Agreements...")

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# Get all matched IronClad records with their Agreement link
ic_matched = sf.query_all(
    "SELECT Id, IronClad_Id__c, Agreement__c, Stage_IC__c, Contract_Status__c "
    "FROM IronClad__c WHERE Agreement__c != null"
)["records"]

print(f"Matched IronClad records to update from: {len(ic_matched)}")

success = 0
errors = 0

for ic in ic_matched:
    agr_id = ic["Agreement__c"]
    stage = ic.get("Stage_IC__c") or ""
    status = ic.get("Contract_Status__c") or ""

    try:
        sf.Agreement__c.update(agr_id, {
            "IronClad_Stage__c": stage,
            "IronClad_Contract_Status__c": status,
        })
        success += 1
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"  ERROR {ic['IronClad_Id__c']}: {str(e)[:200]}")

print(f"\nUpdated {success} Agreement records, {errors} errors")
print("\nDone! Add 'IronClad Stage' and 'IronClad Contract Status' to your Agreement list views.")
