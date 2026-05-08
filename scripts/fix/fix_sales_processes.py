"""
Fix Sales Processes + Add MDU Validation Rule
===============================================
1. Update MDU Sales Process: add Engaged, Contract Negotiations, On Hold; remove Ready for Eng, Under Construction, Activation
2. Update Business Sales Process: add Engaged, Contract Negotiations, On Hold; keep all post-contract stages
3. Add validation rule: MDU opps cannot be set to Closed Won
"""

import requests
import base64
import io
import zipfile
import time
from xml.etree import ElementTree as ET

# Config
USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
META_URL = f"{INSTANCE_URL}/services/Soap/m/59.0"


def soap_login():
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body>
    <urn:login>
      <urn:username>{USERNAME}</urn:username>
      <urn:password>{PASSWORD}{TOKEN}</urn:password>
    </urn:login>
  </soapenv:Body>
</soapenv:Envelope>"""
    resp = requests.post(LOGIN_URL, data=soap_body, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"})
    ns = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "sf": "urn:partner.soap.sforce.com"}
    root = ET.fromstring(resp.text)
    session_id = root.find(".//sf:sessionId", ns).text
    return session_id


def deploy(session_id, zip_bytes):
    b64_zip = base64.b64encode(zip_bytes).decode("utf-8")
    deploy_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{b64_zip}</met:ZipFile>
      <met:DeployOptions>
        <met:rollbackOnError>true</met:rollbackOnError>
        <met:singlePackage>true</met:singlePackage>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

    ns_meta = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
    resp = requests.post(META_URL, data=deploy_body, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
    root = ET.fromstring(resp.text)
    deploy_id = root.find(".//met:id", ns_meta)
    if deploy_id is None:
        print("DEPLOY FAILED - no ID returned")
        print(resp.text[:2000])
        return False

    deploy_id = deploy_id.text
    print(f"Deploy started: {deploy_id}")

    for i in range(15):
        time.sleep(3)
        check_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        resp2 = requests.post(META_URL, data=check_body, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
        root2 = ET.fromstring(resp2.text)
        done = root2.find(".//met:done", ns_meta)
        success = root2.find(".//met:success", ns_meta)
        status = root2.find(".//met:status", ns_meta)

        if done is not None and done.text == "true":
            print(f"Status: {status.text if status is not None else '?'}")
            print(f"Success: {success.text if success is not None else '?'}")

            errors = root2.findall(".//met:componentFailures", ns_meta)
            for err in errors:
                problem = err.find("met:problem", ns_meta)
                comp = err.find("met:fullName", ns_meta)
                print(f"  ERROR: {comp.text if comp is not None else '?'} -- {problem.text if problem is not None else '?'}")

            if not errors and success is not None and success.text == "true":
                print("\nDEPLOYED SUCCESSFULLY")
                return True
            return False
        else:
            print(f"  Polling... ({status.text if status is not None else 'pending'})")

    print("Timed out waiting for deploy")
    return False


def main():
    print("=" * 60)
    print("Fix Sales Processes + MDU Validation Rule")
    print("=" * 60)

    session_id = soap_login()
    print("Logged in\n")

    # MDU Sales Process: Prospecting, Engaged, Contract Negotiations, Under Contract, On Hold, Closed Won, Closed Lost
    # Business Sales Process: all of the above + Ready for Engineering, Under Construction, Activation
    # Validation Rule: MDU cannot use Closed Won

    object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <businessProcesses>
        <fullName>MDU Sales Process</fullName>
        <isActive>true</isActive>
        <values>
            <fullName>Prospecting</fullName>
        </values>
        <values>
            <fullName>Engaged</fullName>
        </values>
        <values>
            <fullName>Contract Negotiations</fullName>
        </values>
        <values>
            <fullName>Under Contract</fullName>
        </values>
        <values>
            <fullName>On Hold</fullName>
        </values>
        <values>
            <fullName>Closed Won</fullName>
        </values>
        <values>
            <fullName>Closed Lost</fullName>
        </values>
    </businessProcesses>
    <businessProcesses>
        <fullName>Business Sales Process</fullName>
        <isActive>true</isActive>
        <values>
            <fullName>Prospecting</fullName>
        </values>
        <values>
            <fullName>Engaged</fullName>
        </values>
        <values>
            <fullName>Contract Negotiations</fullName>
        </values>
        <values>
            <fullName>Under Contract</fullName>
        </values>
        <values>
            <fullName>On Hold</fullName>
        </values>
        <values>
            <fullName>Ready for Engineering</fullName>
        </values>
        <values>
            <fullName>Under Construction</fullName>
        </values>
        <values>
            <fullName>Activation</fullName>
        </values>
        <values>
            <fullName>Closed Won</fullName>
        </values>
        <values>
            <fullName>Closed Lost</fullName>
        </values>
    </businessProcesses>
    <validationRules>
        <fullName>MDU_No_Closed_Won</fullName>
        <active>true</active>
        <description>MDU opportunities cannot be set to Closed Won. The MDU pipeline ends at Under Contract.</description>
        <errorConditionFormula>AND(
    RecordType.DeveloperName = "MDU",
    ISPICKVAL(StageName, "Closed Won")
)</errorConditionFormula>
        <errorDisplayField>StageName</errorDisplayField>
        <errorMessage>MDU opportunities end at Under Contract. Closed Won is only available for Business opportunities.</errorMessage>
    </validationRules>
</CustomObject>"""

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.MDU Sales Process</members>
        <members>Opportunity.Business Sales Process</members>
        <name>BusinessProcess</name>
    </types>
    <types>
        <members>Opportunity.MDU_No_Closed_Won</members>
        <name>ValidationRule</name>
    </types>
    <version>59.0</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("objects/Opportunity.object", object_xml)
        zf.writestr("package.xml", package_xml)

    print("Deploying:")
    print("  - MDU Sales Process: Prospecting, Engaged, Contract Negotiations, Under Contract, On Hold, Closed Won, Closed Lost")
    print("  - Business Sales Process: above + Ready for Engineering, Under Construction, Activation")
    print("  - Validation Rule: MDU_No_Closed_Won (blocks Closed Won for MDU record type)")
    print()

    deploy(session_id, buf.getvalue())


if __name__ == "__main__":
    main()
