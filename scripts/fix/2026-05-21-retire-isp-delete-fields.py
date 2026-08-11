"""
Final stage: delete the legacy ISP text fields Prospective_ISP__c / Confirmed_ISP__c.
Run with 'check' (validation only) or 'delete' (real destructive deploy).
Fields go to SF's deleted-fields bin (recoverable ~15 days).
"""
import sys, io, json, base64, zipfile, time, requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


mode = sys.argv[1] if len(sys.argv) > 1 else "check"
assert mode in ("check", "delete"), "arg must be 'check' or 'delete'"
check_only = (mode == "check")

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)
print(f"Connected: {sf.sf_instance}  mode={mode}")

destructive = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.Prospective_ISP__c</members>
        <members>Opportunity.Confirmed_ISP__c</members>
        <name>CustomField</name>
    </types>
    <version>59.0</version>
</Package>"""
empty_pkg = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", empty_pkg)
    zf.writestr("destructiveChanges.xml", destructive)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f"{sf.base_url}metadata/deployRequest"
deploy_body = {"deployOptions": {"checkOnly": check_only, "ignoreWarnings": True,
                                 "rollbackOnError": True, "singlePackage": True}}
boundary = "----DeployBoundary"
body = (
    f'--{boundary}\r\nContent-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="d.zip"\r\n'
    f'Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n'
    f'{zip_b64}\r\n--{boundary}--'
)
resp = requests.post(deploy_url, headers={
    "Authorization": f"Bearer {sf.session_id}",
    "Content-Type": f"multipart/form-data; boundary={boundary}"}, data=body)
print(f"submit: {resp.status_code}")
if resp.status_code == 201:
    did = resp.json().get("id")
    for _ in range(30):
        time.sleep(3)
        chk = requests.get(f"{deploy_url}/{did}?includeDetails=true",
                           headers={"Authorization": f"Bearer {sf.session_id}"}).json()
        dr = chk.get("deployResult", {})
        status = dr.get("status", "?")
        print(f"  {status}")
        if status in ("Succeeded", "Failed", "Canceled", "SucceededPartial"):
            det = dr.get("details", {})
            fails = det.get("componentFailures", [])
            if isinstance(fails, dict):
                fails = [fails]
            if fails:
                print("  BLOCKERS:")
                for f in fails:
                    print(f"    {f.get('fullName')}: {f.get('problem')}")
            else:
                ok = det.get("componentSuccesses", [])
                if isinstance(ok, dict):
                    ok = [ok]
                print("  No blockers.", "Fields DELETED." if not check_only else "Safe to delete.")
                for s in ok:
                    if s.get("fullName") and "ISP" in str(s.get("fullName")):
                        print(f"    {s.get('fullName')}: deleted={s.get('deleted')}")
            break
else:
    print(resp.text[:500])
