"""
Signed PALs report support: add Sync_Source__c formula on Agreement__c.
Formula: IF(ISBLANK(IronClad_ID__c), "Manual/Import", "IronClad-synced")
Purpose: at-a-glance flag for whether an Agreement's Status is IronClad-synced
(live) vs imported/manual (static). Doubles as a cleanup filter for the ~102
PALs that say "Completed" only because that was the import default.

Read-only formula field. Additive, reversible, touches no data.
"""
import requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)


def metadata_deploy(zip_bytes, label):
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
        print(f"[{label}] deploy POST failed: {resp.status_code} - {resp.text[:400]}")
        return False
    deploy_id = resp.json().get("id")
    for i in range(30):
        time.sleep(3)
        check = requests.get(f"{deploy_url}/{deploy_id}?includeDetails=true",
                             headers={"Authorization": f"Bearer {sf.session_id}"})
        result = check.json()
        status = result.get("deployResult", {}).get("status", "unknown")
        print(f"  [{label}] poll {i+1}: {status}")
        if status == "Succeeded":
            return True
        if status in ("Failed", "Canceled", "SucceededPartial"):
            for f in (result.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    return False


# idempotency check
desc = sf.Agreement__c.describe()
if "Sync_Source__c" in [f["name"] for f in desc["fields"]]:
    print("Sync_Source__c already exists; skipping field deploy.")
else:
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
    <fields>
        <fullName>Sync_Source__c</fullName>
        <label>Sync Source</label>
        <type>Text</type>
        <formula>IF(ISBLANK(IronClad_ID__c), "Manual/Import", "IronClad-synced")</formula>
        <formulaTreatBlanksAs>BlankAsBlank</formulaTreatBlanksAs>
        <description>Signed PALs report: flags whether Status is IronClad-synced (live) or imported/manual (static). Derived from IronClad_ID__c presence.</description>
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
    if not metadata_deploy(buf.getvalue(), "field"):
        print("Field deploy failed."); raise SystemExit(1)

    # FLS for Admin (formula field -> readable only, never editable)
    profile_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions>
        <editable>false</editable>
        <field>Agreement__c.Sync_Source__c</field>
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
    metadata_deploy(buf2.getvalue(), "fls-admin")

# verify formula evaluates correctly against real data
print("\nVerification (Sync_Source__c vs IronClad_ID__c on signed PALs):")
sf2 = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
rows = sf2.query_all(
    "SELECT Sync_Source__c v, COUNT(Id) c FROM Agreement__c "
    "WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null GROUP BY Sync_Source__c"
)["records"]
for r in rows:
    print(f"   {str(r['v']):<18} {r['c']}")
# sanity: a few sample rows
for r in sf2.query("SELECT Name, IronClad_ID__c, Sync_Source__c FROM Agreement__c "
                   "WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null LIMIT 6")["records"]:
    print(f"   {r['Name']:<10} IC_ID={str(r['IronClad_ID__c']):<24} -> {r['Sync_Source__c']}")
