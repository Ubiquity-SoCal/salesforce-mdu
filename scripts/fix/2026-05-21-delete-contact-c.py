"""
Delete the empty, redundant custom Contact__c lookup on Opportunity (contacts are
tracked via the Opportunity_Contact__c junction; ContactId standard exists too).
Verified 0 populated. Run 'check' (validation only) or 'delete'.
"""
import sys, io, json, base64, zipfile, time, requests
from simple_salesforce import Salesforce

mode = sys.argv[1] if len(sys.argv) > 1 else "check"
check_only = (mode == "check")
sf = Salesforce(username="cass1@ubiquitygp.com", password="Hawaiian1984",
                security_token="IBSKT6CFUpSUJWxq1CMm0HkFC")
hdr = {"Authorization": f"Bearer {sf.session_id}"}

# safety: re-confirm empty
c = sf.query("SELECT COUNT(Id) c FROM Opportunity WHERE Contact__c != null")["records"][0]["c"]
print(f"Contact__c populated={c}")
assert c == 0, "Contact__c has data; stop."

destructive = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Opportunity.Contact__c</members><name>CustomField</name></types>
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
deploy_body = {"deployOptions": {"checkOnly": check_only, "ignoreWarnings": True,
                                 "rollbackOnError": True, "singlePackage": True}}
boundary = "----B"
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="json"\r\n'
        f'Content-Type: application/json\r\n\r\n{json.dumps(deploy_body)}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="d.zip"\r\n'
        f'Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n'
        f'{zip_b64}\r\n--{boundary}--')
resp = requests.post(deploy_url, headers={"Authorization": f"Bearer {sf.session_id}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"}, data=body)
print(f"{mode} submit: {resp.status_code}")
did = resp.json().get("id")
for _ in range(20):
    time.sleep(3)
    dr = requests.get(f"{deploy_url}/{did}?includeDetails=true", headers=hdr).json().get("deployResult", {})
    st = dr.get("status", "?")
    print(f"  {st}")
    if st in ("Succeeded", "Failed", "Canceled"):
        fails = dr.get("details", {}).get("componentFailures", [])
        if isinstance(fails, dict):
            fails = [fails]
        if fails:
            print("  BLOCKERS:")
            for f in fails:
                print(f"    {f.get('fullName')}: {f.get('problem')}")
        else:
            print("  No blockers.", "DELETED." if not check_only else "Safe to delete.")
        break
