"""
Update Lightning App navigation tabs.
- MDU Sales: Home, Tracker, Opportunities, Agreements, Contacts, Accounts, SiteTracker Projects, Reports
- Business Sales: Add Home tab (keep existing tabs)
"""

import requests
import re
import time
import base64
import io
import zipfile
from xml.etree import ElementTree as ET

# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION_NUM = "59.0"


# ── SOAP Login ──────────────────────────────────────────────────────────
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
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "login",
    })

    if resp.status_code != 200:
        print(f"[ERROR] Login failed: {resp.status_code}")
        print(resp.text[:500])
        return None

    root = ET.fromstring(resp.text)
    ns = {"s": "urn:partner.soap.sforce.com"}
    session_id = root.find(".//s:sessionId", ns)
    if session_id is None:
        print("[ERROR] No session ID in response")
        return None

    print(f"[OK] Logged in as {USERNAME}")
    return session_id.text


# ── Metadata Retrieve ───────────────────────────────────────────────────
def retrieve_metadata(session_id, package_inner):
    metadata_url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}"
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>{API_VERSION_NUM}</met:apiVersion>
        <met:unpackaged>{package_inner}
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(metadata_url, data=soap, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "retrieve",
    })

    if resp.status_code != 200:
        print(f"[ERROR] Retrieve request failed: {resp.status_code}")
        return None

    root = ET.fromstring(resp.text)
    async_id = root.find(".//{http://soap.sforce.com/2006/04/metadata}id")
    if async_id is None:
        print("[ERROR] No async ID in retrieve response")
        return None

    # Poll for completion
    for _ in range(30):
        time.sleep(2)
        check_soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus>
      <met:asyncProcessId>{async_id.text}</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        check_resp = requests.post(metadata_url, data=check_soap, headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "checkRetrieveStatus",
        })
        check_root = ET.fromstring(check_resp.text)
        done_el = check_root.find(".//{http://soap.sforce.com/2006/04/metadata}done")
        if done_el is not None and done_el.text == "true":
            zip_el = check_root.find(".//{http://soap.sforce.com/2006/04/metadata}zipFile")
            if zip_el is not None and zip_el.text:
                return base64.b64decode(zip_el.text)
            return None

    print("[ERROR] Retrieve timed out")
    return None


# ── Metadata Deploy ─────────────────────────────────────────────────────
def deploy_metadata_package(session_id, files_dict, description):
    print(f"\n  Deploying: {description}")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files_dict.items():
            zf.writestr(filename, content)
    zip_buffer.seek(0)
    zip_b64 = base64.b64encode(zip_buffer.read()).decode("utf-8")

    metadata_url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}"
    deploy_soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{zip_b64}</met:ZipFile>
      <met:DeployOptions>
        <met:singlePackage>true</met:singlePackage>
        <met:rollbackOnError>true</met:rollbackOnError>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(metadata_url, data=deploy_soap, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "deploy",
    })

    if resp.status_code != 200:
        print(f"  [ERROR] Deploy request failed: {resp.status_code}")
        print(f"  {resp.text[:500]}")
        return False

    root = ET.fromstring(resp.text)
    deploy_id = root.find(".//{http://soap.sforce.com/2006/04/metadata}id")
    if deploy_id is None:
        print("  [ERROR] No deploy ID returned")
        return False

    print(f"  Deploy ID: {deploy_id.text}")
    print("  Waiting for deployment...")

    for attempt in range(30):
        time.sleep(2)
        check_soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id.text}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""

        check_resp = requests.post(metadata_url, data=check_soap, headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "checkDeployStatus",
        })
        check_root = ET.fromstring(check_resp.text)
        ns = {"met": "http://soap.sforce.com/2006/04/metadata"}

        done = check_root.find(".//{http://soap.sforce.com/2006/04/metadata}done")
        if done is not None and done.text == "true":
            success = check_root.find(".//{http://soap.sforce.com/2006/04/metadata}success")
            if success is not None and success.text == "true":
                print(f"  [OK] {description} deployed successfully!")
                return True
            else:
                print(f"  [ERROR] Deploy failed!")
                # Print error details
                for msg in check_root.iter():
                    if "problem" in (msg.tag.split("}")[-1] if "}" in msg.tag else msg.tag).lower():
                        print(f"    {msg.text}")
                return False

    print("  [ERROR] Deploy timed out")
    return False


# ── Build Tab XML ───────────────────────────────────────────────────────
def build_tab_xml(flexipage, label, motif="Custom70: Desk"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">
    <flexiPage>{flexipage}</flexiPage>
    <label>{label}</label>
    <motif>{motif}</motif>
</CustomTab>"""


# ── Build App XML ───────────────────────────────────────────────────────
def build_app_xml(label, tabs):
    tabs_xml = "\n".join(f"    <tabs>{t}</tabs>" for t in tabs)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>{label}</label>
    <formFactors>Large</formFactors>
    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>
    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>
    <isNavTabPersistenceDisabled>false</isNavTabPersistenceDisabled>
    <navType>Standard</navType>
    <uiType>Lightning</uiType>
    {tabs_xml}
</CustomApplication>"""


# ── Retrieve current app tabs ───────────────────────────────────────────
def get_current_tabs(session_id, app_name):
    package_inner = f"""
          <types>
            <members>{app_name}</members>
            <name>CustomApplication</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)
    if not zip_bytes:
        return None

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    for name in zf.namelist():
        if name.endswith(".app"):
            content = zf.read(name).decode("utf-8")
            return re.findall(r"<tabs>([^<]+)</tabs>", content)
    return None


# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("UPDATE LIGHTNING APP NAVIGATION")
    print("=" * 70)

    session_id = soap_login()
    if not session_id:
        return

    # ── Step 1: Retrieve current tabs for both apps ─────────────────
    print("\n--- Retrieving current MDU_Sales tabs ---")
    mdu_current = get_current_tabs(session_id, "MDU_Sales")
    if mdu_current:
        print(f"  Current MDU_Sales tabs: {mdu_current}")
    else:
        print("  Could not retrieve MDU_Sales tabs (will deploy from scratch)")

    print("\n--- Retrieving current Business_Sales tabs ---")
    biz_current = get_current_tabs(session_id, "Business_Sales")
    if biz_current:
        print(f"  Current Business_Sales tabs: {biz_current}")
    else:
        print("  Could not retrieve Business_Sales tabs")

    # ── Step 2: Deploy MDU_Sales with new tab order ─────────────────
    print("\n" + "=" * 70)
    print("UPDATING MDU SALES APP")
    print("=" * 70)

    mdu_tabs = [
        "standard-home",
        "MDU_Tracker",
        "standard-Opportunity",
        "Agreement__c",
        "standard-Contact",
        "standard-Account",
        "SiteTracker_Project__c",
        "standard-report",
    ]

    print(f"\n  New MDU_Sales tab order:")
    for i, t in enumerate(mdu_tabs, 1):
        print(f"    {i}. {t}")

    mdu_xml = build_app_xml("MDU Sales", mdu_tabs)
    mdu_tab_xml = build_tab_xml("MDU_Tracker", "MDU Tracker")
    mdu_package = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales</members>
        <name>CustomApplication</name>
    </types>
    <types>
        <members>MDU_Tracker</members>
        <name>CustomTab</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    mdu_ok = deploy_metadata_package(session_id, {
        "package.xml": mdu_package,
        "applications/MDU_Sales.app": mdu_xml,
        "tabs/MDU_Tracker.tab": mdu_tab_xml,
    }, "MDU Sales — new tab order + rename Tracker to MDU Tracker")

    # ── Step 3: Deploy Business_Sales with new tab order ────────────
    print("\n" + "=" * 70)
    print("UPDATING BUSINESS SALES APP")
    print("=" * 70)

    biz_tabs = [
        "standard-home",
        "Business_Tracker",
        "Property_Location__c",
        "Property_Unit__c",
        "standard-Opportunity",
        "Agreement__c",
        "standard-Contact",
        "standard-report",
    ]

    print(f"\n  New Business_Sales tab order:")
    for i, t in enumerate(biz_tabs, 1):
        print(f"    {i}. {t}")

    biz_xml = build_app_xml("Business Sales", biz_tabs)
    biz_tab_xml = build_tab_xml("Business_Tracker", "BUS Tracker")
    biz_package = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Business_Sales</members>
        <name>CustomApplication</name>
    </types>
    <types>
        <members>Business_Tracker</members>
        <name>CustomTab</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    biz_ok = deploy_metadata_package(session_id, {
        "package.xml": biz_package,
        "applications/Business_Sales.app": biz_xml,
        "tabs/Business_Tracker.tab": biz_tab_xml,
    }, "Business Sales — new tab order + rename Tracker to BUS Tracker")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"  MDU Sales:      {'Updated' if mdu_ok else 'FAILED — check errors above'}")
    print(f"  Business Sales: {'Updated' if biz_ok else 'FAILED — check errors above'}")


if __name__ == "__main__":
    main()
