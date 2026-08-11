"""
Fix Opportunity Stage picklist in Salesforce.
Removes post-sale stages (Engineering, Construction, Activation) that
don't belong in the sales pipeline. Deploys via Metadata API ZIP package.
"""

import requests
import time
import base64
import io
import zipfile
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = _SF["username"]
PASSWORD_TOKEN = (_SF["password"] + _SF["token"])
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "v59.0"
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

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "login",
    }

    print("=" * 60)
    print("AUTHENTICATING")
    print("=" * 60)
    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)

    if resp.status_code != 200:
        print(f"SOAP login failed ({resp.status_code}):")
        print(resp.text[:2000])
        return None

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "sf": "urn:partner.soap.sforce.com",
    }
    root = ET.fromstring(resp.text)
    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        print("SOAP Fault:", ET.tostring(fault, encoding="unicode"))
        return None

    session_id = root.find(".//sf:sessionId", ns)
    if session_id is None:
        print("Could not find sessionId in response.")
        return None

    print("Authenticated successfully.")
    return session_id.text


# ── Deploy Metadata Package ────────────────────────────────────────────
def deploy_metadata_package(session_id, files_dict, description):
    """Deploy a metadata package via the Metadata SOAP API."""
    print(f"\n  Deploying: {description}")

    # Build ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files_dict.items():
            zf.writestr(filename, content)
    zip_buffer.seek(0)
    zip_b64 = base64.b64encode(zip_buffer.read()).decode("utf-8")

    # SOAP deploy call
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
        <met:allowMissingFiles>false</met:allowMissingFiles>
        <met:autoUpdatePackage>true</met:autoUpdatePackage>
        <met:checkOnly>false</met:checkOnly>
        <met:ignoreWarnings>true</met:ignoreWarnings>
        <met:performRetrieve>false</met:performRetrieve>
        <met:purgeOnDelete>false</met:purgeOnDelete>
        <met:rollbackOnError>true</met:rollbackOnError>
        <met:singlePackage>true</met:singlePackage>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "deploy",
    }

    resp = requests.post(metadata_url, data=deploy_soap, headers=headers)

    if resp.status_code != 200:
        print(f"  Deploy request failed ({resp.status_code}):")
        print(f"  {resp.text[:1000]}")
        return False

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }
    root = ET.fromstring(resp.text)

    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        fault_str = ET.tostring(fault, encoding="unicode")
        print(f"  SOAP Fault: {fault_str[:500]}")
        return False

    deploy_id_el = root.find(".//met:id", ns)
    if deploy_id_el is None:
        print("  Could not find deploy ID in response.")
        print(f"  Response: {resp.text[:1000]}")
        return False

    deploy_id = deploy_id_el.text
    print(f"  Deploy ID: {deploy_id}")

    return poll_deploy_status(session_id, deploy_id, description)


def poll_deploy_status(session_id, deploy_id, description):
    """Poll Metadata API for deploy status until complete."""
    metadata_url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}"
    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }

    for attempt in range(30):
        time.sleep(3)

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
      <met:asyncProcessId>{deploy_id}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "checkDeployStatus",
        }

        resp = requests.post(metadata_url, data=check_soap, headers=headers)
        if resp.status_code != 200:
            print(f"  Status check failed ({resp.status_code})")
            continue

        root = ET.fromstring(resp.text)

        done_el = root.find(".//met:done", ns)
        status_el = root.find(".//met:status", ns)
        success_el = root.find(".//met:success", ns)

        done = done_el.text if done_el is not None else "unknown"
        status = status_el.text if status_el is not None else "unknown"

        print(f"  Polling... status={status}, done={done}")

        if done == "true":
            success = success_el.text if success_el is not None else "unknown"
            if success == "true":
                print(f"  SUCCESS: {description} deployed!")
                return True
            else:
                print(f"  FAILED: {description} deployment failed.")
                for fail_el in root.iter():
                    tag = fail_el.tag.split("}")[-1] if "}" in fail_el.tag else fail_el.tag
                    if tag == "componentFailures":
                        for child in fail_el:
                            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                            if child.text:
                                print(f"    {ctag}: {child.text}")
                    if "problem" in tag.lower() or "message" in tag.lower():
                        if fail_el.text:
                            print(f"    {tag}: {fail_el.text}")
                return False

    print(f"  TIMEOUT: Deploy did not complete within 90 seconds.")
    return False


# ── Verify Stages ──────────────────────────────────────────────────────
def verify_stages(session_id):
    """Verify the stages via REST describe."""
    print("\n" + "=" * 60)
    print("VERIFYING OPPORTUNITY STAGES")
    print("=" * 60)

    url = f"{INSTANCE_URL}/services/data/{API_VERSION}/sobjects/Opportunity/describe/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        print(f"  Describe failed ({resp.status_code})")
        return

    fields = resp.json().get("fields", [])
    stage_field = next((f for f in fields if f["name"] == "StageName"), None)

    if stage_field is None:
        print("  Could not find StageName field.")
        return

    print(f"\n  Current stages in Salesforce:")
    for pv in stage_field.get("picklistValues", []):
        active = "ACTIVE" if pv.get("active") else "inactive"
        print(f"    {pv['label']:20s}  [{active}]")


# ── Main ───────────────────────────────────────────────────────────────
def main():
    session_id = soap_login()
    if not session_id:
        print("\nFailed to authenticate. Exiting.")
        return

    # Build the metadata package with only the 5 desired stages
    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpportunityStage</members>
        <name>StandardValueSet</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    stage_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<StandardValueSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <sorted>false</sorted>
    <standardValue>
        <fullName>Prospecting</fullName>
        <default>true</default>
        <label>Prospecting</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>10</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Qualification</fullName>
        <default>false</default>
        <label>Qualification</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>25</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Negotiation</fullName>
        <default>false</default>
        <label>Negotiation</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>50</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Closed Won</fullName>
        <default>false</default>
        <label>Closed Won</label>
        <closed>true</closed>
        <forecastCategory>Closed</forecastCategory>
        <probability>100</probability>
        <won>true</won>
    </standardValue>
    <standardValue>
        <fullName>Closed Lost</fullName>
        <default>false</default>
        <label>Closed Lost</label>
        <closed>true</closed>
        <forecastCategory>Omitted</forecastCategory>
        <probability>0</probability>
        <won>false</won>
    </standardValue>
</StandardValueSet>"""

    print("\n" + "=" * 60)
    print("UPDATING OPPORTUNITY STAGE PICKLIST")
    print("  Keeping: Prospecting, Qualification, Negotiation,")
    print("           Closed Won, Closed Lost")
    print("  Removing: Engineering, Construction, Activation")
    print("=" * 60)

    success = deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "standardValueSets/OpportunityStage.standardValueSet": stage_xml,
    }, "Opportunity Stage picklist update")

    if success:
        verify_stages(session_id)
    else:
        print("\nDeploy failed. Check errors above.")

    print("\nDone.")


if __name__ == "__main__":
    main()
