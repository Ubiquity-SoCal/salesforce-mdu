"""
Per Taylor (2026-05-22 call): a PAL/ROE is "signed/completed" only when
Status = Completed (or Cancelled, if a signed contract exists) AND it has an
agreement date. Update Is_Signed_PAL__c so the Opportunity signed-PAL rollup
(PAL-priority dedup) reflects that, instead of "any PAL with a Signed Date".

Old: ISPICKVAL(Agreement_Type__c,"PAL") && NOT(ISBLANK(Signed_Date__c))
New: + && (Status = Completed OR Cancelled)

Updates the existing field formula (overwrite). Read-only formula, no data touched.
"""
import requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
sf = Salesforce(username=USER, password=PW, security_token=TOK)

AGR = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label><pluralLabel>Agreements</pluralLabel>
    <nameField><label>Agreement Number</label><displayFormat>AGR-{0000}</displayFormat><type>AutoNumber</type></nameField>
    <sharingModel>ControlledByParent</sharingModel><deploymentStatus>Deployed</deploymentStatus>
    <enableReports>true</enableReports>
    <fields>
        <fullName>Is_Signed_PAL__c</fullName>
        <label>Is Signed PAL</label>
        <type>Checkbox</type>
        <formula>ISPICKVAL(Agreement_Type__c, "PAL") &amp;&amp; NOT(ISBLANK(Signed_Date__c)) &amp;&amp; (ISPICKVAL(Status__c, "Completed") || ISPICKVAL(Status__c, "Cancelled"))</formula>
        <description>Signed PALs report: true when a PAL is Completed/Cancelled AND has an agreement (signed) date. Drives the Opportunity signed-PAL rollup / PAL-priority dedup. Updated 2026-05-22 per Taylor: status gate added.</description>
    </fields>
</CustomObject>"""

pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata"><types><members>Agreement__c</members><name>CustomObject</name></types><version>{V}</version></Package>'
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr("objects/Agreement__c.object", AGR)

url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
b64 = base64.b64encode(buf.getvalue()).decode()
body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}: {r.text[:400]}"); raise SystemExit(1)
did = r.json()["id"]
for i in range(40):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st == "Succeeded":
        print("Is_Signed_PAL__c formula updated (status gate added).")
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
