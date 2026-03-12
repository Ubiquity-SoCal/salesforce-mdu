"""
Fix MDU Sales Lightning App visibility in Salesforce App Switcher.

Steps:
1. Authenticate via SOAP
2. Query AppMenu to check if MDU Sales appears in app switcher
3. Query Tooling API for CustomApplication to see if MDU_Sales exists
4. If exists but not visible: deploy profile visibility via Metadata API
5. If doesn't exist: create it fresh via Metadata API deploy (ZIP)
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
    print("STEP 1: AUTHENTICATING")
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


# ── Step 2: Check AppMenu / App Switcher ────────────────────────────────
def check_app_menu(session_id):
    print("\n" + "=" * 70)
    print("STEP 2: CHECKING APP MENU / APP SWITCHER")
    print("=" * 70)

    # Try the AppMenuItem endpoint
    resp = rest_get(session_id, "/appMenu/AppSwitcher")
    mdu_in_switcher = False
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("appMenuItems", [])
        print(f"  Found {len(items)} apps in AppSwitcher:")
        for item in items:
            label = item.get("label", "?")
            dev_name = item.get("name", "?")
            app_type = item.get("type", "?")
            marker = " <-- MDU SALES" if "mdu" in label.lower() else ""
            print(f"    - {label} ({dev_name}) [{app_type}]{marker}")
            if "mdu" in label.lower():
                mdu_in_switcher = True
    else:
        print(f"  AppSwitcher query failed ({resp.status_code}): {resp.text[:300]}")

    if mdu_in_switcher:
        print("\n  RESULT: MDU Sales IS in the App Switcher already.")
    else:
        print("\n  RESULT: MDU Sales is NOT in the App Switcher.")

    return mdu_in_switcher


# ── Step 3: Query Tooling API for CustomApplication ─────────────────────
def check_tooling_api(session_id):
    print("\n" + "=" * 70)
    print("STEP 3: CHECKING TOOLING API FOR MDU_SALES CUSTOM APPLICATION")
    print("=" * 70)

    tooling_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}

    # Query for MDU_Sales
    query = "SELECT Id, DeveloperName, Label, UiType, NavType, Description FROM CustomApplication WHERE DeveloperName = 'MDU_Sales'"
    resp = requests.get(tooling_url, headers=headers, params={"q": query})

    app_exists = False
    app_record = None

    if resp.status_code == 200:
        records = resp.json().get("records", [])
        if records:
            app_record = records[0]
            app_exists = True
            print(f"  FOUND: MDU_Sales CustomApplication")
            print(f"    Id:            {app_record.get('Id')}")
            print(f"    DeveloperName: {app_record.get('DeveloperName')}")
            print(f"    Label:         {app_record.get('Label')}")
            print(f"    UiType:        {app_record.get('UiType')}")
            print(f"    NavType:       {app_record.get('NavType')}")
        else:
            print("  NOT FOUND: No CustomApplication with DeveloperName='MDU_Sales'")
    else:
        print(f"  Tooling query failed ({resp.status_code}): {resp.text[:300]}")

    # Also check for any app with 'MDU' in the name
    query2 = "SELECT Id, DeveloperName, Label, UiType, NavType FROM CustomApplication WHERE Label LIKE '%MDU%'"
    resp2 = requests.get(tooling_url, headers=headers, params={"q": query2})
    if resp2.status_code == 200:
        records2 = resp2.json().get("records", [])
        if records2:
            print(f"\n  All apps matching 'MDU' in label:")
            for r in records2:
                print(f"    - {r.get('Label')} (DeveloperName={r.get('DeveloperName')}, UiType={r.get('UiType')})")

    # Also check FlexiPage for any MDU-related pages
    query3 = "SELECT Id, DeveloperName, MasterLabel, Type FROM FlexiPage WHERE MasterLabel LIKE '%MDU%'"
    resp3 = requests.get(tooling_url, headers=headers, params={"q": query3})
    if resp3.status_code == 200:
        records3 = resp3.json().get("records", [])
        if records3:
            print(f"\n  FlexiPages matching 'MDU':")
            for r in records3:
                print(f"    - {r.get('MasterLabel')} ({r.get('DeveloperName')}, Type={r.get('Type')})")
        else:
            print("\n  No FlexiPages matching 'MDU' found.")

    return app_exists, app_record


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

    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"}
    resp = requests.post(metadata_url, data=deploy_soap, headers=headers)

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
        print(f"  Could not find deploy ID. Response: {resp.text[:1000]}")
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

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"}
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
                # Print error details
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


# ── Step 4: Deploy profile visibility for existing app ──────────────────
def deploy_profile_visibility(session_id):
    print("\n" + "=" * 70)
    print("STEP 4a: DEPLOYING PROFILE VISIBILITY FOR MDU_SALES")
    print("=" * 70)
    print("  Adding MDU_Sales as visible+default for System Administrator profile")

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Admin</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <applicationVisibilities>
        <application>MDU_Sales</application>
        <default>false</default>
        <visible>true</visible>
    </applicationVisibilities>
</Profile>"""

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "profiles/Admin.profile": profile_xml,
    }, "System Administrator profile visibility for MDU_Sales")


# ── Step 5: Create the app fresh with profile visibility ────────────────
def create_mdu_app_fresh(session_id):
    print("\n" + "=" * 70)
    print("STEP 5: CREATING MDU SALES LIGHTNING APP (FRESH)")
    print("=" * 70)

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales</members>
        <name>CustomApplication</name>
    </types>
    <types>
        <members>Admin</members>
        <name>Profile</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    app_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MDU Sales</label>
    <formFactors>Large</formFactors>
    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>
    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>
    <isNavTabPersistenceDisabled>false</isNavTabPersistenceDisabled>
    <navType>Standard</navType>
    <uiType>Lightning</uiType>
    <tabs>standard-Opportunity</tabs>
    <tabs>standard-Account</tabs>
    <tabs>standard-Contact</tabs>
    <tabs>standard-report</tabs>
    <tabs>standard-Dashboard</tabs>
</CustomApplication>"""

    profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <applicationVisibilities>
        <application>MDU_Sales</application>
        <default>true</default>
        <visible>true</visible>
    </applicationVisibilities>
</Profile>"""

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "applications/MDU_Sales.app": app_xml,
        "profiles/Admin.profile": profile_xml,
    }, "MDU Sales Lightning App + System Administrator visibility")


# ── Final verification ──────────────────────────────────────────────────
def verify_final(session_id):
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)

    # Check Tooling API
    tooling_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    query = "SELECT Id, DeveloperName, Label, UiType, NavType FROM CustomApplication WHERE DeveloperName = 'MDU_Sales'"
    resp = requests.get(tooling_url, headers=headers, params={"q": query})
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        if records:
            r = records[0]
            print(f"  Tooling API: MDU_Sales FOUND")
            print(f"    Id:      {r.get('Id')}")
            print(f"    Label:   {r.get('Label')}")
            print(f"    UiType:  {r.get('UiType')}")
            print(f"    NavType: {r.get('NavType')}")
        else:
            print("  Tooling API: MDU_Sales NOT FOUND (this is a problem)")

    # Check AppSwitcher
    resp2 = rest_get(session_id, "/appMenu/AppSwitcher")
    if resp2.status_code == 200:
        items = resp2.json().get("appMenuItems", [])
        mdu_found = False
        for item in items:
            if "mdu" in item.get("label", "").lower():
                mdu_found = True
                print(f"  AppSwitcher: '{item.get('label')}' FOUND (type={item.get('type')})")
                break
        if not mdu_found:
            print("  AppSwitcher: MDU Sales NOT visible yet")
            print("  NOTE: It may take a few minutes or require a page refresh in Salesforce.")
            print("  Try: Setup > App Manager to confirm, then refresh the browser.")
    else:
        print(f"  AppSwitcher check failed ({resp2.status_code})")


# ── Main ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("Authentication failed. Exiting.")
        exit(1)

    # Step 2: Check app switcher
    in_switcher = check_app_menu(session_id)

    # Step 3: Check Tooling API
    app_exists, app_record = check_tooling_api(session_id)

    # Decision logic
    if in_switcher:
        print("\n" + "=" * 70)
        print("MDU Sales is already visible in the App Switcher. No fix needed.")
        print("=" * 70)
    elif app_exists:
        # App exists in metadata but isn't showing in switcher -> profile visibility issue
        print("\n" + "-" * 70)
        print("DIAGNOSIS: App exists but is NOT visible in App Switcher.")
        print("FIX: Deploying profile visibility for System Administrator...")
        print("-" * 70)
        ok = deploy_profile_visibility(session_id)
        if not ok:
            print("  Profile-only deploy failed. Trying full app + profile redeploy...")
            ok = create_mdu_app_fresh(session_id)
    else:
        # App doesn't exist at all -> create fresh
        print("\n" + "-" * 70)
        print("DIAGNOSIS: MDU_Sales CustomApplication does NOT exist.")
        print("FIX: Creating it fresh with profile visibility...")
        print("-" * 70)
        ok = create_mdu_app_fresh(session_id)

    # Final verification
    verify_final(session_id)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
