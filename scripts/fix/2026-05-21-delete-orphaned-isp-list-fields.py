"""
Delete the orphaned, FLS-less, empty _List__c ISP fields (created 2026-04-14, never
used, superseded by *_ISPs__c). Verified: 0 dependencies, 0 populated rows.
Recoverable from SF deleted-fields bin ~15 days.
"""
import io, json, base64, zipfile, time, requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])
hdr = {"Authorization": f"Bearer {sf.session_id}"}

destructive = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.Prospective_ISP_List__c</members>
        <members>Opportunity.Confirmed_ISP_List__c</members>
        <name>CustomField</name>
    </types>
    <version>59.0</version>
</Package>"""
pkg = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata"><version>59.0</version></Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr("destructiveChanges.xml", destructive)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f"{sf.base_url}metadata/deployRequest"
deploy_body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True,
                                 "rollbackOnError": True, "singlePackage": True}}
boundary = "----B"
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="json"\r\n'
        f'Content-Type: application/json\r\n\r\n{json.dumps(deploy_body)}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="d.zip"\r\n'
        f'Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n'
        f'{zip_b64}\r\n--{boundary}--')
resp = requests.post(deploy_url, headers={"Authorization": f"Bearer {sf.session_id}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"}, data=body)
print(f"delete submit: {resp.status_code}")
did = resp.json().get("id")
for _ in range(20):
    time.sleep(3)
    dr = requests.get(f"{deploy_url}/{did}?includeDetails=true", headers=hdr).json().get("deployResult", {})
    st = dr.get("status", "?")
    print(f"  {st}")
    if st in ("Succeeded", "Failed", "Canceled"):
        ok = dr.get("details", {}).get("componentSuccesses", [])
        if isinstance(ok, dict):
            ok = [ok]
        for s in ok:
            if "ISP" in str(s.get("fullName")):
                print(f"    {s.get('fullName')}: deleted={s.get('deleted')}")
        fails = dr.get("details", {}).get("componentFailures", [])
        if fails:
            print("  FAILURES:", fails)
        break

# verify gone
sf2 = Salesforce(username=_SF["username"], password=_SF["password"],
                 security_token=_SF["token"])
desc = sf2.Opportunity.describe()
isp = sorted(f["name"] for f in desc["fields"]
             if (f["label"] or "") in ("Confirmed ISP", "Prospective ISP"))
print(f"\nRemaining ISP-labelled fields (API): {isp}")
