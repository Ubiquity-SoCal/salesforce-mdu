"""
Stage 2b: the Business Penetration Lightning dashboard (grid layout) in the
"Inside Sales" dashboard folder, fed by the PropertyReports/BizPen_* reports.
Two filters (State, Penetration Priority) re-slice every widget.

Run validate-only by default; set APPLY=1 to commit (prod requires rollbackOnError).
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="InsideSales"; API="Business_Penetration"; RF="PropertyReports"
sf = Salesforce(username=USER, password=PW, security_token=TOK)
CHECKONLY = os.environ.get("APPLY") != "1"
print(f"[{'VALIDATE (checkOnly)' if CHECKONLY else 'APPLY'}]")

DFC = ("<dashboardFilterColumns><column>Property_Location__c.State__c</column></dashboardFilterColumns>"
       "<dashboardFilterColumns><column>Property_Location__c.Penetration_Priority__c</column></dashboardFilterColumns>")

def comp_metric(header, label, report):
    return f"""<componentType>Metric</componentType>
{DFC}
                <drillEnabled>false</drillEnabled>
                <drillToDetailEnabled>true</drillToDetailEnabled>
                <header>{header}</header>
                <indicatorHighColor>#54C254</indicatorHighColor>
                <indicatorLowColor>#C25454</indicatorLowColor>
                <indicatorMiddleColor>#D9D925</indicatorMiddleColor>
                <metricLabel>{label}</metricLabel>
                <report>{RF}/{report}</report>"""

def comp_chart(ctype, header, report, group, agg=None, col="RowCount", donut_total=False, pct=False):
    summ = f"<axisBinding>y</axisBinding><column>{col}</column>"
    if agg:
        summ = f"<aggregate>{agg}</aggregate>" + summ
    extra = "<showTotal>true</showTotal>" if donut_total else ""
    return f"""<autoselectColumnsFromReport>false</autoselectColumnsFromReport>
                <chartAxisRange>Auto</chartAxisRange>
                <chartSummary>{summ}</chartSummary>
                <componentType>{ctype}</componentType>
                {DFC}
                <displayUnits>Auto</displayUnits>
                <drillEnabled>false</drillEnabled>
                <drillToDetailEnabled>true</drillToDetailEnabled>
                <enableHover>true</enableHover>
                <expandOthers>true</expandOthers>
                <groupingColumn>{group}</groupingColumn>
                <header>{header}</header>
                <legendPosition>Bottom</legendPosition>
                <report>{RF}/{report}</report>
                <showPercentage>{str(pct).lower()}</showPercentage>
                <showValues>true</showValues>
                <sortBy>RowLabelAscending</sortBy>
                {extra}
                <useReportChart>false</useReportChart>"""

def comp_table(header, report):
    return f"""<autoselectColumnsFromReport>true</autoselectColumnsFromReport>
                <componentType>Table</componentType>
                {DFC}
                <drillEnabled>true</drillEnabled>
                <drillToDetailEnabled>true</drillToDetailEnabled>
                <header>{header}</header>
                <indicatorHighColor>#54C254</indicatorHighColor>
                <indicatorLowColor>#C25454</indicatorLowColor>
                <indicatorMiddleColor>#C2C254</indicatorMiddleColor>
                <report>{RF}/{report}</report>
                <useReportChart>false</useReportChart>"""

def grid(inner, col, row, cspan, rspan):
    return f"""        <dashboardGridComponents>
            <colSpan>{cspan}</colSpan>
            <columnIndex>{col}</columnIndex>
            <dashboardComponent>
                {inner}
            </dashboardComponent>
            <rowIndex>{row}</rowIndex>
            <rowSpan>{rspan}</rowSpan>
        </dashboardGridComponents>"""

comps = []
# Row 0: KPI tiles
kpis = [
    ("Lit Buildings", "Buildings", "BizPen_Lit", 0),
    ("Overall Penetration", "Penetration %", "BizPen_KPI_Pen", 2),
    ("Active Units", "Active", "BizPen_ActiveUnits", 4),
    ("Deactivated Units", "Deactivated", "BizPen_DeactUnits", 6),
    ("Category 1 (lit, unsold)", "Buildings", "BizPen_Cat1", 8),
    ("Category 2 (pipeline)", "Buildings", "BizPen_Cat2", 10),
]
for header, label, rep, c in kpis:
    comps.append(grid(comp_metric(header, label, rep), c, 0, 2, 2))

# Row 1 (rowIndex 2): charts
comps.append(grid(comp_chart("Bar", "Penetration % by State", "BizPen_by_State",
                             "Property_Location__c.State__c", col="FORMULA1"), 0, 2, 4, 4))
comps.append(grid(comp_chart("Donut", "Priority Mix (all business)", "BizPen_Priority_Mix",
                             "Property_Location__c.Penetration_Priority__c", pct=True), 4, 2, 4, 4))
comps.append(grid(comp_chart("Column", "Penetration Distribution (lit)", "BizPen_Distribution",
                             "BucketField_Pen"), 8, 2, 4, 4))

# Row 2 (rowIndex 6): Category 1 action list, full width
comps.append(grid(comp_table("Category 1 Action List (lowest penetration first)", "BizPen_Cat1_List"), 0, 6, 12, 8))

filters = """    <dashboardFilters>
        <name>State</name>
        <dashboardFilterOptions><operator>equals</operator><values>TX</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>NE</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>AZ</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>CA</values></dashboardFilterOptions>
    </dashboardFilters>
    <dashboardFilters>
        <name>Penetration Priority</name>
        <dashboardFilterOptions><operator>equals</operator><values>Category 1</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>Category 2</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>Category 3</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>All Active</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>Hold</values></dashboardFilterOptions>
    </dashboardFilters>"""

dash = f"""<?xml version="1.0" encoding="UTF-8"?>
<Dashboard xmlns="http://soap.sforce.com/2006/04/metadata">
    <backgroundEndColor>#FFFFFF</backgroundEndColor>
    <backgroundFadeDirection>Diagonal</backgroundFadeDirection>
    <backgroundStartColor>#FFFFFF</backgroundStartColor>
{filters}
    <dashboardGridLayout>
{chr(10).join(comps)}
        <numberOfColumns>12</numberOfColumns>
        <rowHeight>60</rowHeight>
    </dashboardGridLayout>
    <dashboardType>SpecifiedUser</dashboardType>
    <description>Business serviceable penetration from Vetro (Property_Location). Lit = Cat1 + All Active. Penetration = active/total units. Filters re-slice every widget.</description>
    <isGridLayout>true</isGridLayout>
    <owner>{USER}</owner>
    <runningUser>{USER}</runningUser>
    <textColor>#000000</textColor>
    <title>Business Penetration</title>
    <titleColor>#000000</titleColor>
    <titleSize>12</titleSize>
</Dashboard>"""

pkg = (f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
       f'<types><members>{FOLDER}/{API}</members><name>Dashboard</name></types><version>{V}</version></Package>')
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr(f"dashboards/{FOLDER}/{API}.dashboard", dash)

url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
_raw = base64.b64encode(buf.getvalue()).decode()
b64 = "\r\n".join(_raw[i:i+76] for i in range(0, len(_raw), 76))
body = {"deployOptions": {"checkOnly": CHECKONLY, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}: {r.text[:800]}"); raise SystemExit(1)
did = r.json()["id"]
for i in range(50):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st == "Succeeded":
        if CHECKONLY:
            print("\nValidation passed. Re-run with APPLY=1 to commit.")
        else:
            print(f"\nDashboard deployed: Inside Sales > Business Penetration")
            print(f"  {INSTANCE}/lightning/r/Dashboard/")
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
