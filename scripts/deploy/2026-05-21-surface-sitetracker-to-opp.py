"""
Surface SiteTracker Build Status + Activation (Actual) onto the Opportunity so
they can be columns on the PAL/ROE Completed report (SiteTracker is a sibling
child of Opportunity, so its fields can't join that report type directly).

Creates Opportunity.ST_Build_Status__c (text) and ST_Activation_Actual__c (date),
then backfills from each Opp's MOST-ADVANCED SiteTracker project. One-time backfill;
ongoing freshness requires extending the daily SiteTracker sync (flagged separately).
Audit log written to data/output/audit_logs/.
"""
import requests, json, time, base64, io, zipfile, csv, os
from datetime import datetime, timezone
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
sf = Salesforce(username=USER, password=PW, security_token=TOK)


def deploy(files, members_types, label):
    types_xml = "".join(f"<types><members>{m}</members><name>{t}</name></types>" for m, t in members_types)
    pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">{types_xml}<version>{V}</version></Package>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg)
        for path, content in files.items():
            zf.writestr(path, content)
    url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
    b64 = base64.b64encode(buf.getvalue()).decode()
    body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
    bnd = "----B"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
               f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
               f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
    r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json()["id"]
    for i in range(40):
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


# ---- Step 1: create the two Opp fields (standard object: deploy only <fields>) ----
existing = [f["name"] for f in sf.Opportunity.describe()["fields"]]
need = []
if "ST_Build_Status__c" not in existing:
    need.append("""    <fields>
        <fullName>ST_Build_Status__c</fullName>
        <label>SiteTracker Build Status</label>
        <type>Text</type><length>100</length>
        <description>SiteTracker build status of the Opp's most-advanced SiteTracker project. Backfilled/synced from SiteTracker_Project__c.</description>
    </fields>""")
if "ST_Activation_Actual__c" not in existing:
    need.append("""    <fields>
        <fullName>ST_Activation_Actual__c</fullName>
        <label>SiteTracker Activation (Actual)</label>
        <type>Date</type>
        <description>Actual activation date from the Opp's most-advanced SiteTracker project. Backfilled/synced from SiteTracker_Project__c.</description>
    </fields>""")
if need:
    obj = f'<?xml version="1.0" encoding="UTF-8"?>\n<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n{chr(10).join(need)}\n</CustomObject>'
    if not deploy({"objects/Opportunity.object": obj}, [("Opportunity", "CustomObject")], "opp-fields"):
        raise SystemExit(1)
    prof = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions><editable>true</editable><field>Opportunity.ST_Build_Status__c</field><readable>true</readable></fieldPermissions>
    <fieldPermissions><editable>true</editable><field>Opportunity.ST_Activation_Actual__c</field><readable>true</readable></fieldPermissions>
</Profile>"""
    deploy({"profiles/Admin.profile": prof}, [("Admin", "Profile")], "fls")
else:
    print("Both Opp fields already exist; skipping field deploy.")

# ---- Step 2: backfill from most-advanced ST project ----
sf = Salesforce(username=USER, password=PW, security_token=TOK)  # refresh after schema change
RANK = {
    "4. Project - Completed": 5,
    "3. Project - Construction Phase": 4,
    "2. Project - Design Phase": 3,
    "2. Project - Up Next": 2,
    "1. Project - PAL/ROE Signed": 1,
    "5. Project - Pending Business Case Approval": 0,
}
st = sf.query_all("SELECT Opportunity__c, Build_Status__c, Activation_Actual__c, LastModifiedDate FROM SiteTracker_Project__c WHERE Opportunity__c != null")["records"]
byopp = {}
for s in st:
    byopp.setdefault(s["Opportunity__c"], []).append(s)

def primary(projs):
    return sorted(projs, key=lambda p: (RANK.get(p["Build_Status__c"], -1), p["LastModifiedDate"]), reverse=True)[0]

updates = []
for oid, projs in byopp.items():
    p = primary(projs)
    updates.append({"Id": oid, "ST_Build_Status__c": p["Build_Status__c"], "ST_Activation_Actual__c": p["Activation_Actual__c"]})

print(f"\nBackfilling {len(updates)} Opportunities from their primary ST project...")
os.makedirs(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs", exist_ok=True)
audit = r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-21-st-surface-backfill.csv"
ts = datetime.now(timezone.utc).isoformat()
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["SF_Id", "ST_Build_Status", "ST_Activation_Actual", "Source", "Timestamp", "Action"])
    for u in updates:
        w.writerow([u["Id"], u["ST_Build_Status__c"], u["ST_Activation_Actual__c"], "SiteTracker_Project__c primary", ts, "update"])

res = sf.bulk.Opportunity.update(updates)
ok = sum(1 for r in res if r.get("success"))
err = [r for r in res if not r.get("success")]
print(f"  updated={ok}  errors={len(err)}")
for e in err[:5]: print("   ERR:", e)
print(f"  audit log -> {audit}")
