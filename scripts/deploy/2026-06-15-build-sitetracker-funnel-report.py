"""
Item 2 — SiteTracker build-funnel report.

A Summary report on SiteTracker_Project__c grouped by Build_Status__c (the
"1. PAL/ROE Signed" -> "4. Completed" pipeline, already numerically ordered so it
reads as a funnel), record count + Total_Units__c summed, with a horizontal-bar
chart of project count by phase.

MDU-only by nature: SiteTracker_Project__c currently holds only MDU rows (SFU
lives on Lit_Fiber__c, not synced — see item 3). Cancelled is excluded upstream
by the sync, so this reflects active MDU builds.

Deploy mechanics mirror 2026-05-21-build-palroe-dashboard-reports.py (proven).
Verified by grand total + per-phase breakdown via the analytics API.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER = _SF["username"]; PW = _SF["password"]; TOK = _SF["token"]
INSTANCE = "https://fun-power-747.my.salesforce.com"; V = "59.0"; FOLDER = "MDU_Sales_Reports"
RT = "Opportunity"                     # standard Opportunity report type
GROUP = "Opportunity.ST_Build_Status__c"   # SiteTracker phase surfaced onto the Opp
UNITS = "Opportunity.Units__c"
NAMECOL = "OPPORTUNITY_NAME"
API = "SiteTracker_Build_Funnel"
LABEL = "SiteTracker Build Funnel"
DESC = ("MDU build pipeline: MDU Opps with a SiteTracker build, grouped by Build Status "
        "(PAL/ROE Signed -> Design -> Construction -> Completed), units summed. Excludes "
        "pre-build. MDU-only (SFU not yet synced).")

if os.environ.get("SF_SESSION_ID"):
    sf = Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL", INSTANCE), session_id=os.environ["SF_SESSION_ID"])
else:
    sf = Salesforce(username=USER, password=PW, security_token=TOK)

report_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>{LABEL}</name>
    <description>{DESC}</description>
    <reportType>{RT}</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>{GROUP}</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <timeFrameFilter><dateColumn>CLOSE_DATE</dateColumn><interval>INTERVAL_CUSTOM</interval></timeFrameFilter>
    <columns><field>{NAMECOL}</field></columns>
    <columns><aggregateTypes>Sum</aggregateTypes><field>{UNITS}</field></columns>
    <filter>
        <booleanFilter>1 AND 2</booleanFilter>
        <criteriaItems><column>RECORDTYPE</column><operator>equals</operator><value>Opportunity.MDU</value></criteriaItems>
        <criteriaItems><column>{GROUP}</column><operator>notEqual</operator><value></value></criteriaItems>
    </filter>
    <chart>
        <chartType>HorizontalBar</chartType>
        <groupingColumn>{GROUP}</groupingColumn>
        <location>CHART_TOP</location>
        <size>Medium</size>
        <summaryAxisRange>Auto</summaryAxisRange>
        <chartSummaries>
            <axisBinding>y</axisBinding>
            <column>RowCount</column>
        </chartSummaries>
        <title>Projects by Build Phase</title>
    </chart>
</Report>"""

# Drop the optional inactive custom-summary aggregate if it trips validation; keep XML minimal-safe.
files = {f"reports/{FOLDER}/{API}.report": report_xml}
pkg = (f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
       f'<types><members>{FOLDER}/{API}</members><name>Report</name></types><version>{V}</version></Package>')

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    for path, content in files.items():
        zf.writestr(path, content)

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
final = None
for i in range(40):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    final = res
    if st == "Succeeded":
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)

# verify: grand total + per-phase breakdown
hdr = {"Authorization": f"Bearer {sf.session_id}"}
rid = sf.query(f"SELECT Id FROM Report WHERE DeveloperName='{API}'")["records"][0]["Id"]
j = requests.get(sf.base_url + f"analytics/reports/{rid}", headers=hdr).json()
tot = j["factMap"].get("T!T", {}).get("aggregates", [{}])
print(f"\nReport Id: {rid}")
print(f"Grand totals: {[a.get('label') for a in tot]}")
print("\nPer-phase (Build Status) breakdown:")
groupings = j.get("groupingsDown", {}).get("groupings", [])
for g in groupings:
    key = g.get("key")
    cnt = j["factMap"].get(f"{key}!T", {}).get("aggregates", [{}])
    label = g.get("label")
    vals = [a.get("label") for a in cnt]
    print(f"   {str(label):<32} {vals}")
print("\nDONE.")
