"""
Remove Reports tab from MDU_Sales and Inside_Sales apps.
Fix Home dashboard links to open in new browser tab.
"""

import requests
import base64
import io
import zipfile
import time
from xml.etree import ElementTree as ET

LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD"
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

    # ── Step 1: Update both apps — remove Reports tab ───────────────
    print("\n" + "=" * 60)
    print("STEP 1: REMOVE REPORTS TAB FROM BOTH APPS")
    print("=" * 60)

    mdu_app = """<?xml version="1.0" encoding="UTF-8"?>
<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MDU Sales</label>
    <formFactors>Large</formFactors>
    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>
    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>
    <isNavTabPersistenceDisabled>false</isNavTabPersistenceDisabled>
    <navType>Standard</navType>
    <uiType>Lightning</uiType>
    <tabs>standard-home</tabs>
    <tabs>MDU_Tracker</tabs>
    <tabs>standard-Opportunity</tabs>
    <tabs>Agreement__c</tabs>
    <tabs>standard-Contact</tabs>
    <tabs>standard-Account</tabs>
    <tabs>SiteTracker_Project__c</tabs>
</CustomApplication>"""

    bus_app = """<?xml version="1.0" encoding="UTF-8"?>
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
</CustomApplication>"""

    pkg1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales</members>
        <members>Inside_Sales</members>
        <name>CustomApplication</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf1 = io.BytesIO()
    with zipfile.ZipFile(buf1, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg1)
        zf.writestr("applications/MDU_Sales.app", mdu_app)
        zf.writestr("applications/Inside_Sales.app", bus_app)
    buf1.seek(0)

    deploy_zip(session_id, buf1.read(), "Remove Reports tab from both apps")

    # ── Step 2: Fix Home dashboard links to open in new tab ─────────
    print("\n" + "=" * 60)
    print("STEP 2: FIX HOME DASHBOARD LINKS (open in new tab)")
    print("=" * 60)

    # Retrieve current VF page, fix target, redeploy
    meta_url = f"{INSTANCE_URL}/services/Soap/m/{V}"

    # Retrieve
    pkg_retrieve = f"""
          <types>
            <members>InsideSalesDashboard</members>
            <name>ApexPage</name>
          </types>"""
    soap_ret = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>{V}</met:apiVersion>
        <met:unpackaged>{pkg_retrieve}</met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(meta_url, data=soap_ret, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "retrieve"
    })
    async_id = ET.fromstring(resp.text).find(
        ".//{http://soap.sforce.com/2006/04/metadata}id"
    ).text

    vf_page = None
    vf_meta = None
    for _ in range(30):
        time.sleep(2)
        check = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus>
      <met:asyncProcessId>{async_id}</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(meta_url, data=check, headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkRetrieveStatus"
        })
        croot = ET.fromstring(cr.text)
        done = croot.find(".//{http://soap.sforce.com/2006/04/metadata}done")
        if done is not None and done.text == "true":
            zb = croot.find(".//{http://soap.sforce.com/2006/04/metadata}zipFile")
            if zb is not None and zb.text:
                zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(zb.text)))
                for name in zf.namelist():
                    if name.endswith(".page") and not name.endswith("-meta.xml"):
                        vf_page = zf.read(name).decode("utf-8")
                    elif name.endswith("-meta.xml") and "page" in name.lower():
                        vf_meta = zf.read(name).decode("utf-8")
            break

    if not vf_page:
        print("  [ERROR] Could not retrieve VF page")
        return

    # Fix: Change the Reports and Dashboards links from target="_top" to target="_blank"
    # These are the link buttons in the header
    old_reports = "html += '<a class=\"link-btn\" href=\"' + lightningUrl + '/lightning/o/Report/home\" target=\"_top\">Reports</a>';"
    new_reports = "html += '<a class=\"link-btn\" href=\"' + lightningUrl + '/lightning/o/Report/home\" target=\"_blank\">Reports</a>';"

    old_dashboards = "html += '<a class=\"link-btn\" href=\"' + lightningUrl + '/lightning/o/Dashboard/home\" target=\"_top\">Dashboards</a>';"
    new_dashboards = "html += '<a class=\"link-btn\" href=\"' + lightningUrl + '/lightning/o/Dashboard/home\" target=\"_blank\">Dashboards</a>';"

    vf_page = vf_page.replace(old_reports, new_reports)
    vf_page = vf_page.replace(old_dashboards, new_dashboards)

    print(f"  Reports link: {'fixed' if new_reports in vf_page else 'NOT FOUND'}")
    print(f"  Dashboards link: {'fixed' if new_dashboards in vf_page else 'NOT FOUND'}")

    pkg2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>InsideSalesDashboard</members>
        <name>ApexPage</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg2)
        zf.writestr("pages/InsideSalesDashboard.page", vf_page)
        zf.writestr("pages/InsideSalesDashboard.page-meta.xml", vf_meta or """<?xml version="1.0" encoding="UTF-8"?>
<ApexPage xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <availableInTouch>true</availableInTouch>
    <confirmationTokenRequired>false</confirmationTokenRequired>
    <label>Inside Sales Dashboard</label>
</ApexPage>""")
    buf2.seek(0)

    deploy_zip(session_id, buf2.read(), "Fix dashboard links to open in new tab")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
