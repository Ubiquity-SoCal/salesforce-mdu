"""
Setup Agreement__c Page Layout and Field-Level Security.

1. Retrieve current Agreement__c layout name via Metadata API
2. Deploy rebuilt layout with proper sections:
   - Agreement Information (2-col)
   - Dates (2-col)
   - Signer (2-col)
   - Notes (1-col)
   - System Information (2-col)
3. Deploy FLS: visible+editable for System Administrator and Standard User profiles
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
API_VERSION_NUM = "59.0"
MD_NS = "http://soap.sforce.com/2006/04/metadata"


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


# ── Discover the Agreement__c layout name ──────────────────────────────
def discover_layout_name(session_id):
    """Retrieve Agreement__c layouts to find the actual layout name."""
    print("\n" + "=" * 70)
    print("STEP 1: DISCOVER AGREEMENT__C LAYOUT NAME")
    print("=" * 70)

    # Use wildcard to get all Agreement__c layouts
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
            print(f"  ZIP entry: {name}")
            if name.endswith(".layout"):
                # Extract layout name from path: layouts/Agreement__c-Something.layout
                basename = name.split("/")[-1].replace(".layout", "")
                layout_name = basename
                print(f"  Found layout: {layout_name}")

    if not layout_name:
        # Try the standard default name
        print("  No layout found via wildcard. Trying 'Agreement__c-Agreement Layout'...")
        layout_name = "Agreement__c-Agreement Layout"

        # Verify it exists
        package_inner2 = f"""
              <types>
                <members>{layout_name}</members>
                <name>Layout</name>
              </types>"""
        zip_bytes2 = retrieve_metadata(session_id, package_inner2)
        if zip_bytes2:
            zf2 = zipfile.ZipFile(io.BytesIO(zip_bytes2))
            found = False
            for name in zf2.namelist():
                print(f"  ZIP entry: {name}")
                if name.endswith(".layout"):
                    found = True
            if not found:
                # Last resort: the auto-generated name
                layout_name = "Agreement__c-Agreement__c Layout"
                print(f"  Falling back to: {layout_name}")

    print(f"\n  Using layout name: {layout_name}")
    return layout_name


# ── Build the Agreement__c layout XML ──────────────────────────────────
def build_layout_xml(layout_name):
    """Build a complete Agreement__c page layout XML."""

    # The layout file name uses the full "Object-Layout Name" format
    # but the XML <fullName> should NOT include the object prefix — just the layout label
    # Actually for Metadata API, <fullName> IS "Object-Layout Name"

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
        <style>TwoColumnsLeftToRight</style>
        <layoutColumns>
            <layoutItems>
                <behavior>Edit</behavior>
                <field>Signer__c</field>
            </layoutItems>
        </layoutColumns>
        <layoutColumns/>
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

    return layout_xml


# ── Build FLS Profile XML ─────────────────────────────────────────────
def build_profile_xml(profile_name, custom_fields):
    """Build a Profile metadata XML that sets FLS for Agreement__c fields."""
    field_perms = ""
    for field in custom_fields:
        field_perms += f"""
    <fieldPermissions>
        <editable>true</editable>
        <field>Agreement__c.{field}</field>
        <readable>true</readable>
    </fieldPermissions>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">{field_perms}
</Profile>"""


# ── Deploy Layout ──────────────────────────────────────────────────────
def deploy_layout(session_id, layout_name):
    print("\n" + "=" * 70)
    print("STEP 2: DEPLOY AGREEMENT__C PAGE LAYOUT")
    print("=" * 70)

    layout_xml = build_layout_xml(layout_name)

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>{layout_name}</members>
        <name>Layout</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    # The file path in the ZIP must match: layouts/<LayoutFullName>.layout
    layout_file_path = f"layouts/{layout_name}.layout"

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        layout_file_path: layout_xml,
    }, "Agreement__c Page Layout")


# ── Deploy FLS ─────────────────────────────────────────────────────────
def deploy_fls(session_id):
    print("\n" + "=" * 70)
    print("STEP 3: DEPLOY FIELD-LEVEL SECURITY")
    print("=" * 70)

    custom_fields = [
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

    profiles = {
        "Admin": "System Administrator",
        "Standard": "Standard User",
    }

    files = {
        "package.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Admin</members>
        <members>Standard</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""
    }

    for api_name, display_name in profiles.items():
        files[f"profiles/{api_name}.profile"] = build_profile_xml(display_name, custom_fields)
        print(f"  Built FLS for profile: {display_name} (API: {api_name})")

    return deploy_metadata_package(session_id, files, "Field-Level Security for Agreement__c")


# ── Main ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("\nFailed to authenticate. Exiting.")
        exit(1)

    # Step 1: Discover the layout name
    layout_name = discover_layout_name(session_id)

    # Step 2: Deploy the rebuilt layout
    layout_ok = deploy_layout(session_id, layout_name)

    # Step 3: Deploy FLS
    fls_ok = deploy_fls(session_id)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Layout deploy: {'SUCCESS' if layout_ok else 'FAILED'}")
    print(f"  FLS deploy:    {'SUCCESS' if fls_ok else 'FAILED'}")

    if layout_ok and fls_ok:
        print("\nAll done! Agreement__c layout and FLS updated successfully.")
    else:
        print("\nSome steps failed. Check output above for details.")
    print("=" * 70)
