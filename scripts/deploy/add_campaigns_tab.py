"""
Add the Campaigns tab to MDU Sales and Business Sales apps.

Retrieves each app's current tab list, inserts `standard-Campaign` right after
Opportunities, and deploys the updated CustomApplication metadata.

Idempotent: skips if Campaign tab already present.
"""

import requests
import base64
import io
import time
import zipfile
from xml.etree import ElementTree as ET

USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Hawaiian1984IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

MDU_TABS = [
    "standard-home",
    "MDU_Tracker",
    "standard-Opportunity",
    "standard-Campaign",   # NEW
    "Agreement__c",
    "standard-Contact",
    "standard-Account",
    "SiteTracker_Project__c",
    "IronClad__c",
]

BIZ_TABS = [
    "standard-home",
    "Business_Tracker",
    "Property_Location__c",
    "Property_Unit__c",
    "standard-Opportunity",
    "standard-Campaign",   # NEW
    "Agreement__c",
    "standard-Contact",
]

NS_META = {"met": "http://soap.sforce.com/2006/04/metadata"}


def soap_login():
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body>
    <urn:login>
      <urn:username>{USERNAME}</urn:username>
      <urn:password>{PASSWORD_TOKEN}</urn:password>
    </urn:login>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(
        "https://login.salesforce.com/services/Soap/u/" + API_VERSION,
        data=body,
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"},
    )
    root = ET.fromstring(r.text)
    sid = root.find(".//{urn:partner.soap.sforce.com}sessionId")
    if sid is None:
        print("LOGIN FAILED:", r.text[:600])
        return None
    return sid.text


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


def deploy(session_id, files, description):
    print(f"\n  Deploying: {description}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    zip_b64 = base64.b64encode(buf.read()).decode("utf-8")

    url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION}"
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
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
    r = requests.post(url, data=soap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
    root = ET.fromstring(r.text)
    did = root.find(".//met:id", NS_META)
    if did is None:
        print("    DEPLOY REQUEST FAIL:", r.text[:600])
        return False
    print(f"    Deploy id: {did.text}")
    for _ in range(30):
        time.sleep(2)
        csoap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{did.text}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=csoap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
        cr_root = ET.fromstring(cr.text)
        done = cr_root.find(".//met:done", NS_META)
        if done is not None and done.text == "true":
            success = cr_root.find(".//met:success", NS_META)
            if success is not None and success.text == "true":
                print("    OK")
                return True
            print("    FAILED. Details:")
            for el in cr_root.iter():
                tag = el.tag.split("}")[-1]
                if tag in ("problem", "problemType", "fullName", "fileName", "componentType"):
                    if el.text:
                        print(f"      {tag}: {el.text}")
            return False
    print("    TIMEOUT")
    return False


def main():
    print("Adding Campaigns tab to MDU Sales + Business Sales apps")
    sid = soap_login()
    if not sid:
        return

    # MDU_Sales
    deploy(sid, {
        "package.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>MDU_Sales</members><name>CustomApplication</name></types>
    <version>{API_VERSION}</version>
</Package>""",
        "applications/MDU_Sales.app": build_app_xml("MDU Sales", MDU_TABS),
    }, "MDU Sales — add Campaigns tab")

    # Inside_Sales  (API name) / Business Sales (label)
    deploy(sid, {
        "package.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Inside_Sales</members><name>CustomApplication</name></types>
    <version>{API_VERSION}</version>
</Package>""",
        "applications/Inside_Sales.app": build_app_xml("Business Sales", BIZ_TABS),
    }, "Business Sales (Inside_Sales) — add Campaigns tab")


if __name__ == "__main__":
    main()
