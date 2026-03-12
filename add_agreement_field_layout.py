"""
Add Agreement_Name__c field to the Opportunity page layout.

Retrieves the current Opportunity Layout via Metadata API,
adds Agreement_Name__c to the "Opportunity Information" section
(right column, near the top), then deploys the updated layout.
"""

import requests
import json
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
API_VERSION = "v59.0"
API_VERSION_NUM = "59.0"

MD_NS = "http://soap.sforce.com/2006/04/metadata"
FIELD_TO_ADD = "Agreement_Name__c"


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

    print("=" * 70)
    print("AUTHENTICATING")
    print("=" * 70)
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


# ── Metadata API Retrieve ──────────────────────────────────────────────
def retrieve_metadata(session_id, package_inner):
    """Retrieve metadata via SOAP Metadata API. Returns ZIP bytes or None."""
    metadata_url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}"
    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }

    retrieve_soap = f"""<?xml version="1.0" encoding="utf-8"?>
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
        <met:unpackaged>
          {package_inner}
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "retrieve",
    }

    resp = requests.post(metadata_url, data=retrieve_soap, headers=headers)
    if resp.status_code != 200:
        print(f"  Retrieve request failed ({resp.status_code})")
        print(f"  {resp.text[:1000]}")
        return None

    root = ET.fromstring(resp.text)
    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        print(f"  SOAP Fault: {ET.tostring(fault, encoding='unicode')[:500]}")
        return None

    retrieve_id_el = root.find(".//met:id", ns)
    if retrieve_id_el is None:
        print("  Could not find retrieve ID")
        return None

    retrieve_id = retrieve_id_el.text
    print(f"  Retrieve ID: {retrieve_id}")

    # Poll for completion
    for attempt in range(20):
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
    <met:checkRetrieveStatus>
      <met:asyncProcessId>{retrieve_id}</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""

        resp = requests.post(metadata_url, data=check_soap, headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "checkRetrieveStatus",
        })

        if resp.status_code != 200:
            continue

        root = ET.fromstring(resp.text)
        done_el = root.find(".//met:done", ns)
        if done_el is not None and done_el.text == "true":
            success_el = root.find(".//met:success", ns)
            if success_el is not None and success_el.text == "true":
                zip_el = root.find(".//met:zipFile", ns)
                if zip_el is not None and zip_el.text:
                    print("  Retrieve completed successfully.")
                    return base64.b64decode(zip_el.text)
            else:
                for msg_el in root.iter():
                    tag = msg_el.tag.split("}")[-1] if "}" in msg_el.tag else msg_el.tag
                    if tag in ("problem", "message") and msg_el.text:
                        print(f"  Retrieve error: {msg_el.text}")
                return None

        status_el = root.find(".//met:status", ns)
        status = status_el.text if status_el is not None else "unknown"
        print(f"  Retrieve polling... status={status}")

    print("  Retrieve timed out.")
    return None


# ── Metadata API Deploy ────────────────────────────────────────────────
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
        print(f"  SOAP Fault: {ET.tostring(fault, encoding='unicode')[:500]}")
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
                print(f"  SUCCESS: {description} deployed successfully!")
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
                return False

    print(f"  TIMEOUT: Deploy did not complete within 90 seconds.")
    return False


# ── Main Logic ─────────────────────────────────────────────────────────
def add_agreement_field(session_id):
    print("\n" + "=" * 70)
    print(f"ADD {FIELD_TO_ADD} TO OPPORTUNITY LAYOUT")
    print("=" * 70)

    # Step 1: Retrieve the current Opportunity Layout
    print("\n  Step 1: Retrieving current Opportunity Layout...")
    package_inner = """
          <types>
            <members>Opportunity-Opportunity Layout</members>
            <name>Layout</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)

    if not zip_bytes:
        print("\n  ERROR: Could not retrieve layout. Aborting.")
        return False

    # Step 2: Parse the retrieved layout
    print("\n  Step 2: Parsing retrieved layout...")
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    layout_xml = None
    layout_filename = None

    for name in zf.namelist():
        print(f"    ZIP entry: {name}")
        if "layout" in name.lower() and name.endswith(".layout"):
            layout_filename = name
            layout_xml = zf.read(name).decode("utf-8")

    if not layout_xml:
        print("  ERROR: Could not find layout file in retrieved ZIP.")
        return False

    print(f"  Found layout: {layout_filename}")
    print(f"  Layout XML length: {len(layout_xml)} chars")

    ET.register_namespace("", MD_NS)
    root = ET.fromstring(layout_xml)

    # Check if Agreement_Name__c is already on the layout
    already_present = False
    for field_el in root.iter(f"{{{MD_NS}}}field"):
        if field_el.text == FIELD_TO_ADD:
            already_present = True
            break

    if already_present:
        print(f"\n  {FIELD_TO_ADD} is already on the layout. Nothing to do!")
        return True

    # Step 3: Find the "Opportunity Information" section and add the field
    print(f"\n  Step 3: Adding {FIELD_TO_ADD} to Opportunity Information section...")

    all_sections = list(root.findall(f"{{{MD_NS}}}layoutSections"))
    target_section = None

    for i, sec in enumerate(all_sections):
        label_el = sec.find(f"{{{MD_NS}}}label")
        label_text = label_el.text if label_el is not None else "(none)"
        style_el = sec.find(f"{{{MD_NS}}}style")
        style_text = style_el.text if style_el is not None else "(none)"
        print(f"    Section {i}: label='{label_text}', style='{style_text}'")

        # The main "Opportunity Information" section is typically the first section.
        # It may have label "Opportunity Information" or sometimes no custom label
        # (the standard first section). We look for it by label first.
        if label_text == "Opportunity Information":
            target_section = sec
            print(f"    -> Found target section at index {i}")

    # If not found by exact label, use the first section (which is the main info section)
    if target_section is None and all_sections:
        # The first section in Salesforce layouts is the main detail section
        first_label = all_sections[0].find(f"{{{MD_NS}}}label")
        first_label_text = first_label.text if first_label is not None else "(none)"
        print(f"\n  'Opportunity Information' label not found. Using first section (label='{first_label_text}').")
        target_section = all_sections[0]

    if target_section is None:
        print("  ERROR: No sections found in layout.")
        return False

    # Find the right column (second layoutColumns element) in the target section
    columns = list(target_section.findall(f"{{{MD_NS}}}layoutColumns"))
    print(f"  Target section has {len(columns)} column(s)")

    if len(columns) >= 2:
        # Add to the right column (index 1), near the top
        right_col = columns[1]
        existing_items = list(right_col.findall(f"{{{MD_NS}}}layoutItems"))
        print(f"  Right column has {len(existing_items)} existing items")

        # Create the new layoutItem
        new_item = ET.Element(f"{{{MD_NS}}}layoutItems")
        behavior = ET.SubElement(new_item, f"{{{MD_NS}}}behavior")
        behavior.text = "Edit"
        field = ET.SubElement(new_item, f"{{{MD_NS}}}field")
        field.text = FIELD_TO_ADD

        # Insert at position 0 (top of right column) for visibility
        right_col.insert(0, new_item)
        print(f"  Inserted {FIELD_TO_ADD} at top of right column")
    elif len(columns) == 1:
        # Single column - add near the top
        col = columns[0]
        new_item = ET.Element(f"{{{MD_NS}}}layoutItems")
        behavior = ET.SubElement(new_item, f"{{{MD_NS}}}behavior")
        behavior.text = "Edit"
        field = ET.SubElement(new_item, f"{{{MD_NS}}}field")
        field.text = FIELD_TO_ADD
        col.insert(0, new_item)
        print(f"  Inserted {FIELD_TO_ADD} at top of single column")
    else:
        print("  ERROR: No columns found in target section.")
        return False

    # Step 4: Serialize and deploy
    print("\n  Step 4: Deploying updated layout...")
    new_layout_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity-Opportunity Layout</members>
        <name>Layout</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "layouts/Opportunity-Opportunity Layout.layout": new_layout_xml,
    }, f"Add {FIELD_TO_ADD} to Opportunity Layout")


# ── Entry Point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("\nFailed to authenticate. Exiting.")
        exit(1)

    success = add_agreement_field(session_id)

    print("\n" + "=" * 70)
    if success:
        print("DONE - Agreement_Name__c added to Opportunity Layout successfully!")
    else:
        print("FAILED - Could not add Agreement_Name__c to layout.")
    print("=" * 70)
