"""
Setup Opportunity Page Layout and List Views for MDU Sales app.

Task 1: Update Opportunity Layout - add Property Details, ISP Information,
         and Migration Reference sections with custom fields.
Task 2: Create 5 list views for Opportunities.
Task 3: Check if Path can be enabled via API.

Uses Metadata API deploy (ZIP) for layout and list views.
"""

import requests
import json
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


# ── REST helpers ────────────────────────────────────────────────────────
def rest_get(session_id, path):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    return requests.get(url, headers=headers)


def rest_post(session_id, path, data):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {
        "Authorization": f"Bearer {session_id}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return requests.post(url, headers=headers, json=data)


# ── Metadata API Deploy Helper ──────────────────────────────────────────
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

    # Parse deploy ID
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


# ── Metadata API Retrieve Helper ────────────────────────────────────────
def retrieve_metadata(session_id, package_xml_content):
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
          {package_xml_content}
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

    # Poll for retrieve completion
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
                # Check for errors
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


# ══════════════════════════════════════════════════════════════════════════
# TASK 1: Retrieve current layout, add new sections, redeploy
# ══════════════════════════════════════════════════════════════════════════
def update_opportunity_layout(session_id):
    print("\n" + "=" * 70)
    print("TASK 1: UPDATE OPPORTUNITY PAGE LAYOUT")
    print("=" * 70)

    # Step 1: Retrieve the current Opportunity Layout
    print("\n  Step 1: Retrieving current Opportunity Layout...")
    package_inner = """
          <types>
            <members>Opportunity-Opportunity Layout</members>
            <name>Layout</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)

    if zip_bytes:
        return update_layout_from_retrieved(session_id, zip_bytes)
    else:
        print("\n  Retrieve failed. Using REST describe to reconstruct layout...")
        return update_layout_from_describe(session_id)


def update_layout_from_retrieved(session_id, zip_bytes):
    """Parse retrieved layout XML, add new sections, redeploy."""
    print("\n  Parsing retrieved layout...")

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    layout_xml = None
    layout_filename = None

    for name in zf.namelist():
        print(f"    ZIP entry: {name}")
        if "layout" in name.lower() and name.endswith(".layout"):
            layout_filename = name
            layout_xml = zf.read(name).decode("utf-8")

    if not layout_xml:
        print("  Could not find layout file in retrieved ZIP.")
        return update_layout_from_describe(session_id)

    print(f"  Found layout: {layout_filename}")
    print(f"  Layout XML length: {len(layout_xml)} chars")

    # Parse the XML and insert new sections
    # We need to be careful with namespaces
    MD_NS = "http://soap.sforce.com/2006/04/metadata"
    ET.register_namespace("", MD_NS)

    root = ET.fromstring(layout_xml)

    # Check if our sections already exist
    existing_sections = []
    for section in root.findall(f".//{{{MD_NS}}}layoutSections/{{{MD_NS}}}label", ):
        pass
    for section in root.iter(f"{{{MD_NS}}}layoutSections"):
        label_el = section.find(f"{{{MD_NS}}}label")
        if label_el is not None:
            existing_sections.append(label_el.text)

    print(f"  Existing sections: {existing_sections}")

    if "Property Details" in existing_sections:
        print("  'Property Details' section already exists. Skipping layout update.")
        return True

    # Build new sections as XML elements
    def make_section(label, fields_left, fields_right, columns=2):
        """Create a layoutSections element with 2-column layout.
        Salesforce expects exactly N layoutColumns elements (N = number of columns),
        each containing all layoutItems for that column."""
        section = ET.Element(f"{{{MD_NS}}}layoutSections")

        custom_label = ET.SubElement(section, f"{{{MD_NS}}}customLabel")
        custom_label.text = "true"
        detail_heading = ET.SubElement(section, f"{{{MD_NS}}}detailHeading")
        detail_heading.text = "true"
        edit_heading = ET.SubElement(section, f"{{{MD_NS}}}editHeading")
        edit_heading.text = "true"
        label_el = ET.SubElement(section, f"{{{MD_NS}}}label")
        label_el.text = label

        if columns == 2:
            style = ET.SubElement(section, f"{{{MD_NS}}}style")
            style.text = "TwoColumnsLeftToRight"

            # Left column - one layoutColumns element with all left fields
            col_left = ET.SubElement(section, f"{{{MD_NS}}}layoutColumns")
            for f_name in fields_left:
                li = ET.SubElement(col_left, f"{{{MD_NS}}}layoutItems")
                behavior = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                behavior.text = "Edit"
                field = ET.SubElement(li, f"{{{MD_NS}}}field")
                field.text = f_name

            # Right column - one layoutColumns element with all right fields
            col_right = ET.SubElement(section, f"{{{MD_NS}}}layoutColumns")
            for f_name in fields_right:
                li = ET.SubElement(col_right, f"{{{MD_NS}}}layoutItems")
                behavior = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                behavior.text = "Edit"
                field = ET.SubElement(li, f"{{{MD_NS}}}field")
                field.text = f_name
        else:
            style = ET.SubElement(section, f"{{{MD_NS}}}style")
            style.text = "OneColumn"
            col = ET.SubElement(section, f"{{{MD_NS}}}layoutColumns")
            for f_name in fields_left:
                li = ET.SubElement(col, f"{{{MD_NS}}}layoutItems")
                behavior = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                behavior.text = "Edit"
                field = ET.SubElement(li, f"{{{MD_NS}}}field")
                field.text = f_name

        return section

    # The Salesforce layout XML has layoutSections in order.
    # We need to insert our new sections after the existing field sections
    # but before related lists / buttons sections.
    # Strategy: find all layoutSections, insert before the last few
    # (typically related lists come at the end).

    all_sections = list(root.findall(f"{{{MD_NS}}}layoutSections"))
    print(f"  Total sections in layout: {len(all_sections)}")

    # Find insertion point - we want to add after the main field sections.
    # Related list sections typically don't have a label or have style="CustomLinks".
    # We'll insert before the last section that has no label (the related list section).

    # Actually, the cleanest approach: insert right before the related lists
    # or custom links section, which is usually the last layoutSections.
    # Let's find the index of the last standard field section.

    # First, let's look at what we have
    insert_before_idx = len(all_sections)  # default: append at end
    for i, sec in enumerate(all_sections):
        label_el = sec.find(f"{{{MD_NS}}}label")
        label_text = label_el.text if label_el is not None else "(none)"
        style_el = sec.find(f"{{{MD_NS}}}style")
        style_text = style_el.text if style_el is not None else "(none)"
        print(f"    Section {i}: label='{label_text}', style='{style_text}'")

        # Custom Links or System Information sections - insert before these
        if label_text in ("Custom Links", "System Information"):
            if insert_before_idx == len(all_sections):
                insert_before_idx = i

    print(f"  Will insert new sections at index {insert_before_idx}")

    # Create the new sections
    property_details = make_section(
        "Property Details",
        ["Units__c", "Property_Type__c", "Property_Category__c", "Build_Type__c"],
        ["Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"],
    )

    isp_info = make_section(
        "ISP Information",
        ["Prospective_ISP__c"],
        ["Confirmed_ISP__c"],
    )

    migration_ref = make_section(
        "Migration Reference",
        ["Monday_Item_ID__c"],
        [],
        columns=1,
    )

    # Insert into the XML tree
    # Find the position in root's children
    root_children = list(root)
    section_positions = []
    for i, child in enumerate(root_children):
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "layoutSections":
            section_positions.append(i)

    if section_positions and insert_before_idx < len(section_positions):
        insert_pos = section_positions[insert_before_idx]
    else:
        insert_pos = len(root_children)

    # Insert in reverse order so positions don't shift
    root.insert(insert_pos, migration_ref)
    root.insert(insert_pos, isp_info)
    root.insert(insert_pos, property_details)

    # Serialize back to XML
    new_layout_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    # Deploy
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
    }, "Opportunity Layout with new sections")


def update_layout_from_describe(session_id):
    """Fallback: build layout XML from REST describe + add new sections."""
    print("\n  Building layout from Opportunity describe...")

    resp = rest_get(session_id, "/sobjects/Opportunity/describe/")
    if resp.status_code != 200:
        print(f"  Describe failed: {resp.status_code}")
        return fallback_field_level_security(session_id)

    describe = resp.json()
    fields = describe.get("fields", [])
    field_map = {f["name"]: f for f in fields}

    # Get the layout describe for the actual current layout
    layout_resp = rest_get(session_id, "/sobjects/Opportunity/describe/layouts")
    if layout_resp.status_code != 200:
        print(f"  Layout describe failed: {layout_resp.status_code}")
        return fallback_field_level_security(session_id)

    layout_data = layout_resp.json()

    # The layout describe gives us the detail layout sections
    # We'll reconstruct the layout XML from this
    records = layout_data.get("layouts", layout_data.get("records", []))
    if not records:
        # Try direct
        if "detailLayoutSections" in layout_data:
            records = [layout_data]
        else:
            print("  No layout records found in describe.")
            print(f"  Keys: {list(layout_data.keys())[:10]}")
            return fallback_field_level_security(session_id)

    layout = records[0] if isinstance(records, list) else records
    detail_sections = layout.get("detailLayoutSections", [])

    if not detail_sections:
        print("  No detail sections found.")
        return fallback_field_level_security(session_id)

    print(f"  Found {len(detail_sections)} layout sections in describe.")

    MD_NS = "http://soap.sforce.com/2006/04/metadata"
    ET.register_namespace("", MD_NS)

    root = ET.Element(f"{{{MD_NS}}}Layout")

    # Reconstruct sections from describe
    for sec in detail_sections:
        section_el = ET.SubElement(root, f"{{{MD_NS}}}layoutSections")

        heading = sec.get("heading", "")
        use_heading = sec.get("useHeading", False)
        columns_count = sec.get("columns", 2)
        rows = sec.get("rows", 1)

        if use_heading and heading:
            custom_label = ET.SubElement(section_el, f"{{{MD_NS}}}customLabel")
            custom_label.text = "true" if heading not in ("Opportunity Information", "Additional Information",
                                                            "Description Information", "System Information",
                                                            "Other Information") else "false"
            detail_heading = ET.SubElement(section_el, f"{{{MD_NS}}}detailHeading")
            detail_heading.text = "true"
            edit_heading = ET.SubElement(section_el, f"{{{MD_NS}}}editHeading")
            edit_heading.text = "true"
            label_el = ET.SubElement(section_el, f"{{{MD_NS}}}label")
            label_el.text = heading

        if columns_count == 2:
            style = ET.SubElement(section_el, f"{{{MD_NS}}}style")
            style.text = "TwoColumnsTopToBottom"
        else:
            style = ET.SubElement(section_el, f"{{{MD_NS}}}style")
            style.text = "OneColumn"

        # Process layout rows -> columns
        layout_rows = sec.get("layoutRows", [])
        # We need to rebuild as layoutColumns (Salesforce metadata format)
        # In describe, it's rows x items; in metadata XML it's columns x items

        # Collect fields by column position
        col_fields = {}  # col_index -> list of field names
        for row in layout_rows:
            items = row.get("layoutItems", [])
            for col_idx, item in enumerate(items):
                components = item.get("layoutComponents", [])
                for comp in components:
                    field_name = comp.get("value") or comp.get("details", {}).get("name", "")
                    if field_name:
                        col_fields.setdefault(col_idx, []).append(field_name)

        for col_idx in range(columns_count):
            col_el = ET.SubElement(section_el, f"{{{MD_NS}}}layoutColumns")
            for field_name in col_fields.get(col_idx, []):
                li = ET.SubElement(col_el, f"{{{MD_NS}}}layoutItems")
                behavior = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                # Determine if read-only or editable
                f_info = field_map.get(field_name, {})
                if f_info.get("updateable", True):
                    behavior.text = "Edit"
                else:
                    if f_info.get("createable", False):
                        behavior.text = "Edit"
                    else:
                        behavior.text = "Readonly"
                field_el = ET.SubElement(li, f"{{{MD_NS}}}field")
                field_el.text = field_name

    # Now add our new sections before System Information / at the end
    def add_custom_section(label, fields_left, fields_right, columns=2):
        section_el = ET.SubElement(root, f"{{{MD_NS}}}layoutSections")
        cl = ET.SubElement(section_el, f"{{{MD_NS}}}customLabel")
        cl.text = "true"
        dh = ET.SubElement(section_el, f"{{{MD_NS}}}detailHeading")
        dh.text = "true"
        eh = ET.SubElement(section_el, f"{{{MD_NS}}}editHeading")
        eh.text = "true"
        lbl = ET.SubElement(section_el, f"{{{MD_NS}}}label")
        lbl.text = label

        if columns == 2:
            style = ET.SubElement(section_el, f"{{{MD_NS}}}style")
            style.text = "TwoColumnsLeftToRight"
            max_rows = max(len(fields_left), len(fields_right))
            for i in range(max_rows):
                col_l = ET.SubElement(section_el, f"{{{MD_NS}}}layoutColumns")
                if i < len(fields_left):
                    li = ET.SubElement(col_l, f"{{{MD_NS}}}layoutItems")
                    b = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                    b.text = "Edit"
                    f = ET.SubElement(li, f"{{{MD_NS}}}field")
                    f.text = fields_left[i]
                col_r = ET.SubElement(section_el, f"{{{MD_NS}}}layoutColumns")
                if i < len(fields_right):
                    li = ET.SubElement(col_r, f"{{{MD_NS}}}layoutItems")
                    b = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                    b.text = "Edit"
                    f = ET.SubElement(li, f"{{{MD_NS}}}field")
                    f.text = fields_right[i]
        else:
            style = ET.SubElement(section_el, f"{{{MD_NS}}}style")
            style.text = "OneColumn"
            col = ET.SubElement(section_el, f"{{{MD_NS}}}layoutColumns")
            for fn in fields_left:
                li = ET.SubElement(col, f"{{{MD_NS}}}layoutItems")
                b = ET.SubElement(li, f"{{{MD_NS}}}behavior")
                b.text = "Edit"
                f = ET.SubElement(li, f"{{{MD_NS}}}field")
                f.text = fn

    add_custom_section(
        "Property Details",
        ["Units__c", "Property_Type__c", "Property_Category__c", "Build_Type__c"],
        ["Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"],
    )
    add_custom_section(
        "ISP Information",
        ["Prospective_ISP__c"],
        ["Confirmed_ISP__c"],
    )
    add_custom_section(
        "Migration Reference",
        ["Monday_Item_ID__c"],
        [],
        columns=1,
    )

    # Serialize
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
    }, "Opportunity Layout (reconstructed from describe)")


def fallback_field_level_security(session_id):
    """Fallback: Set field-level security for custom fields on key profiles."""
    print("\n  FALLBACK: Setting Field-Level Security for custom fields.")
    print("  (Fields will be accessible but may need manual layout placement.)")

    custom_fields = [
        "Units__c", "Property_Type__c", "Property_Category__c", "Build_Type__c",
        "Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c",
        "Prospective_ISP__c", "Confirmed_ISP__c", "Monday_Item_ID__c",
    ]

    profiles = ["Admin", "Standard"]

    for profile_name in profiles:
        field_perms = ""
        for field in custom_fields:
            field_perms += f"""
        <fieldPermissions>
            <editable>true</editable>
            <field>Opportunity.{field}</field>
            <readable>true</readable>
        </fieldPermissions>"""

        profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    {field_perms}
</Profile>"""

        package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>{profile_name}</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

        result = deploy_metadata_package(session_id, {
            "package.xml": package_xml,
            f"profiles/{profile_name}.profile": profile_xml,
        }, f"FLS for {profile_name} profile")

        if result:
            print(f"    FLS set for {profile_name} profile.")
        else:
            print(f"    FLS failed for {profile_name} profile.")

    print("\n  NOTE: Fields are now visible via FLS. To add them to the page layout,")
    print("  go to Setup > Object Manager > Opportunity > Page Layouts > Opportunity Layout")
    print("  and drag the fields into new sections.")
    return False


# ══════════════════════════════════════════════════════════════════════════
# TASK 2: Create List Views via Metadata API
# ══════════════════════════════════════════════════════════════════════════
def create_list_views(session_id):
    print("\n" + "=" * 70)
    print("TASK 2: CREATE OPPORTUNITY LIST VIEWS")
    print("=" * 70)

    base_columns = """
        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Units__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>Property_Category__c</columns>
        <columns>Prospective_ISP__c</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>"""

    closed_won_columns = base_columns + """
        <columns>Confirmed_ISP__c</columns>"""

    views = [
        {
            "name": "All_Open_MDU_Deals",
            "label": "All Open MDU Deals",
            "columns": base_columns,
            "filters": """
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>""",
        },
        {
            "name": "Prospecting_View",
            "label": "Prospecting",
            "columns": base_columns,
            "filters": """
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Prospecting</value>
        </filters>""",
        },
        {
            "name": "In_Negotiation_View",
            "label": "In Negotiation",
            "columns": base_columns,
            "filters": """
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Negotiation</value>
        </filters>""",
        },
        {
            "name": "Closed_Won_View",
            "label": "Closed Won",
            "columns": closed_won_columns,
            "filters": """
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Closed Won</value>
        </filters>""",
        },
        {
            "name": "Closed_Lost_View",
            "label": "Closed Lost",
            "columns": base_columns,
            "filters": """
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Closed Lost</value>
        </filters>""",
        },
    ]

    # First, retrieve an existing Opportunity list view to check column name format
    print("\n  Retrieving existing list views to check column format...")
    retrieve_inner = """
          <types>
            <members>Opportunity</members>
            <name>CustomObject</name>
          </types>"""
    zip_bytes = retrieve_metadata(session_id, retrieve_inner)
    if zip_bytes:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for name in zf.namelist():
            if "object" in name.lower():
                content = zf.read(name).decode("utf-8")
                # Find existing column references
                import re
                cols_found = re.findall(r'<columns>([^<]+)</columns>', content)
                if cols_found:
                    print(f"  Existing column names in retrieved metadata: {cols_found[:15]}")
                break

    # List views for standard objects must be embedded in the .object file
    list_views_xml = ""
    for view in views:
        list_views_xml += f"""
    <listViews>
        <fullName>{view['name']}</fullName>
        <label>{view['label']}</label>
        {view['columns']}
        <filterScope>Everything</filterScope>
        {view['filters']}
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>"""

    obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    {list_views_xml}
</CustomObject>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    result = deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "objects/Opportunity.object": obj_xml,
    }, "Opportunity List Views (5 views)")

    return result


def create_list_views_via_object_metadata(session_id, views, base_columns, closed_won_columns):
    """Alternative: embed list views inside an Opportunity .object file."""
    print("\n  Trying list views embedded in CustomObject metadata...")

    list_views_xml = ""
    for view in views:
        list_views_xml += f"""
    <listViews>
        <fullName>{view['name']}</fullName>
        <label>{view['label']}</label>
        {view['columns']}
        <filterScope>Everything</filterScope>
        {view['filters']}
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>"""

    obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    {list_views_xml}
</CustomObject>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "objects/Opportunity.object": obj_xml,
    }, "Opportunity List Views (via CustomObject)")


# ══════════════════════════════════════════════════════════════════════════
# TASK 3: Check Path enablement
# ══════════════════════════════════════════════════════════════════════════
def check_path_settings(session_id):
    print("\n" + "=" * 70)
    print("TASK 3: CHECK PATH (SALES PATH) ENABLEMENT")
    print("=" * 70)

    # Try Tooling API to check PathAssistant settings
    print("\n  Checking for existing Path configurations...")

    # Check if PathAssistant is available via Tooling API
    tooling_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}

    # Query for PathAssistant
    query = "SELECT Id, DeveloperName, MasterLabel FROM PathAssistant"
    resp = requests.get(tooling_url, headers=headers, params={"q": query})

    if resp.status_code == 200:
        data = resp.json()
        records = data.get("records", [])
        if records:
            print(f"  Found {len(records)} existing Path configuration(s):")
            for rec in records:
                print(f"    - {rec.get('MasterLabel', 'N/A')} ({rec.get('DeveloperName', 'N/A')})")
            print("  Path is already configured!")
            return True
        else:
            print("  No Path configurations found.")
    else:
        print(f"  PathAssistant query returned {resp.status_code}")
        if resp.status_code == 400:
            error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            print(f"  Error: {str(error)[:300]}")

    # Try to enable Path Settings via Metadata API
    print("\n  Attempting to enable Path Settings via Metadata API...")

    path_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PathAssistantSettings xmlns="http://soap.sforce.com/2006/04/metadata">
    <pathAssistantEnabled>true</pathAssistantEnabled>
</PathAssistantSettings>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>PathAssistant</members>
        <name>Settings</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    result = deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "settings/PathAssistant.settings": path_xml,
    }, "Path Assistant Settings")

    if result:
        print("  Path Settings enabled!")

        # Now try to create a Path for Opportunity
        print("\n  Creating Opportunity Sales Path...")
        opp_path_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PathAssistant xmlns="http://soap.sforce.com/2006/04/metadata">
    <active>true</active>
    <entityName>Opportunity</entityName>
    <fieldName>StageName</fieldName>
    <masterLabel>Opportunity Sales Path</masterLabel>
    <pathAssistantSteps>
        <fieldNames>Property_Type__c</fieldNames>
        <fieldNames>Units__c</fieldNames>
        <picklistValueName>Prospecting</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <fieldNames>Property_Category__c</fieldNames>
        <fieldNames>Prospective_ISP__c</fieldNames>
        <picklistValueName>Qualification</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <fieldNames>Prospective_ISP__c</fieldNames>
        <picklistValueName>Negotiation</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <picklistValueName>Engineering</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <picklistValueName>Construction</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <picklistValueName>Activation</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <fieldNames>Confirmed_ISP__c</fieldNames>
        <picklistValueName>Closed Won</picklistValueName>
    </pathAssistantSteps>
    <pathAssistantSteps>
        <picklistValueName>Closed Lost</picklistValueName>
    </pathAssistantSteps>
    <recordTypeName>Master</recordTypeName>
</PathAssistant>"""

        path_package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.Opportunity_Sales_Path</members>
        <name>PathAssistant</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

        path_result = deploy_metadata_package(session_id, {
            "package.xml": path_package_xml,
            "pathAssistants/Opportunity.Opportunity_Sales_Path.pathAssistant": opp_path_xml,
        }, "Opportunity Sales Path")

        if path_result:
            print("  Opportunity Sales Path created and activated!")
        else:
            print("  Could not create Sales Path via API.")
            print("  Manual step: Setup > Path Settings > New Path > select Opportunity / StageName")
        return result
    else:
        print("\n  Could not enable Path Settings via API.")
        print("  MANUAL STEPS REQUIRED:")
        print("    1. Go to Setup > Path Settings")
        print("    2. Enable Path")
        print("    3. Click 'New Path'")
        print("    4. Object: Opportunity, Picklist: Stage")
        print("    5. Configure guidance for each stage as desired")
        print("    6. Activate the path")
        return False


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("Authentication failed. Exiting.")
        exit(1)

    # Task 1: Update Opportunity Layout
    layout_ok = update_opportunity_layout(session_id)

    # Task 2: Create List Views
    views_ok = create_list_views(session_id)

    # Task 3: Check/Enable Path
    path_ok = check_path_settings(session_id)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Task 1 - Opportunity Layout:  {'SUCCESS' if layout_ok else 'NEEDS MANUAL SETUP (see notes above)'}")
    print(f"  Task 2 - List Views:          {'SUCCESS' if views_ok else 'FAILED'}")
    print(f"  Task 3 - Sales Path:          {'SUCCESS' if path_ok else 'NEEDS MANUAL SETUP (see notes above)'}")

    if not layout_ok:
        print("\n  LAYOUT MANUAL STEPS:")
        print("    Setup > Object Manager > Opportunity > Page Layouts")
        print("    Edit 'Opportunity Layout' and add sections:")
        print("      - 'Property Details' (2-col): Units, Property_Type, Property_Category, Build_Type | Address, City, State, Zip")
        print("      - 'ISP Information' (2-col): Prospective_ISP | Confirmed_ISP")
        print("      - 'Migration Reference' (1-col): Monday_Item_ID")

    print("\n  Done!")
