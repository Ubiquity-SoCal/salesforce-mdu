"""
Add IronClad__c lookup on Agreement__c (same pattern as SiteTracker on Opportunity).
Then populate it from the existing matches.
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


# Step 1: Add IronClad__c lookup on Agreement__c
desc = sf.Agreement__c.describe()
existing = [f["name"] for f in desc["fields"]]

if "IronClad_Record__c" not in existing:
    print("Deploying IronClad lookup on Agreement__c...")

    obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label>
    <pluralLabel>Agreements</pluralLabel>
    <nameField>
        <label>Agreement Number</label>
        <displayFormat>AGR-{0000}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ControlledByParent</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    <fields>
        <fullName>IronClad_Record__c</fullName>
        <label>IronClad Record</label>
        <type>Lookup</type>
        <referenceTo>IronClad__c</referenceTo>
        <relationshipLabel>Agreements</relationshipLabel>
        <relationshipName>Agreements</relationshipName>
        <deleteConstraint>SetNull</deleteConstraint>
        <description>Link to the matched IronClad contract record</description>
    </fields>
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
        print("Failed!")
        exit(1)

    # Grant FLS
    print("Granting field access...")
    profile_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions>
        <editable>true</editable>
        <field>Agreement__c.IronClad_Record__c</field>
        <readable>true</readable>
    </fieldPermissions>
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
    metadata_deploy(buf2.getvalue())
else:
    print("IronClad_Record__c already exists on Agreement__c")

# Step 2: Populate the lookup from matched IronClad records
print("\nPopulating IronClad Record lookup on matched Agreements...")

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# Get all matched IronClad records (they have Agreement__c filled)
ic_matched = sf.query_all(
    "SELECT Id, IronClad_Id__c, Agreement__c "
    "FROM IronClad__c WHERE Agreement__c != null"
)["records"]

print(f"Matched records to link: {len(ic_matched)}")

success = 0
errors = 0

for ic in ic_matched:
    try:
        sf.Agreement__c.update(ic["Agreement__c"], {
            "IronClad_Record__c": ic["Id"],
        })
        success += 1
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"  ERROR {ic['IronClad_Id__c']}: {str(e)[:200]}")

print(f"\nLinked {success} Agreements to IronClad records, {errors} errors")
print("\nDone! 'IronClad Record' field now available on Agreement list views and record pages.")
print("Click the IronClad Record link from any Agreement to jump to the full IronClad details.")
