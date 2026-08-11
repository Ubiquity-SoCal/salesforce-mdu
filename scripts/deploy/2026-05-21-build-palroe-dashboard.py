"""
Build the "MDU/SFU PALs/ROEs" dashboard (GRID layout) in MDU Sales Dashboards.
Top row: 6 small KPI tiles -- each count paired with its Units total
(PALs|PAL Units, ROEs|ROE Units, Activated|Activated Units). Below: charts.
Two dashboard filters (Category, MDU Categorization) re-slice every widget.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="MDU_Sales_Dashboards"; API="PALROE_Completed"; RF="MDU_Sales_Reports"
DFC = ("<dashboardFilterColumns><column>Opportunity.Property_Category__c</column></dashboardFilterColumns>"
       "<dashboardFilterColumns><column>Opportunity.MDU_Categorization__c</column></dashboardFilterColumns>")
if os.environ.get("SF_SESSION_ID"):
    sf = Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL", INSTANCE), session_id=os.environ["SF_SESSION_ID"])
else:
    sf = Salesforce(username=USER, password=PW, security_token=TOK)


def comp_metric(header, label, report):
    return f"""<componentType>Metric</componentType>
{DFC}
                <drillEnabled>false</drillEnabled>
                <drillToDetailEnabled>false</drillToDetailEnabled>
                <header>{header}</header>
                <indicatorHighColor>#54C254</indicatorHighColor>
                <indicatorLowColor>#C25454</indicatorLowColor>
                <indicatorMiddleColor>#D9D925</indicatorMiddleColor>
                <metricLabel>{label}</metricLabel>
                <report>{RF}/{report}</report>"""


def comp_chart(ctype, header, report, group, agg=None, col="RowCount", donut_total=False, pct=False, autoselect=False):
    summ = f"<axisBinding>y</axisBinding><column>{col}</column>"
    if agg:
        summ = f"<aggregate>{agg}</aggregate>" + summ
    extra = "<showTotal>true</showTotal>" if donut_total else ""
    return f"""<autoselectColumnsFromReport>{str(autoselect).lower()}</autoselectColumnsFromReport>
                <chartAxisRange>Auto</chartAxisRange>
                <chartSummary>{summ}</chartSummary>
                <componentType>{ctype}</componentType>
                {DFC}
                <displayUnits>Auto</displayUnits>
                <drillEnabled>false</drillEnabled>
                <drillToDetailEnabled>false</drillToDetailEnabled>
                <enableHover>true</enableHover>
                <expandOthers>false</expandOthers>
                <groupingColumn>{group}</groupingColumn>
                <header>{header}</header>
                <legendPosition>Bottom</legendPosition>
                <report>{RF}/{report}</report>
                <showPercentage>{str(pct).lower()}</showPercentage>
                <showValues>true</showValues>
                <sortBy>RowLabelAscending</sortBy>
                {extra}
                <useReportChart>false</useReportChart>"""


def comp_stacked(header, report):
    # autoselect mode: chart reads both report groupings (month X-axis, Agreement Type stack)
    return f"""<autoselectColumnsFromReport>true</autoselectColumnsFromReport>
                <chartAxisRange>Auto</chartAxisRange>
                <componentType>ColumnStacked</componentType>
                {DFC}
                <displayUnits>Auto</displayUnits>
                <drillEnabled>false</drillEnabled>
                <drillToDetailEnabled>false</drillToDetailEnabled>
                <enableHover>true</enableHover>
                <expandOthers>false</expandOthers>
                <header>{header}</header>
                <legendPosition>Bottom</legendPosition>
                <report>{RF}/{report}</report>
                <showPercentage>false</showPercentage>
                <showTotal>true</showTotal>
                <showValues>true</showValues>
                <sortBy>RowLabelAscending</sortBy>
                <useReportChart>false</useReportChart>"""


def comp_table(header, report):
    # Lightning table: shows the report's columns as rows; drill opens the full report.
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
# Row 0: 6 small KPI tiles (count + paired units)
kpis = [
    ("Signed PALs", "PALs", "PALROE_KPI_PALs", 0),
    ("PAL Units", "Units", "PALROE_KPI_PALs_Units", 2),
    ("Signed MDU ROEs", "ROEs", "PALROE_KPI_ROEs", 4),
    ("ROE Units", "Units", "PALROE_KPI_ROEs_Units", 6),
    ("Activated", "Activated", "PALROE_KPI_Activated", 8),
    ("Activated Units", "Units", "PALROE_KPI_Activated_Units", 10),
]
for header, label, rep, c in kpis:
    comps.append(grid(comp_metric(header, label, rep), c, 0, 2, 2))

# Row 1 (rowIndex 2): pipeline charts
comps.append(grid(comp_chart("Donut", "PAL vs MDU ROE", "PALROE_by_Type", "Agreement__c.Agreement_Type__c", pct=True), 0, 2, 4, 4))
comps.append(grid(comp_chart("Column", "Build Pipeline (count by status)", "PALROE_Doors_by_Stage", "Opportunity.ST_Build_Status__c"), 4, 2, 4, 4))
comps.append(grid(comp_chart("Donut", "Doors Secured by Build Status", "PALROE_Doors_by_Stage", "Opportunity.ST_Build_Status__c", agg="Sum", col="Opportunity.Units__c", donut_total=True, pct=True), 8, 2, 4, 4))

# Row 2 (rowIndex 6): breakdowns
comps.append(grid(comp_chart("Bar", "Sites by State", "PALROE_by_State", "Opportunity.Property_State__c"), 0, 6, 4, 4))
comps.append(grid(comp_chart("Donut", "By Category", "PALROE_by_Category", "Opportunity.Property_Category__c", pct=True), 4, 6, 4, 4))
comps.append(grid(comp_chart("Donut", "IronClad-synced vs Manual", "PALROE_by_SyncSource", "Agreement__c.Sync_Source__c", pct=True), 8, 6, 4, 4))

# Row 3 (rowIndex 10): velocity full width
comps.append(grid(comp_stacked("Signed by Month (PAL vs ROE)", "PALROE_by_Month"), 0, 10, 12, 3))

# Row 4 (rowIndex 13+): Data Cleanup -- signed/complete PAL/ROE not linked to SiteTracker
comps.append(grid(comp_metric("Not Linked to SiteTracker", "PAL/ROE", "PALROE_Not_Linked_SiteTracker"), 0, 13, 4, 2))
comps.append(grid(comp_table("Not Linked to SiteTracker (worklist)", "PALROE_Not_Linked_SiteTracker"), 0, 15, 12, 6))

filters = """    <dashboardFilters>
        <name>Category</name>
        <dashboardFilterOptions><operator>equals</operator><values>Cat 1</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>Cat 2</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>Cat 3</values></dashboardFilterOptions>
    </dashboardFilters>
    <dashboardFilters>
        <name>MDU Categorization</name>
        <dashboardFilterOptions><operator>equals</operator><values>OnNet</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>OffNet</values></dashboardFilterOptions>
        <dashboardFilterOptions><operator>equals</operator><values>NearNet</values></dashboardFilterOptions>
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
    <description>Signed PALs + ROEs on MDU/SFU; a site with both counts as PAL. All time. Every tile/chart shares this filter.</description>
    <isGridLayout>true</isGridLayout>
    <owner>{USER}</owner>
    <runningUser>{USER}</runningUser>
    <textColor>#000000</textColor>
    <title>MDU/SFU PALs/ROEs</title>
    <titleColor>#000000</titleColor>
    <titleSize>12</titleSize>
</Dashboard>"""

pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata"><types><members>{FOLDER}/{API}</members><name>Dashboard</name></types><version>{V}</version></Package>'
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr(f"dashboards/{FOLDER}/{API}.dashboard", dash)

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
    print(f"POST {r.status_code}: {r.text[:600]}"); raise SystemExit(1)
did = r.json()["id"]
for i in range(40):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st == "Succeeded":
        print("\nGrid dashboard deployed: MDU Sales Dashboards > MDU/SFU PALs/ROEs")
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
