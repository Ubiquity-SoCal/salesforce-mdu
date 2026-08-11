"""Deploy updated InsideSalesDashboard with pipeline slicer."""

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

    # Read the new VF page
    import os
    page_path = os.path.join("C:", os.sep, "Users", "cass", "Work_Projects",
                              "SalesForce", "InsideSalesDashboard_new.page")
    with open(page_path, "r", encoding="utf-8") as f:
        vf_page = f.read()

    print(f"  Page size: {len(vf_page)} chars")

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
<ApexPage xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <availableInTouch>true</availableInTouch>
    <confirmationTokenRequired>false</confirmationTokenRequired>
    <label>Inside Sales Dashboard</label>
</ApexPage>"""

    pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>InsideSalesDashboard</members>
        <name>ApexPage</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg_xml)
        zf.writestr("pages/InsideSalesDashboard.page", vf_page)
        zf.writestr("pages/InsideSalesDashboard.page-meta.xml", meta_xml)
    buf.seek(0)

    deploy_zip(session_id, buf.read(), "Dashboard with pipeline slicer")


if __name__ == "__main__":
    main()
