"""
Add Resolution_Stage__c picklist field on Campaign and set the 9-25 Campaign's value.

Field:
  - API: Resolution_Stage__c
  - Label: Resolution Stage
  - Type: Picklist (SF Opportunity stages)
  - Description: "Opps at this stage or later are considered resolved for this project."
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
NS = {"met": "http://soap.sforce.com/2006/04/metadata"}

STAGES = [
    "Prospecting", "Engaged", "ROE Secured", "Contract Negotiations",
    "Under Contract", "Ready for Engineering", "Under Construction",
    "Activation", "Closed Won",
]


def soap_login():
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body><urn:login><urn:username>{USERNAME}</urn:username><urn:password>{PASSWORD_TOKEN}</urn:password></urn:login></soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post("https://login.salesforce.com/services/Soap/u/" + API_VERSION, data=body,
                      headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"})
    root = ET.fromstring(r.text)
    sid = root.find(".//{urn:partner.soap.sforce.com}sessionId")
    return sid.text if sid is not None else None


pv_xml = "\n".join(
    f"""            <value>
                <fullName>{s}</fullName>
                <default>false</default>
                <label>{s}</label>
            </value>"""
    for s in STAGES
)

OBJECT_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Resolution_Stage__c</fullName>
        <externalId>false</externalId>
        <label>Resolution Stage</label>
        <inlineHelpText>Opps at this stage or later count as resolved for this project. Blank = Closed Won.</inlineHelpText>
        <description>Opps at this stage or later are considered resolved for this project. Closed Lost is always resolved.</description>
        <required>false</required>
        <trackFeedHistory>false</trackFeedHistory>
        <type>Picklist</type>
        <valueSet>
            <restricted>true</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
{pv_xml}
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

PROFILE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions><editable>true</editable><field>Campaign.Resolution_Stage__c</field><readable>true</readable></fieldPermissions>
</Profile>"""

PACKAGE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Campaign.Resolution_Stage__c</members>
        <name>CustomField</name>
    </types>
    <types>
        <members>Admin</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""


def deploy(sid, files, desc):
    print(f"\n  Deploying: {desc}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION}"
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{b64}</met:ZipFile>
      <met:DeployOptions><met:singlePackage>true</met:singlePackage><met:rollbackOnError>true</met:rollbackOnError></met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(url, data=soap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
    root = ET.fromstring(r.text)
    did = root.find(".//met:id", NS)
    if did is None:
        print("    REQUEST FAIL:", r.text[:500])
        return False
    for _ in range(30):
        time.sleep(2)
        csoap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkDeployStatus><met:asyncProcessId>{did.text}</met:asyncProcessId><met:includeDetails>true</met:includeDetails></met:checkDeployStatus></soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=csoap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
        cr_root = ET.fromstring(cr.text)
        done = cr_root.find(".//met:done", NS)
        if done is not None and done.text == "true":
            ok = cr_root.find(".//met:success", NS)
            if ok is not None and ok.text == "true":
                print("    OK")
                return True
            print("    FAILED details:")
            for el in cr_root.iter():
                t = el.tag.split("}")[-1]
                if t in ("problem", "fullName", "problemType", "componentType", "fileName"):
                    if el.text:
                        print(f"      {t}: {el.text}")
            return False
    print("    timeout")
    return False


def main():
    sid = soap_login()
    if not sid:
        return
    files = {
        "package.xml": PACKAGE_XML,
        "objects/Campaign.object": OBJECT_XML,
        "profiles/Admin.profile": PROFILE_XML,
    }
    deploy(sid, files, "Campaign.Resolution_Stage__c picklist")

    # Stamp the 9-25 Campaign value
    from simple_salesforce import Salesforce
    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Hawaiian1984",
        security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
    )
    sf.Campaign.update("701WR00001IwJYsYAN", {"Resolution_Stage__c": "ROE Secured"})
    print("\nStamped 9-25 MDU ROE Project with Resolution_Stage__c = 'ROE Secured'")


if __name__ == "__main__":
    main()
