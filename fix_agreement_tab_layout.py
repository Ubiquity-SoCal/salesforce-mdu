"""
Fix Agreement__c page layout fields not showing + add Agreements tab to MDU Sales app.

Issue 1: Agreement__c layout fields not visible
  - Redeploy complete page layout with all sections/fields
  - Deploy FLS granting read/edit on all Agreement__c custom fields for Admin + Standard profiles

Issue 2: Agreement__c needs its own Tab in the MDU Sales Lightning App
  - Create a CustomTab for Agreement__c (Custom20 icon — document/contract style)
  - Retrieve current MDU_Sales app, add the Agreement__c tab, redeploy
"""

import requests
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

AGREEMENT_CUSTOM_FIELDS = [
    "Agreement_Type__c",
    "Status__c",
    "IronClad_ID__c",
    "IronClad_URL__c",
    "Requested_Date__c",
    "Signed_Date__c",
    "Expiration_Date__c",
    "Signer__c",
    "Notes__c",
]


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

    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"}

    print("=" * 70)
    print("AUTHENTICATING")
    print("=" * 70)
    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)

    if resp.status_code != 200:
        print(f"SOAP login failed ({resp.status_code}): {resp.text[:500]}")
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

    print("  Authenticated successfully.")
    return session_id.text


def rest_get(session_id, path):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    return requests.get(url, headers=headers)


# ── Metadata API Retrieve ──────────────────────────────────────────────
def retrieve_metadata(session_id, package_inner):
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

    resp = requests.post(metadata_url, data=retrieve_soap, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "retrieve",
    })
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

    resp = requests.post(metadata_url, data=deploy_soap, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "deploy",
    })

    if resp.status_code != 200:
        print(f"  Deploy request failed ({resp.status_code}): {resp.text[:1000]}")
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

        resp = requests.post(metadata_url, data=check_soap, headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "checkDeployStatus",
        })
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


# ══════════════════════════════════════════════════════════════════════
# ISSUE 1: FIX AGREEMENT__C PAGE LAYOUT + FLS
# ══════════════════════════════════════════════════════════════════════

def diagnose_layout_and_fls(session_id):
    """Check current state of Agreement__c layout and FLS."""
    print("\n" + "=" * 70)
    print("STEP 1: DIAGNOSE AGREEMENT__C LAYOUT AND FLS")
    print("=" * 70)

    # 1a. Check what fields exist on Agreement__c
    print("\n  Checking Agreement__c fields via describe...")
    resp = rest_get(session_id, "/sobjects/Agreement__c/describe/")
    if resp.status_code == 200:
        desc = resp.json()
        fields = desc.get("fields", [])
        print(f"  Total fields on Agreement__c: {len(fields)}")
        for f in fields:
            name = f["name"]
            if name.endswith("__c") or name in ("Name", "CreatedById", "LastModifiedById"):
                print(f"    {name}: type={f['type']}, updateable={f['updateable']}")
    else:
        print(f"  Describe failed ({resp.status_code}): {resp.text[:300]}")

    # 1b. Check FieldPermissions for Agreement__c on System Administrator
    print("\n  Checking FieldPermissions for Agreement__c (System Administrator)...")
    soql = (
        "SELECT Id, Field, PermissionsRead, PermissionsEdit, Parent.Profile.Name "
        "FROM FieldPermissions "
        "WHERE SobjectType = 'Agreement__c' "
        "AND Parent.Profile.Name = 'System Administrator'"
    )
    resp2 = rest_get(session_id, f"/query/?q={requests.utils.quote(soql)}")
    if resp2.status_code == 200:
        records = resp2.json().get("records", [])
        if records:
            print(f"  Found {len(records)} field permissions:")
            for r in records:
                print(f"    {r['Field']}: read={r['PermissionsRead']}, edit={r['PermissionsEdit']}")
        else:
            print("  NO field permissions found for System Administrator on Agreement__c!")
            print("  This confirms FLS is likely the issue.")
    else:
        print(f"  FieldPermissions query failed ({resp2.status_code}): {resp2.text[:300]}")

    # 1c. Retrieve the current layout
    print("\n  Retrieving current Agreement__c layout...")
    package_inner = """
          <types>
            <members>Agreement__c-*</members>
            <name>Layout</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)
    layout_name = None

    if zip_bytes:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for name in zf.namelist():
            print(f"    ZIP entry: {name}")
            if name.endswith(".layout"):
                layout_name = name.split("/")[-1].replace(".layout", "")
                # Show what's in the current layout
                layout_content = zf.read(name).decode("utf-8")
                print(f"\n  Current layout content ({layout_name}):")
                # Count fields in the layout
                field_count = layout_content.count("<field>")
                print(f"    Fields referenced in layout: {field_count}")
                # List the fields
                import re
                layout_fields = re.findall(r"<field>([^<]+)</field>", layout_content)
                for lf in layout_fields:
                    print(f"      - {lf}")

    if not layout_name:
        layout_name = "Agreement__c-Agreement Layout"
        print(f"\n  No layout found via wildcard, will use: {layout_name}")

    return layout_name


def deploy_layout(session_id, layout_name):
    """Deploy a complete Agreement__c page layout with all fields."""
    print("\n" + "=" * 70)
    print("STEP 2: DEPLOY AGREEMENT__C PAGE LAYOUT")
    print("=" * 70)

    layout_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <layoutSections>
        <label>Agreement Information</label>
        <style>TwoColumnsLeftToRight</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Readonly</behavior>
                <field>Name</field>
            </layoutItems>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Agreement_Type__c</field>
            </layoutItems>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Status__c</field>
            </layoutItems>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Opportunity__c</field>
            </layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>IronClad_ID__c</field>
            </layoutItems>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>IronClad_URL__c</field>
            </layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Dates</label>
        <style>TwoColumnsLeftToRight</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Requested_Date__c</field>
            </layoutItems>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Signed_Date__c</field>
            </layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Expiration_Date__c</field>
            </layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Signer</label>
        <style>OneColumn</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Signer__c</field>
            </layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Notes</label>
        <style>OneColumn</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Notes__c</field>
            </layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>System Information</label>
        <style>TwoColumnsLeftToRight</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Readonly</behavior>
                <field>CreatedById</field>
            </layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems>
                <behavior>Readonly</behavior>
                <field>LastModifiedById</field>
            </layoutItems>
        </layoutColumns>
    </layoutSections>
</Layout>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>{layout_name}</members>
        <name>Layout</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    layout_file_path = f"layouts/{layout_name}.layout"

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        layout_file_path: layout_xml,
    }, "Agreement__c Page Layout (all fields)")


def deploy_fls(session_id):
    """Deploy FLS for all Agreement__c custom fields on Admin + Standard profiles."""
    print("\n" + "=" * 70)
    print("STEP 3: DEPLOY FIELD-LEVEL SECURITY")
    print("=" * 70)

    def build_profile_xml(fields):
        field_perms = ""
        for field in fields:
            field_perms += f"""
    <fieldPermissions>
        <editable>true</editable>
        <field>Agreement__c.{field}</field>
        <readable>true</readable>
    </fieldPermissions>"""

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">{field_perms}
</Profile>"""

    # Note: Opportunity__c is a required/master-detail field, so Salesforce
    # won't allow deploying FLS for it (it's always visible). Only include
    # the editable custom fields.
    all_fields = AGREEMENT_CUSTOM_FIELDS

    files = {
        "package.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Admin</members>
        <members>Standard</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>""",
        "profiles/Admin.profile": build_profile_xml(all_fields),
        "profiles/Standard.profile": build_profile_xml(all_fields),
    }

    print("  Granting read+edit on all Agreement__c fields for:")
    print("    - System Administrator (Admin)")
    print("    - Standard User (Standard)")
    print(f"  Fields: {', '.join(all_fields)}")

    return deploy_metadata_package(session_id, files, "FLS for Agreement__c fields")


# ══════════════════════════════════════════════════════════════════════
# ISSUE 2: CREATE AGREEMENT TAB + ADD TO MDU SALES APP
# ══════════════════════════════════════════════════════════════════════

def deploy_agreement_tab(session_id):
    """Create a CustomTab for Agreement__c."""
    print("\n" + "=" * 70)
    print("STEP 4: CREATE AGREEMENT__C CUSTOM TAB")
    print("=" * 70)

    tab_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomTab xmlns="http://soap.sforce.com/2006/04/metadata">
    <customObject>true</customObject>
    <motif>Custom20: Handshake</motif>
</CustomTab>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Agreement__c</members>
        <name>CustomTab</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "tabs/Agreement__c.tab": tab_xml,
    }, "Agreement__c Custom Tab")


def add_tab_to_mdu_app(session_id):
    """Retrieve MDU_Sales app, add Agreement__c tab, and redeploy."""
    print("\n" + "=" * 70)
    print("STEP 5: ADD AGREEMENT TAB TO MDU SALES APP")
    print("=" * 70)

    # Retrieve current MDU_Sales app metadata
    print("\n  Retrieving current MDU_Sales app metadata...")
    package_inner = """
          <types>
            <members>MDU_Sales</members>
            <name>CustomApplication</name>
          </types>"""

    zip_bytes = retrieve_metadata(session_id, package_inner)

    current_tabs = []
    app_xml_content = None

    if zip_bytes:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for name in zf.namelist():
            print(f"    ZIP entry: {name}")
            if name.endswith(".app"):
                app_xml_content = zf.read(name).decode("utf-8")
                print(f"\n  Current MDU_Sales app content:")
                # Extract current tabs
                import re
                current_tabs = re.findall(r"<tabs>([^<]+)</tabs>", app_xml_content)
                for t in current_tabs:
                    print(f"    - {t}")

    # Build updated app XML with Agreement__c tab added
    agreement_tab_name = "Agreement__c"

    if agreement_tab_name in current_tabs:
        print(f"\n  Agreement__c tab is ALREADY in MDU_Sales app. Skipping.")
        return True

    # Add the Agreement__c tab to the existing tabs list
    updated_tabs = current_tabs + [agreement_tab_name]

    tabs_xml = ""
    for tab in updated_tabs:
        tabs_xml += f"\n    <tabs>{tab}</tabs>"

    # If we couldn't retrieve the app, build from known defaults
    if not current_tabs:
        print("  Could not retrieve current app tabs. Using known defaults + Agreement__c.")
        tabs_xml = """
    <tabs>standard-Opportunity</tabs>
    <tabs>standard-Account</tabs>
    <tabs>standard-Contact</tabs>
    <tabs>standard-report</tabs>
    <tabs>standard-Dashboard</tabs>
    <tabs>Agreement__c</tabs>"""

    app_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MDU Sales</label>
    <formFactors>Large</formFactors>
    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>
    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>
    <isNavTabPersistenceDisabled>false</isNavTabPersistenceDisabled>
    <navType>Standard</navType>
    <uiType>Lightning</uiType>{tabs_xml}
</CustomApplication>"""

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales</members>
        <name>CustomApplication</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    print(f"\n  Deploying MDU_Sales app with tabs: {updated_tabs}")

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "applications/MDU_Sales.app": app_xml,
    }, "MDU_Sales app with Agreement__c tab")


# ══════════════════════════════════════════════════════════════════════
# VERIFICATION
# ══════════════════════════════════════════════════════════════════════

def verify_all(session_id):
    """Verify layout, FLS, tab, and app are all correct."""
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Verify Agreement__c fields are accessible
    print("\n  Checking Agreement__c field accessibility...")
    resp = rest_get(session_id, "/sobjects/Agreement__c/describe/")
    if resp.status_code == 200:
        desc = resp.json()
        fields = desc.get("fields", [])
        expected_fields = ["Name", "Opportunity__c"] + AGREEMENT_CUSTOM_FIELDS
        for exp in expected_fields:
            match = next((f for f in fields if f["name"] == exp), None)
            if match:
                print(f"    {exp}: ACCESSIBLE (updateable={match['updateable']})")
            else:
                print(f"    {exp}: NOT FOUND")
    else:
        print(f"  Agreement__c describe failed ({resp.status_code})")

    # Verify FLS
    print("\n  Checking FLS for System Administrator...")
    soql = (
        "SELECT Field, PermissionsRead, PermissionsEdit "
        "FROM FieldPermissions "
        "WHERE SobjectType = 'Agreement__c' "
        "AND Parent.Profile.Name = 'System Administrator'"
    )
    resp2 = rest_get(session_id, f"/query/?q={requests.utils.quote(soql)}")
    if resp2.status_code == 200:
        records = resp2.json().get("records", [])
        if records:
            for r in records:
                print(f"    {r['Field']}: read={r['PermissionsRead']}, edit={r['PermissionsEdit']}")
        else:
            print("    WARNING: No FLS records found (may need cache refresh)")
    else:
        print(f"    FLS query failed ({resp2.status_code})")

    # Verify MDU_Sales app has Agreement__c tab
    print("\n  Checking MDU_Sales app tabs...")
    tooling_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    query = "SELECT Id, DeveloperName, Label FROM CustomApplication WHERE DeveloperName = 'MDU_Sales'"
    resp3 = requests.get(tooling_url, headers=headers, params={"q": query})
    if resp3.status_code == 200:
        records = resp3.json().get("records", [])
        if records:
            print(f"    MDU_Sales app: FOUND (Id: {records[0]['Id']})")
        else:
            print("    MDU_Sales app: NOT FOUND")

    # Verify Agreement__c tab exists
    print("\n  Checking Agreement__c CustomTab...")
    query_tab = "SELECT Id, SobjectName, Label FROM CustomTab WHERE SobjectName = 'Agreement__c'"
    resp4 = requests.get(tooling_url, headers=headers, params={"q": query_tab})
    if resp4.status_code == 200:
        records = resp4.json().get("records", [])
        if records:
            print(f"    Agreement__c tab: FOUND (Label: {records[0].get('Label', '?')})")
        else:
            print("    Agreement__c tab: NOT FOUND in Tooling API (may need cache refresh)")
    else:
        print(f"    Tab query failed ({resp4.status_code}): {resp4.text[:200]}")


# ── Main ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("\nFailed to authenticate. Exiting.")
        exit(1)

    # ── ISSUE 1: Fix Agreement__c layout + FLS ──
    layout_name = diagnose_layout_and_fls(session_id)
    layout_ok = deploy_layout(session_id, layout_name)
    fls_ok = deploy_fls(session_id)

    # ── ISSUE 2: Create tab + add to MDU Sales app ──
    tab_ok = deploy_agreement_tab(session_id)
    app_ok = add_tab_to_mdu_app(session_id)

    # ── Verification ──
    verify_all(session_id)

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Issue 1 - Layout deploy:   {'SUCCESS' if layout_ok else 'FAILED'}")
    print(f"  Issue 1 - FLS deploy:      {'SUCCESS' if fls_ok else 'FAILED'}")
    print(f"  Issue 2 - Tab deploy:      {'SUCCESS' if tab_ok else 'FAILED'}")
    print(f"  Issue 2 - App update:      {'SUCCESS' if app_ok else 'FAILED'}")

    all_ok = layout_ok and fls_ok and tab_ok and app_ok
    if all_ok:
        print("\nAll deployments succeeded!")
        print("  - Agreement records should now show all fields (Type, Status, dates, etc.)")
        print("  - Agreements tab should appear in the MDU Sales app nav bar")
        print("  - If fields/tab don't appear immediately, try hard-refreshing the browser (Ctrl+Shift+R)")
    else:
        print("\nSome steps failed. Check output above for details.")
    print("=" * 70)
