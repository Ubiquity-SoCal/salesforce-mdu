"""
Stage 2a: reports for the Business Penetration dashboard, in folder PropertyReports.
Source object Property_Location__c (reportType CustomEntity$Property_Location__c).
Every report is scoped to business + non-stale. Deployed in one package, then
grand totals are verified via the Analytics API.

Reports:
  BizPen_Lit            count of lit buildings (Cat1 + All Active)   -> KPI
  BizPen_ActiveUnits    SUM Active_Unit_Count (lit)                  -> KPI
  BizPen_DeactUnits     SUM Deactive_Unit_Count (lit)               -> KPI
  BizPen_Cat1           count Category 1                             -> KPI
  BizPen_Cat2           count Category 2 (pipeline)                  -> KPI
  BizPen_by_State       penetration % CSF by State (lit)            -> KPI + bar
  BizPen_Priority_Mix   count by Penetration_Priority (all biz)     -> donut
  BizPen_Distribution   count by penetration band bucket (lit)      -> bar
  BizPen_Cat1_List      tabular action list of Category 1           -> table
"""
import requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="PropertyReports"; RT="CustomEntity$Property_Location__c"
sf = Salesforce(username=USER, password=PW, security_token=TOK)

P = "Property_Location__c."
# scope criteria building blocks
BIZ   = (f"{P}Address_Type__c", "equals", "Business")
LIVE  = (f"{P}Import_Delete_Property__c", "equals", "0")
LIT   = (f"{P}Penetration_Priority__c", "equals", "Category 1,All Active")
CAT1  = (f"{P}Penetration_Priority__c", "equals", "Category 1")
CAT2  = (f"{P}Penetration_Priority__c", "equals", "Category 2")

def crit(items):
    return "".join(f"<criteriaItems><column>{c}</column><columnToColumn>false</columnToColumn>"
                   f"<operator>{o}</operator><value>{v}</value></criteriaItems>" for c, o, v in items)

CSF = (f"<aggregates><calculatedFormula>{P}Active_Unit_Count__c:SUM / "
       f"{P}Property_Unit_Count__c:SUM * 100</calculatedFormula>"
       "<datatype>number</datatype><developerName>FORMULA1</developerName>"
       "<isActive>true</isActive><masterLabel>Penetration %</masterLabel><scale>1</scale></aggregates>")

BUCKET = (f"<buckets><bucketType>number</bucketType><developerName>BucketField_Pen</developerName>"
          "<masterLabel>Penetration Band</masterLabel><nullTreatment>n</nullTreatment>"
          f"<sourceColumnName>{P}Penetration__c</sourceColumnName>"
          "<values><sourceValues><to>0</to></sourceValues><value>0%</value></values>"
          "<values><sourceValues><from>0</from><to>25</to></sourceValues><value>1-25%</value></values>"
          "<values><sourceValues><from>25</from><to>50</to></sourceValues><value>26-50%</value></values>"
          "<values><sourceValues><from>50</from><to>75</to></sourceValues><value>51-75%</value></values>"
          "<values><sourceValues><from>75</from></sourceValues><value>76-100%</value></values></buckets>")

def col(field, agg=None):
    a = f"<aggregateTypes>{agg}</aggregateTypes>" if agg else ""
    return f"<columns>{a}<field>{field}</field></columns>"

def report(name, fmt, criteria, bf, cols, group=None, desc="", aggregates="", buckets="", sort=None):
    grp = f"<groupingsDown><dateGranularity>None</dateGranularity><field>{group}</field><sortOrder>Asc</sortOrder></groupingsDown>" if group else ""
    srt = f"<sortColumn>{sort[0]}</sortColumn><sortOrder>{sort[1]}</sortOrder>" if sort else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>{name}</name>
    <description>{desc}</description>
    <reportType>{RT}</reportType>
    <format>{fmt}</format>
    <scope>organization</scope>
    {buckets}{aggregates}{grp}{cols}{srt}
    <filter><booleanFilter>{bf}</booleanFilter>{crit(criteria)}</filter>
</Report>"""

NAME = "CUST_NAME"
ACT = f"{P}Active_Unit_Count__c"; TOT = f"{P}Property_Unit_Count__c"; DEA = f"{P}Deactive_Unit_Count__c"
PEN = f"{P}Penetration__c"; ST = f"{P}State__c"; CITY = f"{P}City__c"; OWN = f"{P}User__c"
PRIO = f"{P}Penetration_Priority__c"
SH = "Business serviceable, non-stale, from Vetro."

reports = {
 "BizPen_Lit": report("Biz Penetration - Lit Buildings", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME), group=ST, desc=SH+" Lit = Cat1 + All Active."),
 "BizPen_ActiveUnits": report("Biz Penetration - Active Units", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME)+col(ACT, "Sum"), group=ST, desc=SH+" Active units in lit buildings."),
 "BizPen_DeactUnits": report("Biz Penetration - Deactivated Units", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME)+col(DEA, "Sum"), group=ST, desc=SH+" Deactivated units in lit buildings."),
 "BizPen_Cat1": report("Biz Penetration - Category 1", "Summary", [BIZ, LIVE, CAT1],
    "1 AND 2 AND 3", col(NAME), group=ST, desc=SH+" Multi-unit lit, not fully sold."),
 "BizPen_Cat2": report("Biz Penetration - Category 2 Pipeline", "Summary", [BIZ, LIVE, CAT2],
    "1 AND 2 AND 3", col(NAME), group=ST, desc=SH+" Multi-unit, no customers yet."),
 "BizPen_by_State": report("Biz Penetration - by State", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME)+col(ACT, "Sum")+col(TOT, "Sum"), group=ST,
    desc=SH+" Door-weighted penetration % by state.", aggregates=CSF),
 "BizPen_KPI_Pen": report("Biz Penetration - Overall % (KPI)", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME), group=ST,
    desc=SH+" Door-weighted overall penetration % over lit buildings.", aggregates=CSF),
 "BizPen_Priority_Mix": report("Biz Penetration - Priority Mix", "Summary", [BIZ, LIVE],
    "1 AND 2", col(NAME), group=PRIO, desc=SH+" Building count by Penetration Priority."),
 "BizPen_Distribution": report("Biz Penetration - Distribution", "Summary", [BIZ, LIVE, LIT],
    "1 AND 2 AND 3", col(NAME), group="BucketField_Pen", desc=SH+" Lit buildings by penetration band.",
    buckets=BUCKET),
 # Summary (grouped by State) not Tabular: a tabular report needs special dashboard
 # settings to be a table-component source; a grouped summary works directly.
 "BizPen_Cat1_List": report("Biz Penetration - Category 1 Action List", "Summary", [BIZ, LIVE, CAT1],
    "1 AND 2 AND 3",
    col(NAME)+col(CITY)+col(OWN)+col(TOT)+col(ACT)+col(DEA)+col(PEN),
    group=ST,
    desc=SH+" Category 1 buildings to chase, by state, lowest penetration first.",
    sort=(PEN, "Asc")),
}

files = {f"reports/{FOLDER}/{api}.report": xml for api, xml in reports.items()}
members = "".join(f"<members>{FOLDER}/{api}</members>" for api in reports)
pkg = (f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
       f'<types>{members}<name>Report</name></types><version>{V}</version></Package>')

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    for path, content in files.items():
        zf.writestr(path, content)

url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
_raw = base64.b64encode(buf.getvalue()).decode()
b64 = "\r\n".join(_raw[i:i+76] for i in range(0, len(_raw), 76))
import os

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

CHECKONLY = os.environ.get("APPLY") != "1"   # default validate-only; set APPLY=1 to commit
body = {"deployOptions": {"checkOnly": CHECKONLY, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
print(f"[{'VALIDATE (checkOnly)' if CHECKONLY else 'APPLY'}]")
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}: {r.text[:800]}"); raise SystemExit(1)
did = r.json()["id"]
ok = False
for i in range(50):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st in ("Succeeded", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        ok = True; break
    if st in ("Failed", "Canceled"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
if not ok:
    print("timeout"); raise SystemExit(1)

if CHECKONLY:
    print("\nValidation passed (checkOnly). Re-run with APPLY=1 to commit."); raise SystemExit(0)

# verify grand totals via analytics API
hdr = {"Authorization": f"Bearer {sf.session_id}"}
print("\nVerification (grand totals):")
for api in reports:
    recs = sf.query(f"SELECT Id FROM Report WHERE DeveloperName='{api}'")["records"]
    if not recs:
        print(f"   {api:<22} -> NOT DEPLOYED"); continue
    j = requests.get(sf.base_url + f"analytics/reports/{recs[0]['Id']}", headers=hdr).json()
    agg = j["factMap"].get("T!T", {}).get("aggregates", [])
    vals = ", ".join(str(a.get("label")) for a in agg)
    print(f"   {api:<22} -> {vals}")
