"""
Enable 'Allow Reports' on Agreement__c so it becomes reportable.
Since Agreement__c is master-detail to Opportunity, this should auto-create the
standard "Opportunities with Agreements" report type. Additive, no data touched.
Then re-check the analytics report-type list to confirm.
"""
import requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
sf = Salesforce(username=USER, password=PW, security_token=TOK)


def metadata_deploy(zip_bytes, label):
    url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
    b64 = base64.b64encode(zip_bytes).decode()
    body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
    bnd = "----DeployBoundary"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n"
               f"{json.dumps(body)}\r\n--{bnd}\r\n"
               f"Content-Disposition: form-data; name=\"file\"; filename=\"deploy.zip\"\r\n"
               f"Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
    h = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}
    r = requests.post(url, headers=h, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json().get("id")
    for i in range(30):
        time.sleep(3)
        res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
        st = res.get("deployResult", {}).get("status", "?")
        print(f"  [{label}] poll {i+1}: {st}")
        if st == "Succeeded": return True
        if st in ("Failed", "Canceled", "SucceededPartial"):
            for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
                if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    return False


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
    <enableReports>true</enableReports>
</CustomObject>"""
pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Agreement__c</members><name>CustomObject</name></types>
    <version>{V}</version>
</Package>"""
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr("objects/Agreement__c.object", obj_xml)
ok = metadata_deploy(buf.getvalue(), "enable-reports")
print("Deploy:", "OK" if ok else "FAILED")

# re-check report types
print("\nRe-checking report types for Agreement__c ...")
sf2 = Salesforce(username=USER, password=PW, security_token=TOK)
data = requests.get(sf2.base_url + "analytics/reportTypes",
                    headers={"Authorization": f"Bearer {sf2.session_id}"}).json()
hits = [(rt.get("type"), rt.get("label")) for cat in data for rt in cat.get("reportTypes", [])
        if "Agreement__c" in (rt.get("type") or "") and "Lease" not in (rt.get("type") or "")
        or (rt.get("label") or "").lower() in ("agreements", "opportunities with agreements")]
for t, l in hits:
    print(f"   {t!r:<50} {l!r}")
if not hits:
    print("   still none -> will need a custom report type")
