"""
Fix Business Sales app:
1. Delete accidental Business_Sales app (created in error)
2. Update Inside_Sales app with new tab order + rename Tracker to BUS Tracker
"""

import requests
import base64
import io
import zipfile
import time
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = _SF["username"]
PASSWORD_TOKEN = (_SF["password"] + _SF["token"])
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
V = "59.0"


def soap_login():
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body>
    <urn:login>
      <urn:username>{USERNAME}</urn:username>
      <urn:password>{PASSWORD_TOKEN}</urn:password>
    </urn:login>
  </soapenv:Body>
</soapenv:Envelope>"""
    resp = requests.post(LOGIN_URL, data=soap_body, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"
    })
    sid = ET.fromstring(resp.text).find(".//{urn:partner.soap.sforce.com}sessionId")
    if sid is None:
        print("[ERROR] Login failed")
        return None
    print("[OK] Logged in")
    return sid.text


def deploy_zip(session_id, zip_bytes, description):
    print(f"\n  Deploying: {description}")
    meta_url = f"{INSTANCE_URL}/services/Soap/m/{V}"
    z64 = base64.b64encode(zip_bytes).decode("utf-8")

    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{z64}</met:ZipFile>
      <met:DeployOptions>
        <met:singlePackage>true</met:singlePackage>
        <met:rollbackOnError>true</met:rollbackOnError>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(meta_url, data=soap, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"
    })
    deploy_id = ET.fromstring(resp.text).find(
        ".//{http://soap.sforce.com/2006/04/metadata}id"
    )
    if deploy_id is None:
        print("  [ERROR] No deploy ID")
        return False

    print(f"  Deploy ID: {deploy_id.text}")
    for _ in range(30):
        time.sleep(2)
        check = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id.text}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(meta_url, data=check, headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"
        })
        croot = ET.fromstring(cr.text)
        done = croot.find(".//{http://soap.sforce.com/2006/04/metadata}done")
        if done is not None and done.text == "true":
            ok = croot.find(".//{http://soap.sforce.com/2006/04/metadata}success")
            if ok is not None and ok.text == "true":
                print(f"  [OK] {description}")
                return True
            else:
                print(f"  [ERROR] {description} failed!")
                for m in croot.iter():
                    tag = m.tag.split("}")[-1] if "}" in m.tag else m.tag
                    if "problem" in tag.lower() and m.text:
                        print(f"    {m.text}")
                return False

    print("  [ERROR] Timed out")
    return False


def main():
    session_id = soap_login()
    if not session_id:
        return

    # ── Step 1: Delete accidental Business_Sales app ────────────────
    print("\n" + "=" * 60)
    print("STEP 1: DELETE ACCIDENTAL Business_Sales APP")
    print("=" * 60)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <version>59.0</version>
</Package>""")
        zf.writestr("destructiveChanges.xml", """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Business_Sales</members>
        <name>CustomApplication</name>
    </types>
    <version>59.0</version>
</Package>""")
    buf.seek(0)

    del_ok = deploy_zip(session_id, buf.read(), "Delete Business_Sales app")

    # ── Step 2: Update Inside_Sales with new tab order ──────────────
    print("\n" + "=" * 60)
    print("STEP 2: UPDATE Inside_Sales (new tab order + BUS Tracker)")
    print("=" * 60)

    app_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Business Sales</label>
    <formFactors>Large</formFactors>
    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>
    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>
    <isNavTabPersistenceDisabled>false</isNavTabPersistenceDisabled>
    <navType>Standard</navType>
    <uiType>Lightning</uiType>
    <tabs>standard-home</tabs>
    <tabs>Business_Tracker</tabs>
    <tabs>Property_Location__c</tabs>
    <tabs>Property_Unit__c</tabs>
    <tabs>standard-Opportunity</tabs>
    <tabs>Agreement__c</tabs>
    <tabs>standard-Contact</tabs>
    <tabs>standard-report</tabs>
</CustomApplication>"""

    tab_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">
    <flexiPage>Business_Tracker</flexiPage>
    <label>BUS Tracker</label>
    <motif>Custom70: Desk</motif>
</CustomTab>"""

    pkg_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Inside_Sales</members>
        <name>CustomApplication</name>
    </types>
    <types>
        <members>Business_Tracker</members>
        <name>CustomTab</name>
    </types>
    <version>59.0</version>
</Package>"""

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg_xml)
        zf.writestr("applications/Inside_Sales.app", app_xml)
        zf.writestr("tabs/Business_Tracker.tab", tab_xml)
    buf2.seek(0)

    upd_ok = deploy_zip(session_id, buf2.read(),
                        "Inside_Sales — new tab order + BUS Tracker rename")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Delete Business_Sales: {'OK' if del_ok else 'FAILED'}")
    print(f"  Update Inside_Sales:   {'OK' if upd_ok else 'FAILED'}")


if __name__ == "__main__":
    main()
