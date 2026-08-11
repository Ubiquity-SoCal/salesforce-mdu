"""
Rebuild the MDU Cleanup Dashboard (classic 3-section) adding two tiles:
  - Not Linked to SiteTracker        -> PALROE_Not_Linked_SiteTracker (91)
  - PAL/ROE Complete: No Agreement   -> PALROE_Complete_No_Agreement  (10)
appended to the right section. Reproduces the existing 8 tiles verbatim so the
script is the authoritative source going forward. Re-runnable (overwrites).

Source of the existing 8 tiles: live retrieve 2026-05-22.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="MDU_Sales_Dashboards"; API="MDU_Cleanup_Dashboard"; RF="MDU_Sales_Reports"

if os.environ.get("SF_SESSION_ID"):
    sf = Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL", INSTANCE), session_id=os.environ["SF_SESSION_ID"])
else:
    sf = Salesforce(username=USER, password=PW, security_token=TOK)


def tile(header, footer, report):
    return f"""        <components>
            <autoselectColumnsFromReport>true</autoselectColumnsFromReport>
            <componentType>Metric</componentType>
            <displayUnits>Auto</displayUnits>
            <footer>{footer}</footer>
            <header>{header}</header>
            <indicatorBreakpoint1>1.0</indicatorBreakpoint1>
            <indicatorBreakpoint2>10.0</indicatorBreakpoint2>
            <indicatorHighColor>#B71C1C</indicatorHighColor>
            <indicatorLowColor>#2E7D32</indicatorLowColor>
            <indicatorMiddleColor>#E65100</indicatorMiddleColor>
            <metricLabel>Opps</metricLabel>
            <report>{RF}/{report}</report>
            <showRange>false</showRange>
        </components>"""


left = [
    ("Need IronClad ID — Signed", "Sign or Completed agreements without IronClad ID. Source of truth gap.", "Cleanup_Opps_Need_IC_ID_Signed"),
    ("Under Contract: No PAL", "PAL must be signed before SiteTracker handoff.", "Cleanup_Under_Contract_No_PAL"),
    ("No RE Assigned (active stages)", "Active stages: ROE Secured, Contract Negotiations, Under Contract.", "Cleanup_Opps_No_RE_Assigned"),
]
middle = [
    ("Need IC ID — Out for Sign", "Sign-status agreements out for signature without IronClad ID.", "Cleanup_Opps_Need_IC_ID_OutForSign"),
    ("No Property Location", "Active MDU Opps with no Property Location linked.", "Cleanup_Opps_No_Property_Location"),
    ("No Projected Close Date", "Active pursuits without a forecasted close date.", "Cleanup_Opps_No_Projected_Close"),
]
right = [
    ("Stale Active Opps", "Active opps not modified in 60+ days.", "Cleanup_Stale_Active_Opps"),
    ("Stale EMA/Bulk on wrong stage", "EMA/Bulk agreements on Opps not at the right stage. Review and clean up.", "Cleanup_Stale_EMA_Bulk_Opps"),
    # --- two new tiles (2026-05-22) ---
    ("Not Linked to SiteTracker", "Signed PAL/ROE (or stage PAL/ROE Complete+) with no SiteTracker project linked. Link it.", "PALROE_Not_Linked_SiteTracker"),
    ("PAL/ROE Complete: No Agreement", "Opps at PAL/ROE Complete or beyond with no agreement record. Create/attach the PAL/ROE.", "PALROE_Complete_No_Agreement"),
]


def section(name, tiles):
    inner = "\n".join(tile(*t) for t in tiles)
    return f"""    <{name}>
        <columnSize>Medium</columnSize>
{inner}
    </{name}>"""


dash = f"""<?xml version="1.0" encoding="UTF-8"?>
<Dashboard xmlns="http://soap.sforce.com/2006/04/metadata">
    <backgroundEndColor>#FFFFFF</backgroundEndColor>
    <backgroundFadeDirection>Diagonal</backgroundFadeDirection>
    <backgroundStartColor>#FFFFFF</backgroundStartColor>
    <dashboardType>SpecifiedUser</dashboardType>
    <isGridLayout>false</isGridLayout>
{section("leftSection", left)}
{section("middleSection", middle)}
    <owner>{USER}</owner>
{section("rightSection", right)}
    <runningUser>{USER}</runningUser>
    <textColor>#000000</textColor>
    <title>MDU Cleanup Dashboard</title>
    <titleColor>#1F3A68</titleColor>
    <titleSize>14</titleSize>
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
        print("\nMDU Cleanup Dashboard updated: 8 existing tiles + 2 new (Not Linked to SiteTracker, PAL/ROE Complete: No Agreement)")
        break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
