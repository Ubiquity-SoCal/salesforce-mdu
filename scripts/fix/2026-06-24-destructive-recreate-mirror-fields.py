"""The two SiteTracker_Project__c fields created earlier today stuck half-baked
(Tooling rows exist, name reserved, but not queryable; Tooling delete = insufficient
access, Tooling create = duplicate). Use the Metadata API to (1) destructively delete
them, then (2) recreate them in a MIRROR-ONLY package (the original deploy combined
this object with Opportunity in one CustomField package, which is the suspected cause).
Fields are empty -> delete is safe.
"""
import io, json, time, base64, zipfile, requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])
inst = f"https://{sf.sf_instance}"
V = "59.0"
url = f"{inst}/services/data/v{V}/metadata/deployRequest"

MEMBERS = ["SiteTracker_Project__c.Desktop_Design_Inputs_A__c",
           "SiteTracker_Project__c.Ready_for_Engineering__c"]


def post_deploy(files, label):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    raw = base64.b64encode(buf.getvalue()).decode()
    b64 = "\r\n".join(raw[i:i + 76] for i in range(0, len(raw), 76))
    body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True,
                              "rollbackOnError": True, "singlePackage": True}}
    bnd = "----B"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\n"
               f"Content-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
               f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\n"
               f"Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n"
               f"{b64}\r\n--{bnd}--")
    hdr = {"Authorization": f"Bearer {sf.session_id}",
           "Content-Type": f"multipart/form-data; boundary={bnd}"}
    did = requests.post(url, headers=hdr, data=payload).json()["id"]
    for _ in range(40):
        time.sleep(3)
        dr = requests.get(f"{url}/{did}?includeDetails=true",
                          headers={"Authorization": f"Bearer {sf.session_id}"}).json().get("deployResult", {})
        st = dr.get("status", "?")
        if st in ("Succeeded", "Failed", "Canceled", "SucceededPartial"):
            det = dr.get("details", {})
            for s in (det.get("componentSuccesses", []) or []):
                if isinstance(s, dict) and s.get("componentType"):
                    print(f"  [{label}] OK {s.get('fullName')} deleted={s.get('deleted')} created={s.get('created')}")
            for f in (det.get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  [{label}] FAIL {f.get('fullName')} - {f.get('problem')}")
            print(f"  [{label}] {st}")
            return st == "Succeeded"
    print(f"  [{label}] timed out")
    return False


def tooling_rows():
    q = ("SELECT Id, DeveloperName FROM CustomField WHERE DeveloperName "
         "IN ('Desktop_Design_Inputs_A','Ready_for_Engineering')")
    return sf.restful("tooling/query", params={"q": q})["records"]


# ── 1. destructive delete ──
empty_pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata"><version>{V}</version></Package>'
destruct = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Package xmlns="http://soap.sforce.com/2006/04/metadata"><types>'
            + "".join(f"<members>{m}</members>" for m in MEMBERS)
            + f"<name>CustomField</name></types><version>{V}</version></Package>")
print("Destructive delete...")
post_deploy({"package.xml": empty_pkg, "destructiveChanges.xml": destruct}, "delete")

for _ in range(8):
    time.sleep(5)
    if not tooling_rows():
        break
print("Tooling rows remaining after delete:", [r["DeveloperName"] for r in tooling_rows()])

# ── 2. recreate mirror-only ──
OBJ = ('<?xml version="1.0" encoding="UTF-8"?>'
       '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">'
       '<fields><fullName>Desktop_Design_Inputs_A__c</fullName>'
       '<label>Desktop Design Inputs and Floor Plan (A)</label><type>Date</type></fields>'
       '<fields><fullName>Ready_for_Engineering__c</fullName>'
       '<label>Ready for Engineering?</label><type>Checkbox</type><defaultValue>false</defaultValue></fields>'
       '</CustomObject>')
pkg = ('<?xml version="1.0" encoding="UTF-8"?>'
       '<Package xmlns="http://soap.sforce.com/2006/04/metadata"><types>'
       + "".join(f"<members>{m}</members>" for m in MEMBERS)
       + f"<name>CustomField</name></types><version>{V}</version></Package>")
print("Recreate mirror-only...")
post_deploy({"package.xml": pkg, "objects/SiteTracker_Project__c.object": OBJ}, "create")

# ── 3. verify queryable ──
ok = False
for attempt in range(18):
    time.sleep(10)
    try:
        sf.query("SELECT Id, Desktop_Design_Inputs_A__c, Ready_for_Engineering__c "
                 "FROM SiteTracker_Project__c LIMIT 1")
        ok = True
        print(f"queryable after ~{(attempt + 1) * 10}s")
        break
    except Exception:
        pass
print("RESULT:", "OK - both mirror fields queryable" if ok else "STILL STUCK - escalate")
