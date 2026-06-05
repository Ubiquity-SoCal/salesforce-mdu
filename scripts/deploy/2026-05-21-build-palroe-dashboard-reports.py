"""
Supporting reports for the PAL/ROE Completed dashboard. All share the combined
PAL + MDU-ROE population with PAL-priority dedup (booleanFilter), in folder
MDU_Sales_Reports. Deployed in one package. Verified by grand-total counts.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"; FOLDER="MDU_Sales_Reports"
RT = "OpportunityCustomEntity$Agreement__c"
if os.environ.get("SF_SESSION_ID"):
    sf = Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL", INSTANCE), session_id=os.environ["SF_SESSION_ID"])
else:
    sf = Salesforce(username=USER, password=PW, security_token=TOK)

# shared criteria building blocks
RC   = ("RECORDTYPE", "equals", "Opportunity.MDU")
SD   = ("Agreement__c.Signed_Date__c", "notEqual", "")
PAL  = ("Agreement__c.Agreement_Type__c", "equals", "PAL")
ROE  = ("Agreement__c.Agreement_Type__c", "equals", "ROE")
NOPAL= ("Opportunity.Signed_PAL_Date_Count__c", "equals", "0")
DONE = ("Opportunity.ST_Build_Status__c", "equals", "4. Project - Completed")
# 2026-05-22 (Taylor): "signed/completed" = Status Completed (or Cancelled-if-signed) AND has agreement date.
STAT = ("Agreement__c.Status__c", "equals", "Completed,Cancelled")

COMBINED = ([RC, SD, PAL, ROE, NOPAL, STAT], "1 AND 2 AND (3 OR (4 AND 5)) AND 6")
PAL_ONLY = ([RC, SD, PAL, STAT], "1 AND 2 AND 3 AND 4")
ROE_ONLY = ([RC, SD, ROE, NOPAL, STAT], "1 AND 2 AND 3 AND 4 AND 5")
ACTIVATED= ([RC, SD, PAL, ROE, NOPAL, DONE, STAT], "1 AND 2 AND (3 OR (4 AND 5)) AND 6 AND 7")

# plain = name only (count reports + KPI metrics); doors = name + Units summed (Sum-of-Units chart)
COLS_PLAIN = "<columns><field>OPPORTUNITY_NAME</field></columns>"
COLS_DOORS = ("<columns><field>OPPORTUNITY_NAME</field></columns>"
              "<columns><aggregateTypes>Sum</aggregateTypes><field>Opportunity.Units__c</field></columns>")


def crit_xml(items):
    out = ""
    for col, op, val in items:
        out += f"<criteriaItems><column>{col}</column><operator>{op}</operator><value>{val}</value></criteriaItems>"
    return out


def report_xml(name, fmt, crit, bf, gfield=None, gran=None, cols=COLS_PLAIN, desc="", gfield2=None):
    grp = ""
    if gfield:
        grp = f"<groupingsDown><dateGranularity>{gran or 'None'}</dateGranularity><field>{gfield}</field><sortOrder>Asc</sortOrder></groupingsDown>"
    if gfield2:
        grp += f"<groupingsDown><dateGranularity>None</dateGranularity><field>{gfield2}</field><sortOrder>Asc</sortOrder></groupingsDown>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>{name}</name>
    <description>{desc}</description>
    <reportType>{RT}</reportType>
    <format>{fmt}</format>
    <scope>organization</scope>
    {grp}
    <timeFrameFilter><dateColumn>CLOSE_DATE</dateColumn><interval>INTERVAL_CUSTOM</interval></timeFrameFilter>
    {cols}
    <filter><booleanFilter>{bf}</booleanFilter>{crit_xml(crit)}</filter>
</Report>"""


# (api_name, label, (crit,bf), gfield, gran, cols, desc)  -- all Summary
BUILD = "Opportunity.ST_Build_Status__c"
SH = "MDU; signed PALs + MDU ROEs (site with both = PAL); all time."
REPORTS = [
    ("PALROE_by_Type",       "PAL/ROE Completed by Type",         COMBINED,  "Agreement__c.Agreement_Type__c",  None,    COLS_PLAIN, SH+" Grouped by Agreement Type."),
    ("PALROE_by_State",      "PAL/ROE Completed by State",        COMBINED,  "Opportunity.Property_State__c",    None,    COLS_PLAIN, SH+" Grouped by State."),
    ("PALROE_by_Category",   "PAL/ROE Completed by Category",     COMBINED,  "Opportunity.Property_Category__c", None,    COLS_PLAIN, SH+" Grouped by Category."),
    ("PALROE_by_SyncSource", "PAL/ROE Completed by Sync Source",  COMBINED,  "Agreement__c.Sync_Source__c",     None,    COLS_PLAIN, SH+" Grouped by Sync Source (IronClad vs manual)."),
    ("PALROE_by_Month",      "PAL/ROE Signed by Month",           COMBINED,  "Agreement__c.Signed_Date__c",     "Month", COLS_PLAIN, SH+" Grouped by month signed."),
    ("PALROE_Doors_by_Stage","PAL/ROE Doors by Build Status",     COMBINED,  BUILD,                             None,    COLS_DOORS, SH+" Units summed, grouped by SiteTracker Build Status."),
    ("PALROE_KPI_PALs",      "KPI - Signed PALs",                 PAL_ONLY,  BUILD,                             None,    COLS_PLAIN, "MDU signed PALs only. All time."),
    ("PALROE_KPI_ROEs",      "KPI - Signed MDU ROEs",             ROE_ONLY,  BUILD,                             None,    COLS_PLAIN, "MDU signed ROEs on sites with no signed PAL. All time."),
    ("PALROE_KPI_Activated", "KPI - Activated",                   ACTIVATED, BUILD,                             None,    COLS_PLAIN, SH+" Build Status = Completed."),
    ("PALROE_KPI_PALs_Units","KPI - PAL Units",                   PAL_ONLY,  BUILD,                             None,    COLS_DOORS, "MDU signed PALs - total units. All time."),
    ("PALROE_KPI_ROEs_Units","KPI - MDU ROE Units",               ROE_ONLY,  BUILD,                             None,    COLS_DOORS, "MDU signed ROEs (no signed PAL) - total units. All time."),
    ("PALROE_KPI_Activated_Units","KPI - Activated Units",        ACTIVATED, BUILD,                             None,    COLS_DOORS, "Activated MDU PAL/ROE - total units. All time."),
]

files = {}
members = []
for api, label, (crit, bf), gfield, gran, cols, desc in REPORTS:
    g2 = "Agreement__c.Agreement_Type__c" if api == "PALROE_by_Month" else None  # 2nd grouping for stacked chart
    files[f"reports/{FOLDER}/{api}.report"] = report_xml(label, "Summary", crit, bf, gfield=gfield, gran=gran, cols=cols, desc=desc, gfield2=g2)
    members.append(f"{FOLDER}/{api}")

types = "".join(f"<members>{m}</members>" for m in members) + "<name>Report</name>"
pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata"><types>{types}</types><version>{V}</version></Package>'
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    for path, content in files.items():
        zf.writestr(path, content)

# deploy
url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
_raw = base64.b64encode(buf.getvalue()).decode()
b64 = "\r\n".join(_raw[i:i+76] for i in range(0, len(_raw), 76))  # line-wrap for multipart buffer
body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}:\n{r.text[:1000]}"); raise SystemExit(1)
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

# verify grand totals
hdr = {"Authorization": f"Bearer {sf.session_id}"}
print("\nVerification (grand totals):")
for api, label, *_ in REPORTS:
    rid = sf.query(f"SELECT Id FROM Report WHERE DeveloperName='{api}'")["records"][0]["Id"]
    j = requests.get(sf.base_url + f"analytics/reports/{rid}", headers=hdr).json()
    tot = j["factMap"].get("T!T", {}).get("aggregates", [{}])[0].get("label")
    print(f"   {api:<24} {label:<32} -> {tot}")
