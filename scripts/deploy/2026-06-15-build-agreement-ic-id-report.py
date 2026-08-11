"""
Agreement-level "Need IronClad ID" report (Taylor, 6/15 follow-up): recreate the
opportunity-level Cleanup: Need IronClad ID (Signed) report at the AGREEMENT grain
so the team can see/populate each individual agreement that's missing its IC ID.

One row per signed (Completed) MDU agreement with a blank IronClad_ID__c, grouped
by Opportunity owner, with the IronClad ID column included (blank) so an export can
be filled in directly. Folder MDU_Sales_Reports (same as the opp-level original).

Deploy mechanics mirror today's funnel report build. Verified by grand total.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"; FOLDER="MDU_Sales_Reports"
RT="OpportunityCustomEntity$Agreement__c"
API="Cleanup_Agreements_Need_IC_ID"
LABEL="Cleanup: Need IronClad ID (Agreements)"
DESC=("MDU signed (Completed) agreements missing an IronClad ID, one row per agreement, "
      "grouped by owner. Worklist for populating IC IDs. Agreement-level recreation of the "
      "opp-level Need IronClad ID report.")

sf = Salesforce(username=USER, password=PW, security_token=TOK)

# filter building blocks
RC = ("RECORDTYPE", "equals", "Opportunity.MDU")
ST = ("Agreement__c.Status__c", "equals", "Completed")
IC = ("Agreement__c.IronClad_ID__c", "equals", "")   # blank IronClad ID

crit = [RC, ST, IC]
bf = "1 AND 2 AND 3"
GROUP = "FULL_NAME"   # Opportunity owner

cols = "".join(f"<columns><field>{c}</field></columns>" for c in [
    "OPPORTUNITY_NAME",
    "CUST_NAME",
    "Agreement__c.Agreement_Type__c",
    "Agreement__c.Status__c",
    "Agreement__c.Signed_Date__c",
    "Agreement__c.IronClad_ID__c",
    "Opportunity.RE_Assigned__c",
    "Opportunity.Property_State__c",
])


def crit_xml(items):
    return "".join(f"<criteriaItems><column>{c}</column><operator>{o}</operator><value>{v}</value></criteriaItems>"
                   for c, o, v in items)


report_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>{LABEL}</name>
    <description>{DESC}</description>
    <reportType>{RT}</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown><dateGranularity>None</dateGranularity><field>{GROUP}</field><sortOrder>Asc</sortOrder></groupingsDown>
    <timeFrameFilter><dateColumn>CLOSE_DATE</dateColumn><interval>INTERVAL_CUSTOM</interval></timeFrameFilter>
    {cols}
    <filter><booleanFilter>{bf}</booleanFilter>{crit_xml(crit)}</filter>
</Report>"""

pkg = (f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
       f'<types><members>{FOLDER}/{API}</members><name>Report</name></types><version>{V}</version></Package>')
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr(f"reports/{FOLDER}/{API}.report", report_xml)

url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
_raw = base64.b64encode(buf.getvalue()).decode()
b64 = "\r\n".join(_raw[i:i+76] for i in range(0, len(_raw), 76))
body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}:\n{r.text[:1500]}"); raise SystemExit(1)
did = r.json()["id"]
for i in range(40):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st == "Succeeded":
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)

hdr = {"Authorization": f"Bearer {sf.session_id}"}
rid = sf.query(f"SELECT Id FROM Report WHERE DeveloperName='{API}'")["records"][0]["Id"]
j = requests.get(sf.base_url + f"analytics/reports/{rid}", headers=hdr).json()
tot = j["factMap"].get("T!T", {}).get("aggregates", [{}])
print(f"\nReport Id: {rid}")
print(f"Grand total (agreements needing IC ID): {[a.get('label') for a in tot]}")
print("Per-owner:")
for g in j.get("groupingsDown", {}).get("groupings", []):
    key = g.get("key")
    cnt = j["factMap"].get(f"{key}!T", {}).get("aggregates", [{}])
    print(f"   {str(g.get('label')):<26} {[a.get('label') for a in cnt]}")
print("DONE.")
