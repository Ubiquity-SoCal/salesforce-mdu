"""
Migration Phase 1 — Schema Updates
====================================
Prepares Salesforce for Monday.com data import:
  1. Create 7 new Opportunity fields
  2. Add new Opportunity stages (Engaged, Contract Negotiations, On Hold)
  3. Update Agreement__c picklist values (Status → IronClad, Type → expanded)
  4. Add fields to page layout
"""

import requests
import json
import time
import base64
import io
import zipfile
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"
PASSWORD_TOKEN = PASSWORD + SECURITY_TOKEN
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "v59.0"
API_VERSION_NUM = "59.0"

# ── Summary tracking ────────────────────────────────────────────────────
summary = {
    "fields_created": [],
    "fields_skipped": [],
    "fields_failed": [],
    "stages_deployed": False,
    "agreement_picklists_deployed": False,
    "layout_updated": False,
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
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"}
    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"SOAP login failed ({resp.status_code}): {resp.text[:500]}")
    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "sf": "urn:partner.soap.sforce.com",
    }
    root = ET.fromstring(resp.text)
    session_id = root.find(".//sf:sessionId", ns)
    if session_id is None:
        raise Exception("Could not find sessionId in SOAP response")
    return session_id.text


# ── Metadata API Deploy ─────────────────────────────────────────────────
def metadata_deploy(session_id, zip_bytes, label="deployment"):
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
        <met:allowMissingFiles>false</met:allowMissingFiles>
        <met:autoUpdatePackage>false</met:autoUpdatePackage>
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
    resp = requests.post(
        f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}",
        data=deploy_body, headers=headers,
    )
    if resp.status_code != 200:
        raise Exception(f"Deploy failed ({resp.status_code}): {resp.text[:1000]}")

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }
    root = ET.fromstring(resp.text)
    async_id = root.find(".//met:id", ns)
    if async_id is None:
        raise Exception(f"No async ID: {resp.text[:1000]}")

    deploy_id = async_id.text
    print(f"    Deploy initiated: {deploy_id}")

    for attempt in range(60):
        time.sleep(3)
        state, details = check_deploy_status(session_id, deploy_id)
        print(f"    Poll {attempt+1}: {state}")
        if state == "Succeeded":
            return True, details
        if state in ("Failed", "Canceled", "SucceededPartial"):
            return False, details

    raise Exception("Deploy timed out after 180 seconds")


def check_deploy_status(session_id, deploy_id):
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
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"}
    resp = requests.post(
        f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}",
        data=check_body, headers=headers,
    )
    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }
    root = ET.fromstring(resp.text)
    state_el = root.find(".//met:status", ns)
    state = state_el.text if state_el is not None else "Unknown"

    # Collect error messages if any
    details = []
    for msg in root.findall(".//met:componentFailures", ns):
        problem = msg.find("met:problem", ns)
        comp = msg.find("met:fullName", ns)
        details.append(f"{comp.text if comp is not None else '?'}: {problem.text if problem is not None else '?'}")

    return state, details


# ── Tooling API for custom fields ────────────────────────────────────────
def create_custom_field(session_id, object_name, field_def):
    """Create a custom field via Tooling API."""
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/sobjects/CustomField"
    headers = {
        "Authorization": f"Bearer {session_id}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(url, headers=headers, json=field_def)
    return resp


# ══════════════════════════════════════════════════════════════════════════
# TASK 1: Create new Opportunity fields
# ══════════════════════════════════════════════════════════════════════════
def task1_create_fields(session_id, sf):
    print("\n" + "=" * 60)
    print("TASK 1: Create new Opportunity fields")
    print("=" * 60)

    # Get Opportunity object ID for Tooling API
    resp = requests.get(
        f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query",
        params={"q": "SELECT Id FROM EntityDefinition WHERE QualifiedApiName = 'Opportunity'"},
        headers={"Authorization": f"Bearer {session_id}", "Accept": "application/json"},
    )
    entity_id = resp.json()["records"][0]["Id"]

    # Check existing fields
    opp_desc = sf.Opportunity.describe()
    existing = {f["name"] for f in opp_desc["fields"]}

    fields = [
        {
            "FullName": "Opportunity.Sales_Status__c",
            "Metadata": {
                "label": "Sales Status",
                "type": "Picklist",
                "required": False,
                "description": "Sub-status for Prospecting stage",
                "valueSet": {
                    "restricted": False,
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "Contact Pending", "default": False, "label": "Contact Pending"},
                            {"fullName": "Reached Out - Pending Response", "default": False, "label": "Reached Out - Pending Response"},
                        ],
                    },
                },
            },
        },
        {
            "FullName": "Opportunity.Hold_Reason__c",
            "Metadata": {
                "label": "Hold Reason",
                "type": "Picklist",
                "required": False,
                "description": "Required when Stage = On Hold",
                "valueSet": {
                    "restricted": False,
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "Ownership Change", "default": False, "label": "Ownership Change"},
                            {"fullName": "Budget / Timing", "default": False, "label": "Budget / Timing"},
                            {"fullName": "Pending Legal Review", "default": False, "label": "Pending Legal Review"},
                            {"fullName": "Market Conditions", "default": False, "label": "Market Conditions"},
                            {"fullName": "Other", "default": False, "label": "Other"},
                        ],
                    },
                },
            },
        },
        {
            "FullName": "Opportunity.Portfolio__c",
            "Metadata": {
                "label": "Portfolio",
                "type": "Lookup",
                "required": False,
                "description": "Portfolio company (Account lookup)",
                "referenceTo": "Account",
                "relationshipName": "Portfolio_Opportunities",
                "relationshipLabel": "Portfolio Opportunities",
            },
        },
        {
            "FullName": "Opportunity.Management_Company__c",
            "Metadata": {
                "label": "Management Company",
                "type": "Lookup",
                "required": False,
                "description": "Property management company (Account lookup)",
                "referenceTo": "Account",
                "relationshipName": "Managed_Opportunities",
                "relationshipLabel": "Managed Opportunities",
            },
        },
        {
            "FullName": "Opportunity.Incumbent_Provider__c",
            "Metadata": {
                "label": "Incumbent Provider",
                "type": "Text",
                "required": False,
                "length": 255,
                "description": "Current provider at the property",
            },
        },
        {
            "FullName": "Opportunity.Incumbent_Agreement_Type__c",
            "Metadata": {
                "label": "Incumbent Agreement Type",
                "type": "Picklist",
                "required": False,
                "description": "Type of existing agreement with incumbent provider",
                "valueSet": {
                    "restricted": False,
                    "valueSetDefinition": {
                        "sorted": False,
                        "value": [
                            {"fullName": "Exclusive", "default": False, "label": "Exclusive"},
                            {"fullName": "Non-Exclusive", "default": False, "label": "Non-Exclusive"},
                            {"fullName": "Bulk", "default": False, "label": "Bulk"},
                            {"fullName": "Unknown", "default": False, "label": "Unknown"},
                        ],
                    },
                },
            },
        },
        {
            "FullName": "Opportunity.Incumbent_Agreement_Expiration__c",
            "Metadata": {
                "label": "Incumbent Agreement Expiration",
                "type": "Date",
                "required": False,
                "description": "Expiration date of incumbent provider agreement",
            },
        },
    ]

    for field_def in fields:
        api_name = field_def["FullName"].split(".")[-1]
        if api_name in existing:
            print(f"  SKIP: {api_name} already exists")
            summary["fields_skipped"].append(api_name)
            continue

        print(f"  Creating: {api_name}...", end=" ")
        resp = create_custom_field(session_id, "Opportunity", field_def)

        if resp.status_code == 201:
            print("OK")
            summary["fields_created"].append(api_name)
        else:
            error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:300]
            print(f"FAILED: {error}")
            summary["fields_failed"].append((api_name, str(error)))


# ══════════════════════════════════════════════════════════════════════════
# TASK 2: Update Opportunity Stages
# ══════════════════════════════════════════════════════════════════════════
def task2_update_stages(session_id):
    print("\n" + "=" * 60)
    print("TASK 2: Update Opportunity Stages")
    print("=" * 60)

    # Deploy standardValueSet for OpportunityStage
    # Keep all existing stages (Business needs them) + add new ones
    stages_xml = """<?xml version="1.0" encoding="UTF-8"?>
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
        <fullName>Engaged</fullName>
        <default>false</default>
        <label>Engaged</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>30</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Contract Negotiations</fullName>
        <default>false</default>
        <label>Contract Negotiations</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>50</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Under Contract</fullName>
        <default>false</default>
        <label>Under Contract</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>100</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>On Hold</fullName>
        <default>false</default>
        <label>On Hold</label>
        <closed>false</closed>
        <forecastCategory>Omitted</forecastCategory>
        <probability>0</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Ready for Engineering</fullName>
        <default>false</default>
        <label>Ready for Engineering</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>50</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Under Construction</fullName>
        <default>false</default>
        <label>Under Construction</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>75</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Activation</fullName>
        <default>false</default>
        <label>Activation</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
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

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpportunityStage</members>
        <name>StandardValueSet</name>
    </types>
    <version>59.0</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("standardValueSets/OpportunityStage.standardValueSet", stages_xml)
        zf.writestr("package.xml", package_xml)

    print("  Deploying updated stages (adding Engaged, Contract Negotiations, On Hold)...")
    success, details = metadata_deploy(session_id, buf.getvalue(), "stages")

    if success:
        print("  Stages deployed successfully!")
        summary["stages_deployed"] = True
    else:
        print(f"  Stage deploy FAILED: {details}")
        summary["stages_deployed"] = False


# ══════════════════════════════════════════════════════════════════════════
# TASK 3: Update Agreement__c Picklists
# ══════════════════════════════════════════════════════════════════════════
def task3_update_agreement_picklists(session_id):
    print("\n" + "=" * 60)
    print("TASK 3: Update Agreement__c Picklists")
    print("=" * 60)

    # Status__c → IronClad stages
    status_field_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Status__c</fullName>
    <label>Status</label>
    <type>Picklist</type>
    <required>false</required>
    <valueSet>
        <restricted>false</restricted>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>Create</fullName><default>false</default><label>Create</label></value>
            <value><fullName>Review</fullName><default>false</default><label>Review</label></value>
            <value><fullName>Sign</fullName><default>false</default><label>Sign</label></value>
            <value><fullName>Completed</fullName><default>false</default><label>Completed</label></value>
            <value><fullName>Archive</fullName><default>false</default><label>Archive</label></value>
            <value><fullName>Paused</fullName><default>false</default><label>Paused</label></value>
            <value><fullName>Cancelled</fullName><default>false</default><label>Cancelled</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>"""

    # Agreement_Type__c → expanded list
    type_field_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Agreement_Type__c</fullName>
    <label>Agreement Type</label>
    <type>Picklist</type>
    <required>false</required>
    <valueSet>
        <restricted>false</restricted>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>PAL</fullName><default>false</default><label>PAL</label></value>
            <value><fullName>ROE</fullName><default>false</default><label>ROE</label></value>
            <value><fullName>EMA</fullName><default>false</default><label>EMA</label></value>
            <value><fullName>Bulk</fullName><default>false</default><label>Bulk</label></value>
            <value><fullName>NEMA</fullName><default>false</default><label>NEMA</label></value>
            <value><fullName>PAL Addendum</fullName><default>false</default><label>PAL Addendum</label></value>
            <value><fullName>MSA Addendum</fullName><default>false</default><label>MSA Addendum</label></value>
            <value><fullName>2nd ISP NEMA</fullName><default>false</default><label>2nd ISP NEMA</label></value>
            <value><fullName>2nd ISP MSA Addendum</fullName><default>false</default><label>2nd ISP MSA Addendum</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>"""

    # Object metadata (required for field deploy)
    object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Status__c</fullName>
        <label>Status</label>
        <type>Picklist</type>
        <required>false</required>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Create</fullName><default>false</default><label>Create</label></value>
                <value><fullName>Review</fullName><default>false</default><label>Review</label></value>
                <value><fullName>Sign</fullName><default>false</default><label>Sign</label></value>
                <value><fullName>Completed</fullName><default>false</default><label>Completed</label></value>
                <value><fullName>Archive</fullName><default>false</default><label>Archive</label></value>
                <value><fullName>Paused</fullName><default>false</default><label>Paused</label></value>
                <value><fullName>Cancelled</fullName><default>false</default><label>Cancelled</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
    <fields>
        <fullName>Agreement_Type__c</fullName>
        <label>Agreement Type</label>
        <type>Picklist</type>
        <required>false</required>
        <valueSet>
            <restricted>false</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>PAL</fullName><default>false</default><label>PAL</label></value>
                <value><fullName>ROE</fullName><default>false</default><label>ROE</label></value>
                <value><fullName>EMA</fullName><default>false</default><label>EMA</label></value>
                <value><fullName>Bulk</fullName><default>false</default><label>Bulk</label></value>
                <value><fullName>NEMA</fullName><default>false</default><label>NEMA</label></value>
                <value><fullName>PAL Addendum</fullName><default>false</default><label>PAL Addendum</label></value>
                <value><fullName>MSA Addendum</fullName><default>false</default><label>MSA Addendum</label></value>
                <value><fullName>2nd ISP NEMA</fullName><default>false</default><label>2nd ISP NEMA</label></value>
                <value><fullName>2nd ISP MSA Addendum</fullName><default>false</default><label>2nd ISP MSA Addendum</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Agreement__c</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("objects/Agreement__c.object", object_xml)
        zf.writestr("package.xml", package_xml)

    print("  Deploying Agreement__c picklist updates...")
    print("    Status__c -> IronClad stages (Create/Review/Sign/Completed/Archive/Paused/Cancelled)")
    print("    Agreement_Type__c -> adding NEMA, PAL Addendum, MSA Addendum, 2nd ISP NEMA, 2nd ISP MSA Addendum")
    success, details = metadata_deploy(session_id, buf.getvalue(), "agreement_picklists")

    if success:
        print("  Agreement picklists deployed successfully!")
        summary["agreement_picklists_deployed"] = True
    else:
        print(f"  Agreement picklist deploy FAILED: {details}")
        summary["agreement_picklists_deployed"] = False


# ══════════════════════════════════════════════════════════════════════════
# TASK 4: Add fields to page layout
# ══════════════════════════════════════════════════════════════════════════
def task4_update_layout(sf):
    print("\n" + "=" * 60)
    print("TASK 4: Add new fields to Opportunity page layout")
    print("=" * 60)

    layout_id = "00hHs00000dMIY9IAO"

    # Read current layout
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/sobjects/Layout/{layout_id}"
    headers = {
        "Authorization": f"Bearer {sf.session_id}",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        print(f"  Failed to read layout: {resp.status_code}")
        return

    layout = resp.json()
    metadata = layout.get("Metadata", {})
    sections = metadata.get("layoutSections", [])

    # Find the right sections to add fields to
    # Add Sales Status + Hold Reason near Stage (Opportunity Information section)
    # Add Portfolio + Management Company in their own section
    # Add Incumbent fields in their own section

    new_fields_added = []

    # Add to Opportunity Information section (first section usually)
    for section in sections:
        label = section.get("label", "")
        if label == "Opportunity Information":
            # Add Sales_Status__c and Hold_Reason__c
            columns = section.get("layoutColumns", [])
            if columns:
                # Add to second column if exists, else first
                col_idx = 1 if len(columns) > 1 else 0
                items = columns[col_idx].get("layoutItems", [])
                for field_name in ["Sales_Status__c", "Hold_Reason__c"]:
                    if not any(item.get("field") == field_name for item in items):
                        items.append({
                            "behavior": "Edit",
                            "field": field_name,
                        })
                        new_fields_added.append(field_name)
                columns[col_idx]["layoutItems"] = items
            break

    # Add new sections for Portfolio/Mgmt Co and Incumbent fields
    # Check if sections already exist
    existing_labels = {s.get("label", "") for s in sections}

    if "Portfolio & Management" not in existing_labels:
        portfolio_section = {
            "customLabel": True,
            "detailHeading": True,
            "editHeading": True,
            "label": "Portfolio & Management",
            "layoutColumns": [
                {
                    "layoutItems": [
                        {"behavior": "Edit", "field": "Portfolio__c"},
                    ]
                },
                {
                    "layoutItems": [
                        {"behavior": "Edit", "field": "Management_Company__c"},
                    ]
                },
            ],
            "style": "TwoColumnsLeftToRight",
        }
        # Insert before the last section (usually Related Lists)
        sections.insert(-1, portfolio_section)
        new_fields_added.extend(["Portfolio__c", "Management_Company__c"])

    if "Incumbent Provider" not in existing_labels:
        incumbent_section = {
            "customLabel": True,
            "detailHeading": True,
            "editHeading": True,
            "label": "Incumbent Provider",
            "layoutColumns": [
                {
                    "layoutItems": [
                        {"behavior": "Edit", "field": "Incumbent_Provider__c"},
                        {"behavior": "Edit", "field": "Incumbent_Agreement_Expiration__c"},
                    ]
                },
                {
                    "layoutItems": [
                        {"behavior": "Edit", "field": "Incumbent_Agreement_Type__c"},
                    ]
                },
            ],
            "style": "TwoColumnsLeftToRight",
        }
        sections.insert(-1, incumbent_section)
        new_fields_added.extend(["Incumbent_Provider__c", "Incumbent_Agreement_Type__c", "Incumbent_Agreement_Expiration__c"])

    if not new_fields_added:
        print("  All fields already on layout — skipping")
        summary["layout_updated"] = True
        return

    # Update the layout
    metadata["layoutSections"] = sections
    update_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/sobjects/Layout/{layout_id}"
    update_resp = requests.patch(
        update_url,
        headers={
            "Authorization": f"Bearer {sf.session_id}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={"Metadata": metadata},
    )

    if update_resp.status_code == 204:
        print(f"  Layout updated! Added: {', '.join(new_fields_added)}")
        summary["layout_updated"] = True
    else:
        error = update_resp.text[:500]
        print(f"  Layout update FAILED ({update_resp.status_code}): {error}")
        summary["layout_updated"] = False


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
def main():
    print("Migration Phase 1 — Schema Updates")
    print("=" * 60)

    print("\nLogging in...")
    session_id = soap_login()
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("  Logged in successfully")

    # Run tasks in order
    task1_create_fields(session_id, sf)
    task2_update_stages(session_id)
    task3_update_agreement_picklists(session_id)
    task4_update_layout(sf)

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Fields created:  {len(summary['fields_created'])} — {summary['fields_created']}")
    print(f"  Fields skipped:  {len(summary['fields_skipped'])} — {summary['fields_skipped']}")
    print(f"  Fields failed:   {len(summary['fields_failed'])} — {summary['fields_failed']}")
    print(f"  Stages deployed: {summary['stages_deployed']}")
    print(f"  Agreement picklists: {summary['agreement_picklists_deployed']}")
    print(f"  Layout updated:  {summary['layout_updated']}")

    if summary["fields_failed"]:
        print("\n  FIELD FAILURES:")
        for name, err in summary["fields_failed"]:
            print(f"    {name}: {err}")

    all_ok = (
        not summary["fields_failed"]
        and summary["stages_deployed"]
        and summary["agreement_picklists_deployed"]
        and summary["layout_updated"]
    )
    print(f"\n  {'ALL PHASE 1 TASKS COMPLETE' if all_ok else 'SOME TASKS FAILED — review above'}")


if __name__ == "__main__":
    main()
