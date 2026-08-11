"""
Update Opportunity Page Layout, create sample Agreement records, and update List Views.

Task 1: Update Opportunity Layout via Metadata API
  - Add "Integration Links" section (SiteTracker_Project_ID__c, SiteTracker_URL__c, IronClad_URL__c)
  - Add Agreement__c related list
  - Remove Products, Quotes, Partners related lists

Task 2: Create 25-35 sample Agreement__c records across Opportunities

Task 3: Update/Create List Views for MDU stages
"""

import requests
import json
import time
import base64
import io
import random
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce, SalesforceError

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
PASSWORD_TOKEN = PASSWORD + SECURITY_TOKEN
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "v59.0"
API_VERSION_NUM = "59.0"
MD_NS = "http://soap.sforce.com/2006/04/metadata"

# ── Summary tracking ────────────────────────────────────────────────────
summary = {
    "layout_deployed": False,
    "agreements_created": 0,
    "agreements_failed": 0,
    "views_deployed": False,
}


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

    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"SOAP login failed ({resp.status_code}): {resp.text[:500]}")

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "sf": "urn:partner.soap.sforce.com",
    }
    root = ET.fromstring(resp.text)
    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        raise Exception(f"SOAP Fault: {ET.tostring(fault, encoding='unicode')}")

    session_id = root.find(".//sf:sessionId", ns)
    if session_id is None:
        raise Exception("Could not find sessionId in response.")

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
                print(f"  SUCCESS: {description}")
                return True
            else:
                print(f"  FAILED: {description}")
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


# ═══════════════════════════════════════════════════════════════════════════
# TASK 1: UPDATE OPPORTUNITY PAGE LAYOUT
# ═══════════════════════════════════════════════════════════════════════════
def task1_update_layout(session_id):
    print("\n" + "=" * 70)
    print("TASK 1: UPDATE OPPORTUNITY PAGE LAYOUT")
    print("=" * 70)

    # Step 1: Retrieve the current layout
    print("\n  Step 1: Retrieving current Opportunity Layout...")
    package_inner = """
          <types>
            <members>Opportunity-Opportunity Layout</members>
            <name>Layout</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)
    if not zip_bytes:
        print("  ERROR: Could not retrieve layout. Aborting Task 1.")
        return False

    # Step 2: Parse the retrieved layout XML
    print("\n  Step 2: Parsing retrieved layout...")
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    layout_xml = None

    for name in zf.namelist():
        print(f"    ZIP entry: {name}")
        if "layout" in name.lower() and name.endswith(".layout"):
            layout_xml = zf.read(name).decode("utf-8")

    if not layout_xml:
        print("  ERROR: Could not find layout file in retrieved ZIP.")
        return False

    print(f"  Layout XML length: {len(layout_xml)} chars")

    ET.register_namespace("", MD_NS)
    root = ET.fromstring(layout_xml)

    # ── Print current sections for debugging ──
    all_sections = list(root.findall(f"{{{MD_NS}}}layoutSections"))
    print(f"\n  Current sections ({len(all_sections)}):")
    isp_section_idx = None
    migration_section_idx = None
    integration_section_idx = None

    for i, sec in enumerate(all_sections):
        label_el = sec.find(f"{{{MD_NS}}}label")
        label = label_el.text if label_el is not None else "(none)"
        print(f"    [{i}] {label}")
        if label == "ISP Information":
            isp_section_idx = i
        if label == "Migration Reference":
            migration_section_idx = i
        if label == "Integration Links":
            integration_section_idx = i

    # ── Step 3a: Add "Integration Links" section ──
    print("\n  Step 3a: Adding 'Integration Links' section...")

    if integration_section_idx is not None:
        print("    'Integration Links' section already exists. Removing old one to replace.")
        root.remove(all_sections[integration_section_idx])
        # Re-read sections after removal
        all_sections = list(root.findall(f"{{{MD_NS}}}layoutSections"))
        isp_section_idx = None
        migration_section_idx = None
        for i, sec in enumerate(all_sections):
            label_el = sec.find(f"{{{MD_NS}}}label")
            label = label_el.text if label_el is not None else "(none)"
            if label == "ISP Information":
                isp_section_idx = i
            if label == "Migration Reference":
                migration_section_idx = i

    # Build the new Integration Links section
    new_section = ET.Element(f"{{{MD_NS}}}layoutSections")

    custom_label = ET.SubElement(new_section, f"{{{MD_NS}}}customLabel")
    custom_label.text = "true"
    detail_heading = ET.SubElement(new_section, f"{{{MD_NS}}}detailHeading")
    detail_heading.text = "true"
    edit_heading = ET.SubElement(new_section, f"{{{MD_NS}}}editHeading")
    edit_heading.text = "true"
    label_el = ET.SubElement(new_section, f"{{{MD_NS}}}label")
    label_el.text = "Integration Links"
    style_el = ET.SubElement(new_section, f"{{{MD_NS}}}style")
    style_el.text = "TwoColumnsLeftToRight"

    # Left column: SiteTracker_Project_ID__c, SiteTracker_URL__c
    left_col = ET.SubElement(new_section, f"{{{MD_NS}}}layoutColumns")
    for field_name in ["SiteTracker_Project_ID__c", "SiteTracker_URL__c"]:
        item = ET.SubElement(left_col, f"{{{MD_NS}}}layoutItems")
        behavior = ET.SubElement(item, f"{{{MD_NS}}}behavior")
        behavior.text = "Edit"
        field = ET.SubElement(item, f"{{{MD_NS}}}field")
        field.text = field_name

    # Right column: IronClad_URL__c
    right_col = ET.SubElement(new_section, f"{{{MD_NS}}}layoutColumns")
    item = ET.SubElement(right_col, f"{{{MD_NS}}}layoutItems")
    behavior = ET.SubElement(item, f"{{{MD_NS}}}behavior")
    behavior.text = "Edit"
    field = ET.SubElement(item, f"{{{MD_NS}}}field")
    field.text = "IronClad_URL__c"

    # Insert after ISP Information, before Migration Reference
    if isp_section_idx is not None:
        insert_idx = isp_section_idx + 1
        # Find the position in the root element (sections may not be contiguous)
        root_children = list(root)
        section_positions = []
        for ci, child in enumerate(root_children):
            if child.tag == f"{{{MD_NS}}}layoutSections":
                section_positions.append(ci)

        if isp_section_idx < len(section_positions):
            insert_pos = section_positions[isp_section_idx] + 1
            root.insert(insert_pos, new_section)
            print(f"    Inserted after ISP Information (section index {isp_section_idx})")
        else:
            root.append(new_section)
            print("    Appended at end (could not find position)")
    else:
        # If ISP Information not found, insert before Migration Reference or append
        if migration_section_idx is not None:
            root_children = list(root)
            section_positions = []
            for ci, child in enumerate(root_children):
                if child.tag == f"{{{MD_NS}}}layoutSections":
                    section_positions.append(ci)
            if migration_section_idx < len(section_positions):
                insert_pos = section_positions[migration_section_idx]
                root.insert(insert_pos, new_section)
                print(f"    Inserted before Migration Reference")
            else:
                root.append(new_section)
                print("    Appended at end")
        else:
            # Insert before relatedLists
            first_rl = root.find(f"{{{MD_NS}}}relatedLists")
            if first_rl is not None:
                root_children = list(root)
                rl_pos = root_children.index(first_rl)
                root.insert(rl_pos, new_section)
                print("    Inserted before related lists")
            else:
                root.append(new_section)
                print("    Appended at end")

    # ── Step 3b: Add Agreement__c related list ──
    print("\n  Step 3b: Adding Agreement__c related list...")

    # Check if it already exists
    related_lists = list(root.findall(f"{{{MD_NS}}}relatedLists"))
    agreement_rl_exists = False
    for rl in related_lists:
        rl_name = rl.find(f"{{{MD_NS}}}relatedList")
        if rl_name is not None and "Agreement__c" in (rl_name.text or ""):
            agreement_rl_exists = True
            print("    Agreement__c related list already exists.")
            break

    if not agreement_rl_exists:
        agreement_rl = ET.Element(f"{{{MD_NS}}}relatedLists")

        # columns
        for col in ["NAME", "Agreement_Type__c", "Status__c", "Signed_Date__c", "Signer__c"]:
            col_el = ET.SubElement(agreement_rl, f"{{{MD_NS}}}fields")
            col_el.text = col

        rl_el = ET.SubElement(agreement_rl, f"{{{MD_NS}}}relatedList")
        rl_el.text = "Agreement__c.Opportunity__c"

        # Insert as first related list (most relevant)
        first_rl = root.find(f"{{{MD_NS}}}relatedLists")
        if first_rl is not None:
            root_children = list(root)
            rl_pos = root_children.index(first_rl)
            root.insert(rl_pos, agreement_rl)
            print("    Inserted Agreement__c related list at top of related lists.")
        else:
            root.append(agreement_rl)
            print("    Appended Agreement__c related list.")

    # ── Step 3c: Remove unwanted related lists ──
    print("\n  Step 3c: Removing unwanted related lists (Products, Quotes, Partners)...")

    remove_names = {"RelatedLineItemList", "RelatedQuoteList", "RelatedPartnerList"}
    removed = []

    for rl in list(root.findall(f"{{{MD_NS}}}relatedLists")):
        rl_name = rl.find(f"{{{MD_NS}}}relatedList")
        if rl_name is not None and rl_name.text in remove_names:
            root.remove(rl)
            removed.append(rl_name.text)
            print(f"    Removed: {rl_name.text}")

    if not removed:
        print("    None of the target related lists found to remove.")

    # Print final related lists for verification
    print("\n  Final related lists:")
    for rl in root.findall(f"{{{MD_NS}}}relatedLists"):
        rl_name = rl.find(f"{{{MD_NS}}}relatedList")
        name = rl_name.text if rl_name is not None else "(unknown)"
        print(f"    - {name}")

    # ── Step 4: Deploy ──
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

    success = deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "layouts/Opportunity-Opportunity Layout.layout": new_layout_xml,
    }, "Opportunity Layout update (Integration Links + Agreement RL)")

    summary["layout_deployed"] = success
    return success


# ═══════════════════════════════════════════════════════════════════════════
# TASK 2: CREATE SAMPLE AGREEMENT RECORDS
# ═══════════════════════════════════════════════════════════════════════════
def task2_create_agreements():
    print("\n" + "=" * 70)
    print("TASK 2: CREATE SAMPLE AGREEMENT RECORDS")
    print("=" * 70)

    sf = Salesforce(
        username=USERNAME,
        password=PASSWORD,
        security_token=SECURITY_TOKEN,
    )
    print(f"  Connected via simple_salesforce: {sf.sf_instance}")

    # ── Query Opportunities by stage ──
    print("\n  Querying Opportunities by stage...")

    stage_queries = {
        "Under Contract": "SELECT Id, Name, StageName FROM Opportunity WHERE StageName = 'Under Contract' LIMIT 3",
        "Ready for Engineering": "SELECT Id, Name, StageName FROM Opportunity WHERE StageName = 'Ready for Engineering' LIMIT 3",
        "Closed Won": "SELECT Id, Name, StageName FROM Opportunity WHERE StageName = 'Closed Won' LIMIT 3",
        "Prospecting": "SELECT Id, Name, StageName FROM Opportunity WHERE StageName = 'Prospecting' LIMIT 3",
        "Under Construction": "SELECT Id, Name, StageName FROM Opportunity WHERE StageName = 'Under Construction' LIMIT 2",
    }

    opps_by_stage = {}
    for stage, query in stage_queries.items():
        result = sf.query(query)
        opps_by_stage[stage] = result["records"]
        print(f"    {stage}: {len(result['records'])} opportunities")

    # ── Query Contacts for signers ──
    print("\n  Querying Contacts...")
    contacts = sf.query("SELECT Id, Name FROM Contact LIMIT 15")["records"]
    print(f"    Found {len(contacts)} contacts")

    if not contacts:
        print("  ERROR: No contacts found. Cannot assign signers. Aborting Task 2.")
        return False

    # ── Check for existing agreements to avoid duplicates ──
    print("\n  Checking for existing Agreement records...")
    existing = sf.query("SELECT Id, Opportunity__c, Agreement_Type__c FROM Agreement__c")
    existing_keys = set()
    for rec in existing["records"]:
        key = f"{rec['Opportunity__c']}_{rec['Agreement_Type__c']}"
        existing_keys.add(key)
    print(f"    Found {len(existing['records'])} existing agreements")

    # ── Helper: random date in a range ──
    today = date(2026, 3, 10)

    def random_date(days_ago_min, days_ago_max):
        """Return a date string between days_ago_max and days_ago_min days ago."""
        days = random.randint(days_ago_min, days_ago_max)
        return (today - timedelta(days=days)).isoformat()

    def random_signer():
        return random.choice(contacts)["Id"]

    # ── Create agreements for each stage category ──
    created = []
    failed = []

    def create_agreement(opp_id, opp_name, agr_type, status, signed_date=None,
                         signer_id=None, requested_date=None, notes=None):
        """Create a single Agreement__c record."""
        key = f"{opp_id}_{agr_type}"
        if key in existing_keys:
            print(f"    ~ SKIP (exists): {opp_name[:35]:35s} | {agr_type:5s} | {status}")
            return

        data = {
            "Opportunity__c": opp_id,
            "Agreement_Type__c": agr_type,
            "Status__c": status,
        }
        if signed_date:
            data["Signed_Date__c"] = signed_date
        if signer_id:
            data["Signer__c"] = signer_id
        if requested_date:
            data["Requested_Date__c"] = requested_date
        if notes:
            data["Notes__c"] = notes

        try:
            result = sf.Agreement__c.create(data)
            created.append({
                "id": result["id"],
                "opp": opp_name,
                "type": agr_type,
                "status": status,
            })
            marker = "SIGNED" if status == "Signed" else status
            print(f"    + {opp_name[:35]:35s} | {agr_type:5s} | {marker}")
        except SalesforceError as e:
            failed.append({"opp": opp_name, "type": agr_type, "error": str(e)})
            print(f"    ! FAIL {opp_name[:35]:35s} | {agr_type:5s} | {e}")

    # ── "Under Contract" — PAL signed, others in progress ──
    print("\n  --- Under Contract Opportunities ---")
    for opp in opps_by_stage.get("Under Contract", []):
        oid, name = opp["Id"], opp["Name"]

        # PAL: Signed 2-3 months ago
        create_agreement(oid, name, "PAL", "Signed",
                         signed_date=random_date(60, 90),
                         signer_id=random_signer(),
                         requested_date=random_date(100, 120))

        # ROW: Under Review
        create_agreement(oid, name, "ROW", "Under Review",
                         requested_date=random_date(30, 50))

        # EMA: Drafted
        create_agreement(oid, name, "EMA", "Drafted",
                         requested_date=random_date(20, 40))

    # ── "Ready for Engineering" — all agreements done ──
    print("\n  --- Ready for Engineering Opportunities ---")
    for opp in opps_by_stage.get("Ready for Engineering", []):
        oid, name = opp["Id"], opp["Name"]

        # PAL: Signed 4-5 months ago
        create_agreement(oid, name, "PAL", "Signed",
                         signed_date=random_date(120, 150),
                         signer_id=random_signer(),
                         requested_date=random_date(160, 180))

        # ROW: Signed 2-3 months ago
        create_agreement(oid, name, "ROW", "Signed",
                         signed_date=random_date(60, 90),
                         signer_id=random_signer(),
                         requested_date=random_date(100, 130))

        # EMA: Signed 1-2 months ago
        create_agreement(oid, name, "EMA", "Signed",
                         signed_date=random_date(30, 60),
                         signer_id=random_signer(),
                         requested_date=random_date(70, 100))

    # ── "Closed Won" — everything done ──
    print("\n  --- Closed Won Opportunities ---")
    for opp in opps_by_stage.get("Closed Won", []):
        oid, name = opp["Id"], opp["Name"]

        # PAL: Signed 6+ months ago
        create_agreement(oid, name, "PAL", "Signed",
                         signed_date=random_date(180, 240),
                         signer_id=random_signer(),
                         requested_date=random_date(250, 280))

        # ROW: Signed 4-5 months ago
        create_agreement(oid, name, "ROW", "Signed",
                         signed_date=random_date(120, 150),
                         signer_id=random_signer(),
                         requested_date=random_date(160, 190))

        # EMA: Signed 3-4 months ago
        create_agreement(oid, name, "EMA", "Signed",
                         signed_date=random_date(90, 120),
                         signer_id=random_signer(),
                         requested_date=random_date(130, 160))

        # Bulk: Signed on some (roughly half)
        if random.random() > 0.4:
            create_agreement(oid, name, "Bulk", "Signed",
                             signed_date=random_date(60, 100),
                             signer_id=random_signer(),
                             requested_date=random_date(110, 140),
                             notes="Bulk service agreement for MDU deployment")

    # ── "Under Construction" — all signed ──
    print("\n  --- Under Construction Opportunities ---")
    for opp in opps_by_stage.get("Under Construction", []):
        oid, name = opp["Id"], opp["Name"]

        create_agreement(oid, name, "PAL", "Signed",
                         signed_date=random_date(150, 200),
                         signer_id=random_signer(),
                         requested_date=random_date(210, 240))

        create_agreement(oid, name, "ROW", "Signed",
                         signed_date=random_date(100, 140),
                         signer_id=random_signer(),
                         requested_date=random_date(150, 180))

        create_agreement(oid, name, "EMA", "Signed",
                         signed_date=random_date(70, 100),
                         signer_id=random_signer(),
                         requested_date=random_date(110, 140))

    # ── "Prospecting" — PAL not started or requested ──
    print("\n  --- Prospecting Opportunities ---")
    for opp in opps_by_stage.get("Prospecting", []):
        oid, name = opp["Id"], opp["Name"]

        # Some have PAL as Not Started, some as Requested
        if random.random() > 0.5:
            create_agreement(oid, name, "PAL", "Requested",
                             requested_date=random_date(5, 20))
        else:
            create_agreement(oid, name, "PAL", "Not Started")

    # ── Summary ──
    print(f"\n  Agreements created: {len(created)}")
    print(f"  Agreements failed:  {len(failed)}")

    if failed:
        print("\n  Failed details:")
        for f in failed:
            print(f"    {f['opp'][:35]} | {f['type']} | {f['error'][:80]}")

    summary["agreements_created"] = len(created)
    summary["agreements_failed"] = len(failed)
    return len(created) > 0


# ═══════════════════════════════════════════════════════════════════════════
# TASK 3: UPDATE LIST VIEWS
# ═══════════════════════════════════════════════════════════════════════════
def task3_update_list_views(session_id):
    print("\n" + "=" * 70)
    print("TASK 3: UPDATE LIST VIEWS")
    print("=" * 70)

    # Standard columns for all views
    std_columns = """        <columns>OPPORTUNITY_NAME</columns>
        <columns>ACCOUNT_NAME</columns>
        <columns>OPPORTUNITY_STAGE_NAME</columns>
        <columns>OPPORTUNITY_AMOUNT</columns>
        <columns>Agreement_Name__c</columns>
        <columns>OPPORTUNITY_CLOSE_DATE</columns>
        <columns>CORE.USERS.ALIAS</columns>"""

    # ── View 1: All Open MDU Deals ──
    all_open_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>All_Open_MDU_Deals</fullName>
    <booleanFilter></booleanFilter>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>notEqual</operation>
        <value>Closed Won,Closed Lost</value>
    </filters>
    <label>All Open MDU Deals</label>
</ListView>"""

    # ── View 2: Under Contract ──
    under_contract_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Under_Contract</fullName>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>equals</operation>
        <value>Under Contract</value>
    </filters>
    <label>Under Contract</label>
</ListView>"""

    # ── View 3: Ready for Engineering ──
    rfe_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Ready_for_Engineering</fullName>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>equals</operation>
        <value>Ready for Engineering</value>
    </filters>
    <label>Ready for Engineering</label>
</ListView>"""

    # ── View 4: Prospecting ──
    prospecting_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Prospecting</fullName>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>equals</operation>
        <value>Prospecting</value>
    </filters>
    <label>Prospecting</label>
</ListView>"""

    # ── View 5: Closed Won ──
    closed_won_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Closed_Won</fullName>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>equals</operation>
        <value>Closed Won</value>
    </filters>
    <label>Closed Won</label>
</ListView>"""

    # ── View 6: Closed Lost ──
    closed_lost_view = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Closed_Lost</fullName>
{std_columns}
    <filterScope>Everything</filterScope>
    <filters>
        <field>OPPORTUNITY.STAGE_NAME</field>
        <operation>equals</operation>
        <value>Closed Lost</value>
    </filters>
    <label>Closed Lost</label>
</ListView>"""

    # Build Opportunity object file with all list views embedded
    # Metadata API deploys list views as part of the CustomObject metadata
    # Column names use OBJECT.FIELD format for standard fields
    std_cols = """        <columns>OPPORTUNITY.NAME</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>OPPORTUNITY.AMOUNT</columns>
        <columns>Agreement_Name__c</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>"""

    views_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>All_Open_MDU_Deals</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
        <label>All Open MDU Deals</label>
    </listViews>
    <listViews>
        <fullName>Under_Contract</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Under Contract</value>
        </filters>
        <label>Under Contract</label>
    </listViews>
    <listViews>
        <fullName>Ready_for_Engineering</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Ready for Engineering</value>
        </filters>
        <label>Ready for Engineering</label>
    </listViews>
    <listViews>
        <fullName>Prospecting</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Prospecting</value>
        </filters>
        <label>Prospecting</label>
    </listViews>
    <listViews>
        <fullName>Closed_Won</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Closed Won</value>
        </filters>
        <label>Closed Won</label>
    </listViews>
    <listViews>
        <fullName>Closed_Lost</fullName>
{std_cols}
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Closed Lost</value>
        </filters>
        <label>Closed Lost</label>
    </listViews>
</CustomObject>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.All_Open_MDU_Deals</members>
        <members>Opportunity.Under_Contract</members>
        <members>Opportunity.Ready_for_Engineering</members>
        <members>Opportunity.Prospecting</members>
        <members>Opportunity.Closed_Won</members>
        <members>Opportunity.Closed_Lost</members>
        <name>ListView</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    print("\n  Deploying 6 list views...")
    for view_name in ["All_Open_MDU_Deals", "Under_Contract", "Ready_for_Engineering",
                       "Prospecting", "Closed_Won", "Closed_Lost"]:
        print(f"    - {view_name}")

    success = deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "objects/Opportunity.object": views_xml,
    }, "Opportunity List Views (6 views)")

    # ── Try to delete "In Negotiation" view if it exists ──
    if success:
        print("\n  Checking for 'In Negotiation' view to delete...")
        # We'll try a destructiveChanges deploy to remove it
        destructive_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.In_Negotiation</members>
        <name>ListView</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

        empty_package = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <version>{API_VERSION_NUM}</version>
</Package>"""

        print("  Attempting to delete 'In_Negotiation' list view...")
        del_result = deploy_metadata_package(session_id, {
            "package.xml": empty_package,
            "destructiveChanges.xml": destructive_xml,
        }, "Delete In_Negotiation list view")

        if del_result:
            print("  Deleted 'In_Negotiation' view.")
        else:
            print("  Could not delete 'In_Negotiation' view (may not exist). Continuing.")

    summary["views_deployed"] = success
    return success


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("UPDATE OPPORTUNITY LAYOUT, AGREEMENTS, AND LIST VIEWS")
    print("=" * 70)

    # Authenticate via SOAP (needed for Metadata API)
    print("\nAuthenticating via SOAP...")
    session_id = soap_login()
    print("Authenticated successfully.\n")

    # Task 1: Update Layout
    task1_update_layout(session_id)

    # Task 2: Create Agreement records (uses simple_salesforce)
    task2_create_agreements()

    # Task 3: Update List Views
    task3_update_list_views(session_id)

    # ── Final Summary ──
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"  Task 1 - Layout Update:     {'SUCCESS' if summary['layout_deployed'] else 'FAILED'}")
    print(f"  Task 2 - Agreements:        {summary['agreements_created']} created, {summary['agreements_failed']} failed")
    print(f"  Task 3 - List Views:        {'SUCCESS' if summary['views_deployed'] else 'FAILED'}")
    print("\nDone!")
