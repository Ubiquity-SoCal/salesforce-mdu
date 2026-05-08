"""
Build MDU Sales Lightning App in Salesforce
- Authenticates via SOAP API
- Updates Opportunity Stage picklist via Metadata API
- Creates custom fields on Opportunity via Metadata API
- Creates MDU Sales Lightning App via Metadata API

Uses the Metadata API deploy with a ZIP package for all changes.
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


def rest_get(session_id, path):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers)
    return resp


def rest_post(session_id, path, data):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {
        "Authorization": f"Bearer {session_id}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(url, headers=headers, json=data)
    return resp


def rest_patch(session_id, path, data):
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {
        "Authorization": f"Bearer {session_id}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.patch(url, headers=headers, json=data)
    return resp


# ── Step 1: Create Custom Fields via Tooling API ───────────────────────
def create_custom_fields(session_id):
    print("\n" + "=" * 70)
    print("CREATING CUSTOM FIELDS ON OPPORTUNITY")
    print("=" * 70)

    fields = [
        {
            "FullName": "Opportunity.Units__c",
            "Metadata": {
                "label": "Units",
                "type": "Number",
                "precision": 18,
                "scale": 0,
                "description": "Number of units in the property",
                "inlineHelpText": "Number of units in the property",
            },
        },
        {
            "FullName": "Opportunity.Property_Type__c",
            "Metadata": {
                "label": "Property Type",
                "type": "Picklist",
                "description": "Type of property",
                "valueSet": {
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "Apartment", "default": False, "label": "Apartment"},
                            {"fullName": "Condo", "default": False, "label": "Condo"},
                            {"fullName": "Townhome", "default": False, "label": "Townhome"},
                            {"fullName": "Manufactured Home Park", "default": False, "label": "Manufactured Home Park"},
                            {"fullName": "Senior Living", "default": False, "label": "Senior Living"},
                            {"fullName": "Student Housing", "default": False, "label": "Student Housing"},
                            {"fullName": "Mixed Use", "default": False, "label": "Mixed Use"},
                            {"fullName": "Other", "default": False, "label": "Other"},
                        ],
                    }
                },
            },
        },
        {
            "FullName": "Opportunity.Property_Category__c",
            "Metadata": {
                "label": "Property Category",
                "type": "Picklist",
                "description": "Property category",
                "valueSet": {
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "MDU", "default": False, "label": "MDU"},
                            {"fullName": "SFU", "default": False, "label": "SFU"},
                            {"fullName": "MHP", "default": False, "label": "MHP"},
                        ],
                    }
                },
            },
        },
        {
            "FullName": "Opportunity.Build_Type__c",
            "Metadata": {
                "label": "Build Type",
                "type": "Picklist",
                "description": "Build type - brownfield or greenfield",
                "valueSet": {
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "Brownfield", "default": False, "label": "Brownfield"},
                            {"fullName": "Greenfield", "default": False, "label": "Greenfield"},
                        ],
                    }
                },
            },
        },
        {
            "FullName": "Opportunity.Prospective_ISP__c",
            "Metadata": {
                "label": "Prospective ISP",
                "type": "Text",
                "length": 255,
                "description": "Prospective ISP name(s)",
            },
        },
        {
            "FullName": "Opportunity.Confirmed_ISP__c",
            "Metadata": {
                "label": "Confirmed ISP",
                "type": "Text",
                "length": 255,
                "description": "Confirmed ISP name(s)",
            },
        },
        {
            "FullName": "Opportunity.Property_Address__c",
            "Metadata": {
                "label": "Property Address",
                "type": "Text",
                "length": 255,
                "description": "Street address of the property",
            },
        },
        {
            "FullName": "Opportunity.Property_City__c",
            "Metadata": {
                "label": "Property City",
                "type": "Text",
                "length": 100,
                "description": "City of the property",
            },
        },
        {
            "FullName": "Opportunity.Property_State__c",
            "Metadata": {
                "label": "Property State",
                "type": "Text",
                "length": 50,
                "description": "State of the property",
            },
        },
        {
            "FullName": "Opportunity.Property_Zip__c",
            "Metadata": {
                "label": "Property Zip",
                "type": "Text",
                "length": 10,
                "description": "Zip code of the property",
            },
        },
        {
            "FullName": "Opportunity.Monday_Item_ID__c",
            "Metadata": {
                "label": "Monday Item ID",
                "type": "Text",
                "length": 50,
                "externalId": True,
                "unique": False,
                "description": "Monday.com source item ID for migration tracking",
            },
        },
    ]

    results = {"success": [], "failed": [], "skipped": []}

    for field_def in fields:
        field_name = field_def["FullName"].split(".")[-1]
        print(f"\n  Creating {field_name}...", end=" ")

        # First check if field already exists
        check = rest_get(session_id, f"/sobjects/Opportunity/describe/")
        if check.status_code == 200:
            existing_fields = [f["name"] for f in check.json().get("fields", [])]
            if field_name in existing_fields:
                print("SKIPPED (already exists)")
                results["skipped"].append(field_name)
                continue

        # Create via Tooling API
        resp = rest_post(session_id, "/tooling/sobjects/CustomField/", field_def)

        if resp.status_code in (200, 201):
            print("SUCCESS")
            results["success"].append(field_name)
        else:
            error_msg = resp.text[:300]
            # Check if it's a duplicate error
            if "DUPLICATE" in error_msg.upper() or "already exists" in error_msg.lower():
                print("SKIPPED (already exists)")
                results["skipped"].append(field_name)
            else:
                print(f"FAILED ({resp.status_code})")
                print(f"    Error: {error_msg}")
                results["failed"].append((field_name, error_msg))

        # Small delay between API calls
        time.sleep(1)

    return results


# ── Step 2: Update Opportunity Stages via Metadata API (SOAP) ─────────
def update_opportunity_stages(session_id):
    print("\n" + "=" * 70)
    print("UPDATING OPPORTUNITY STAGE PICKLIST")
    print("=" * 70)

    # Use Metadata API SOAP to update the OpportunityStage standard value set
    # We need to use the Metadata API deploy with a ZIP package

    # Build the package.xml and standardValueSet XML
    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpportunityStage</members>
        <name>StandardValueSet</name>
    </types>
    <version>{API_VERSION_NUM}</version>
</Package>"""

    # StandardValueSet for OpportunityStage
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
        <fullName>Engineering</fullName>
        <default>false</default>
        <label>Engineering</label>
        <closed>false</closed>
        <forecastCategory>BestCase</forecastCategory>
        <probability>70</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Construction</fullName>
        <default>false</default>
        <label>Construction</label>
        <closed>false</closed>
        <forecastCategory>BestCase</forecastCategory>
        <probability>80</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Activation</fullName>
        <default>false</default>
        <label>Activation</label>
        <closed>false</closed>
        <forecastCategory>BestCase</forecastCategory>
        <probability>90</probability>
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

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "standardValueSets/OpportunityStage.standardValueSet": stage_xml,
    }, "Opportunity Stage picklist")


# ── Step 3: Create Lightning App via Metadata API ─────────────────────
def create_lightning_app(session_id):
    print("\n" + "=" * 70)
    print("CREATING MDU SALES LIGHTNING APP")
    print("=" * 70)

    package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Sales</members>
        <name>CustomApplication</name>
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

    return deploy_metadata_package(session_id, {
        "package.xml": package_xml,
        "applications/MDU_Sales.app": app_xml,
    }, "MDU Sales Lightning App")


# ── Metadata API Deploy Helper ────────────────────────────────────────
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

    # Poll for completion
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

        # Get done status
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
                for err in root.iter():
                    if "problem" in err.tag.lower() or "message" in err.tag.lower():
                        if err.text:
                            print(f"    Error: {err.text}")
                    if "componentType" in err.tag or "fullName" in err.tag:
                        if err.text:
                            print(f"    Component: {err.text}")
                # Also dump a chunk of response for debugging
                resp_text = resp.text
                if "componentFailures" in resp_text:
                    # Extract failure info
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


# ── Verify Results ────────────────────────────────────────────────────
def verify_results(session_id):
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Check Opportunity fields
    print("\n  Checking Opportunity custom fields...")
    resp = rest_get(session_id, "/sobjects/Opportunity/describe/")
    if resp.status_code == 200:
        fields = resp.json().get("fields", [])
        custom_fields = [f for f in fields if f["name"].endswith("__c")]
        expected = [
            "Units__c", "Property_Type__c", "Property_Category__c",
            "Build_Type__c", "Prospective_ISP__c", "Confirmed_ISP__c",
            "Property_Address__c", "Property_City__c", "Property_State__c",
            "Property_Zip__c", "Monday_Item_ID__c",
        ]
        found = [f["name"] for f in custom_fields]
        for exp in expected:
            status = "FOUND" if exp in found else "MISSING"
            print(f"    {exp}: {status}")

    # Check stages
    print("\n  Checking Opportunity Stage values...")
    if resp.status_code == 200:
        stage_field = next((f for f in fields if f["name"] == "StageName"), None)
        if stage_field:
            picklist_values = [pv["value"] for pv in stage_field.get("picklistValues", [])]
            expected_stages = [
                "Prospecting", "Qualification", "Negotiation",
                "Engineering", "Construction", "Activation",
                "Closed Won", "Closed Lost",
            ]
            for stage in expected_stages:
                status = "FOUND" if stage in picklist_values else "MISSING"
                print(f"    {stage}: {status}")
            # Show all current stages
            print(f"\n  All current stage values: {picklist_values}")

    # Check Lightning App
    print("\n  Checking MDU Sales Lightning App...")
    tooling_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    query = "SELECT Id, DeveloperName, Label FROM CustomApplication WHERE DeveloperName = 'MDU_Sales'"
    app_resp = requests.get(tooling_url, headers=headers, params={"q": query})
    if app_resp.status_code == 200:
        records = app_resp.json().get("records", [])
        if records:
            print(f"    MDU Sales App: FOUND (Id: {records[0]['Id']})")
        else:
            print("    MDU Sales App: NOT FOUND")
    else:
        print(f"    Could not check app: {app_resp.status_code}")


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id = soap_login()
    if not session_id:
        print("Authentication failed. Exiting.")
        exit(1)

    # Step 1: Create custom fields
    field_results = create_custom_fields(session_id)

    print("\n" + "-" * 70)
    print("CUSTOM FIELD SUMMARY")
    print("-" * 70)
    print(f"  Created: {len(field_results['success'])} - {', '.join(field_results['success']) or 'none'}")
    print(f"  Skipped: {len(field_results['skipped'])} - {', '.join(field_results['skipped']) or 'none'}")
    if field_results['failed']:
        print(f"  Failed:  {len(field_results['failed'])}")
        for name, err in field_results['failed']:
            print(f"    - {name}: {err[:200]}")

    # Step 2: Update Opportunity Stages
    stages_ok = update_opportunity_stages(session_id)

    # Step 3: Create Lightning App
    app_ok = create_lightning_app(session_id)

    # Step 4: Verify everything
    verify_results(session_id)

    # Final summary
    print("\n" + "=" * 70)
    print("BUILD COMPLETE")
    print("=" * 70)
    print(f"  Custom Fields: {len(field_results['success'])} created, "
          f"{len(field_results['skipped'])} skipped, "
          f"{len(field_results['failed'])} failed")
    print(f"  Stage Picklist: {'SUCCESS' if stages_ok else 'FAILED'}")
    print(f"  Lightning App:  {'SUCCESS' if app_ok else 'FAILED'}")
