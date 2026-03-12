"""
Rebuild MDU Sales Architecture in Salesforce
=============================================
Task 1: Update Opportunity Stages via Metadata API (standardValueSet)
Task 2: Create Agreement__c custom object via Metadata API
Task 3: Add integration fields to Opportunity via Tooling API
Task 4: Update existing Opportunities to new stages
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

MONDAY_API_TOKEN = open(r"C:\Users\cass\Work_Projects\Monday.com\Monday.com_Key.txt").read().strip()

# ── Summary tracking ────────────────────────────────────────────────────
summary = {
    "stages_deployed": False,
    "agreement_object_created": False,
    "opp_fields_created": [],
    "opp_fields_skipped": [],
    "opp_fields_failed": [],
    "opps_updated": [],
    "opps_failed": [],
    "opps_unchanged": [],
}


# ── SOAP Login (for Metadata API) ──────────────────────────────────────
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


# ── Metadata API Deploy ─────────────────────────────────────────────────
def metadata_deploy(session_id, zip_bytes):
    """Deploy a ZIP package via Metadata API SOAP and poll for completion."""
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

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "deploy",
    }

    resp = requests.post(
        f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}",
        data=deploy_body,
        headers=headers,
    )

    if resp.status_code != 200:
        raise Exception(f"Deploy call failed ({resp.status_code}): {resp.text[:1000]}")

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }
    root = ET.fromstring(resp.text)
    async_id = root.find(".//met:id", ns)
    if async_id is None:
        raise Exception(f"No async ID in deploy response: {resp.text[:1000]}")

    deploy_id = async_id.text
    print(f"    Deploy initiated: {deploy_id}")

    # Poll for completion
    for attempt in range(60):
        time.sleep(3)
        status = check_deploy_status(session_id, deploy_id)
        state = status.get("state", "Unknown")
        print(f"    Poll {attempt+1}: {state}")
        if state in ("Succeeded", "Failed", "Canceled", "SucceededPartial"):
            return status

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

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "checkDeployStatus",
    }

    resp = requests.post(
        f"{INSTANCE_URL}/services/Soap/m/{API_VERSION_NUM}",
        data=check_body,
        headers=headers,
    )

    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "met": "http://soap.sforce.com/2006/04/metadata",
    }
    root = ET.fromstring(resp.text)
    result = root.find(".//met:result", ns)
    if result is None:
        return {"state": "Unknown", "raw": resp.text[:500]}

    state_el = result.find("met:status", ns)
    success_el = result.find("met:success", ns)
    state = state_el.text if state_el is not None else "Unknown"

    info = {"state": state, "success": success_el.text if success_el is not None else "?"}

    # Extract error messages if any
    for detail in result.findall(".//met:componentFailures", ns):
        problem = detail.find("met:problem", ns)
        comp = detail.find("met:fullName", ns)
        comp_name = comp.text if comp is not None else "?"
        prob_text = problem.text if problem is not None else "?"
        info.setdefault("errors", []).append(f"{comp_name}: {prob_text}")

    # Also check DeployMessage errors
    for msg in result.findall(".//met:details//met:componentFailures", ns):
        problem = msg.find("met:problem", ns)
        comp = msg.find("met:fullName", ns)
        if problem is not None:
            comp_name = comp.text if comp is not None else "?"
            info.setdefault("errors", []).append(f"{comp_name}: {problem.text}")

    return info


# ═══════════════════════════════════════════════════════════════════════
# TASK 1: Update Opportunity Stages
# ═══════════════════════════════════════════════════════════════════════
def task1_update_stages(session_id):
    print("\n" + "=" * 70)
    print("TASK 1: UPDATE OPPORTUNITY STAGES")
    print("=" * 70)

    # Build the standardValueSet XML for OpportunityStage
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
        <fullName>Under Contract</fullName>
        <default>false</default>
        <label>Under Contract</label>
        <closed>false</closed>
        <forecastCategory>Pipeline</forecastCategory>
        <probability>30</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Ready for Engineering</fullName>
        <default>false</default>
        <label>Ready for Engineering</label>
        <closed>false</closed>
        <forecastCategory>BestCase</forecastCategory>
        <probability>50</probability>
        <won>false</won>
    </standardValue>
    <standardValue>
        <fullName>Under Construction</fullName>
        <default>false</default>
        <label>Under Construction</label>
        <closed>false</closed>
        <forecastCategory>BestCase</forecastCategory>
        <probability>75</probability>
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

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpportunityStage</members>
        <name>StandardValueSet</name>
    </types>
    <version>59.0</version>
</Package>"""

    # Build ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", package_xml)
        zf.writestr("standardValueSets/OpportunityStage.standardValueSet", stages_xml)

    print("  Deploying Opportunity Stages...")
    result = metadata_deploy(session_id, buf.getvalue())

    if result.get("state") == "Succeeded":
        print("  [OK] Stages deployed successfully!")
        summary["stages_deployed"] = True
    else:
        print(f"  [FAIL] Stage deployment failed: {result}")
        if "errors" in result:
            for err in result["errors"]:
                print(f"    - {err}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# TASK 2: Create Agreement__c Custom Object
# ═══════════════════════════════════════════════════════════════════════
def task2_create_agreement_object(session_id):
    print("\n" + "=" * 70)
    print("TASK 2: CREATE AGREEMENT__c CUSTOM OBJECT")
    print("=" * 70)

    # Object definition XML
    object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label>
    <pluralLabel>Agreements</pluralLabel>
    <nameField>
        <label>Agreement Number</label>
        <displayFormat>AGR-{0000}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ControlledByParent</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    <enableActivities>true</enableActivities>
    <enableHistory>true</enableHistory>
    <enableReports>true</enableReports>
    <enableSearch>true</enableSearch>

    <!-- Master-Detail to Opportunity -->
    <fields>
        <fullName>Opportunity__c</fullName>
        <label>Opportunity</label>
        <type>MasterDetail</type>
        <referenceTo>Opportunity</referenceTo>
        <relationshipLabel>Agreements</relationshipLabel>
        <relationshipName>Agreements</relationshipName>
        <relationshipOrder>0</relationshipOrder>
        <reparentableMasterDetail>false</reparentableMasterDetail>
        <writeRequiresMasterRead>false</writeRequiresMasterRead>
        <externalId>false</externalId>
    </fields>

    <!-- Agreement Type picklist -->
    <fields>
        <fullName>Agreement_Type__c</fullName>
        <label>Agreement Type</label>
        <type>Picklist</type>
        <externalId>false</externalId>
        <valueSet>
            <restricted>true</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>PAL</fullName><default>false</default><label>PAL</label></value>
                <value><fullName>ROW</fullName><default>false</default><label>ROW</label></value>
                <value><fullName>EMA</fullName><default>false</default><label>EMA</label></value>
                <value><fullName>Bulk</fullName><default>false</default><label>Bulk</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <!-- Status picklist -->
    <fields>
        <fullName>Status__c</fullName>
        <label>Status</label>
        <type>Picklist</type>
        <externalId>false</externalId>
        <valueSet>
            <restricted>true</restricted>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Not Started</fullName><default>true</default><label>Not Started</label></value>
                <value><fullName>Requested</fullName><default>false</default><label>Requested</label></value>
                <value><fullName>Drafted</fullName><default>false</default><label>Drafted</label></value>
                <value><fullName>Under Review</fullName><default>false</default><label>Under Review</label></value>
                <value><fullName>Out for Signature</fullName><default>false</default><label>Out for Signature</label></value>
                <value><fullName>Signed</fullName><default>false</default><label>Signed</label></value>
                <value><fullName>Expired</fullName><default>false</default><label>Expired</label></value>
                <value><fullName>Cancelled</fullName><default>false</default><label>Cancelled</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>

    <!-- Date fields -->
    <fields>
        <fullName>Requested_Date__c</fullName>
        <label>Requested Date</label>
        <type>Date</type>
        <externalId>false</externalId>
    </fields>
    <fields>
        <fullName>Signed_Date__c</fullName>
        <label>Signed Date</label>
        <type>Date</type>
        <externalId>false</externalId>
    </fields>
    <fields>
        <fullName>Expiration_Date__c</fullName>
        <label>Expiration Date</label>
        <type>Date</type>
        <externalId>false</externalId>
    </fields>

    <!-- Signer - Lookup to Contact -->
    <fields>
        <fullName>Signer__c</fullName>
        <label>Signer</label>
        <type>Lookup</type>
        <referenceTo>Contact</referenceTo>
        <relationshipLabel>Agreements Signed</relationshipLabel>
        <relationshipName>Agreements_Signed</relationshipName>
        <externalId>false</externalId>
        <deleteConstraint>SetNull</deleteConstraint>
    </fields>

    <!-- IronClad ID - External ID text -->
    <fields>
        <fullName>IronClad_ID__c</fullName>
        <label>IronClad ID</label>
        <type>Text</type>
        <length>100</length>
        <externalId>true</externalId>
        <unique>false</unique>
    </fields>

    <!-- IronClad URL -->
    <fields>
        <fullName>IronClad_URL__c</fullName>
        <label>IronClad URL</label>
        <type>Url</type>
        <externalId>false</externalId>
    </fields>

    <!-- Notes -->
    <fields>
        <fullName>Notes__c</fullName>
        <label>Notes</label>
        <type>LongTextArea</type>
        <length>10000</length>
        <visibleLines>5</visibleLines>
        <externalId>false</externalId>
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
        zf.writestr("package.xml", package_xml)
        zf.writestr("objects/Agreement__c.object", object_xml)

    print("  Deploying Agreement__c object with all fields...")
    result = metadata_deploy(session_id, buf.getvalue())

    if result.get("state") == "Succeeded":
        print("  [OK] Agreement__c object created successfully!")
        summary["agreement_object_created"] = True
    else:
        print(f"  [FAIL] Agreement__c deployment failed: {result}")
        if "errors" in result:
            for err in result["errors"]:
                print(f"    - {err}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# TASK 3: Add Integration Fields to Opportunity (Tooling API)
# ═══════════════════════════════════════════════════════════════════════
def task3_add_opp_fields(session_id):
    print("\n" + "=" * 70)
    print("TASK 3: ADD INTEGRATION FIELDS TO OPPORTUNITY")
    print("=" * 70)

    fields = [
        {
            "FullName": "Opportunity.SiteTracker_Project_ID__c",
            "Metadata": {
                "label": "SiteTracker Project ID",
                "type": "Text",
                "length": 100,
                "externalId": True,
                "unique": False,
                "description": "Links to SiteTracker Salesforce org project",
            },
        },
        {
            "FullName": "Opportunity.SiteTracker_URL__c",
            "Metadata": {
                "label": "SiteTracker URL",
                "type": "Url",
                "description": "Direct link to SiteTracker project",
            },
        },
        {
            "FullName": "Opportunity.IronClad_URL__c",
            "Metadata": {
                "label": "IronClad URL",
                "type": "Url",
                "description": "Link to IronClad for this property's agreements",
            },
        },
    ]

    # Get existing fields once
    check = rest_get(session_id, "/sobjects/Opportunity/describe/")
    existing_fields = []
    if check.status_code == 200:
        existing_fields = [f["name"] for f in check.json().get("fields", [])]

    for field_def in fields:
        field_name = field_def["FullName"].split(".")[-1]
        print(f"\n  Creating {field_name}...", end=" ")

        if field_name in existing_fields:
            print("SKIPPED (already exists)")
            summary["opp_fields_skipped"].append(field_name)
            continue

        resp = rest_post(session_id, "/tooling/sobjects/CustomField/", field_def)

        if resp.status_code in (200, 201):
            print("SUCCESS")
            summary["opp_fields_created"].append(field_name)
        else:
            error_msg = resp.text[:500]
            if "DUPLICATE" in error_msg.upper() or "already exists" in error_msg.lower():
                print("SKIPPED (already exists)")
                summary["opp_fields_skipped"].append(field_name)
            else:
                print(f"FAILED ({resp.status_code})")
                print(f"    Error: {error_msg}")
                summary["opp_fields_failed"].append((field_name, error_msg))

        time.sleep(1)

    # Set FLS for System Administrator profile on new fields
    if summary["opp_fields_created"]:
        print("\n  Setting FLS for System Administrator on new fields...")
        set_fls_for_fields(session_id, summary["opp_fields_created"], "Opportunity")


def set_fls_for_fields(session_id, field_names, object_name):
    """Deploy a profile FLS update via Metadata API for System Administrator."""
    field_permissions = ""
    for fname in field_names:
        field_permissions += f"""
    <fieldPermissions>
        <field>{object_name}.{fname}</field>
        <editable>true</editable>
        <readable>true</readable>
    </fieldPermissions>"""

    # Also set FLS for Agreement__c fields if that object was created
    if summary.get("agreement_object_created"):
        agreement_fields = [
            "Agreement_Type__c", "Status__c", "Requested_Date__c",
            "Signed_Date__c", "Expiration_Date__c", "Signer__c",
            "IronClad_ID__c", "IronClad_URL__c", "Notes__c",
        ]
        for fname in agreement_fields:
            field_permissions += f"""
    <fieldPermissions>
        <field>Agreement__c.{fname}</field>
        <editable>true</editable>
        <readable>true</readable>
    </fieldPermissions>"""

    profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
{field_permissions}
</Profile>"""

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Admin</members>
        <name>Profile</name>
    </types>
    <version>59.0</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", package_xml)
        zf.writestr("profiles/Admin.profile", profile_xml)

    result = metadata_deploy(session_id, buf.getvalue())
    if result.get("state") == "Succeeded":
        print("  [OK] FLS permissions set for System Administrator")
    else:
        print(f"  [WARN] FLS deploy result: {result}")


# ═══════════════════════════════════════════════════════════════════════
# TASK 4: Update Existing Opportunities to New Stages
# ═══════════════════════════════════════════════════════════════════════
def try_monday_group_lookup(monday_item_ids):
    """Try to look up Monday.com groups for items to map stages more accurately."""
    print("  Attempting Monday.com group lookup for better stage mapping...")
    group_map = {}  # monday_id -> group_title

    # Query in batches of 50
    batch_size = 50
    id_list = list(monday_item_ids)
    for i in range(0, len(id_list), batch_size):
        batch = id_list[i:i+batch_size]
        ids_str = ", ".join(str(mid) for mid in batch)
        query = f"""{{
  items(ids: [{ids_str}]) {{
    id
    group {{
      title
    }}
  }}
}}"""
        headers = {
            "Authorization": MONDAY_API_TOKEN,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }
        try:
            resp = requests.post(
                "https://api.monday.com/v2",
                json={"query": query},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("items", [])
                for item in items:
                    item_id = str(item["id"])
                    group_title = item.get("group", {}).get("title", "")
                    if group_title:
                        group_map[item_id] = group_title
        except Exception as e:
            print(f"    Monday.com lookup error: {e}")
            break

        time.sleep(0.5)

    print(f"    Retrieved groups for {len(group_map)} items")
    return group_map


def map_stage(old_stage, monday_group=None):
    """Map old stage to new stage, using Monday.com group if available."""
    # Direct mappings
    if old_stage == "Prospecting":
        return "Prospecting"
    if old_stage == "Closed Won":
        return "Closed Won"
    if old_stage == "Closed Lost":
        return "Closed Lost"

    # For Qualification/Negotiation/etc, try Monday.com group mapping
    if monday_group:
        group_lower = monday_group.lower()
        if "engineering" in group_lower or "ready for eng" in group_lower:
            return "Ready for Engineering"
        if "construction" in group_lower or "under construction" in group_lower:
            return "Under Construction"
        if "activation" in group_lower or "active" in group_lower:
            return "Activation"
        if "prospect" in group_lower:
            return "Prospecting"
        if "closed" in group_lower and "won" in group_lower:
            return "Closed Won"
        if "closed" in group_lower and "lost" in group_lower:
            return "Closed Lost"

    # Default for unmapped stages
    return "Under Contract"


def task4_update_opportunities():
    print("\n" + "=" * 70)
    print("TASK 4: UPDATE EXISTING OPPORTUNITIES TO NEW STAGES")
    print("=" * 70)

    sf = Salesforce(
        username=USERNAME,
        password=PASSWORD,
        security_token=SECURITY_TOKEN,
        domain="login",
    )

    # Query all Opportunities
    result = sf.query_all(
        "SELECT Id, Name, StageName, Monday_Item_ID__c FROM Opportunity ORDER BY Name"
    )
    opps = result["records"]
    print(f"  Found {len(opps)} Opportunities")

    # Collect Monday.com item IDs for lookup
    monday_ids = set()
    for opp in opps:
        mid = opp.get("Monday_Item_ID__c")
        if mid:
            monday_ids.add(mid)

    # Try Monday.com group lookup
    group_map = {}
    if monday_ids:
        group_map = try_monday_group_lookup(monday_ids)

    # Valid new stages
    valid_stages = {
        "Prospecting", "Under Contract", "Ready for Engineering",
        "Under Construction", "Activation", "Closed Won", "Closed Lost",
    }

    updated = 0
    unchanged = 0
    failed = 0

    for opp in opps:
        opp_id = opp["Id"]
        opp_name = opp["Name"]
        old_stage = opp["StageName"]
        monday_id = opp.get("Monday_Item_ID__c")
        monday_group = group_map.get(monday_id) if monday_id else None

        # If already a valid new stage, skip
        if old_stage in valid_stages:
            new_stage = old_stage
        else:
            new_stage = map_stage(old_stage, monday_group)

        if new_stage == old_stage:
            unchanged += 1
            summary["opps_unchanged"].append(opp_name)
            continue

        group_info = f" (Monday group: {monday_group})" if monday_group else ""
        print(f"  {opp_name}: {old_stage} -> {new_stage}{group_info}")

        try:
            sf.Opportunity.update(opp_id, {"StageName": new_stage})
            updated += 1
            summary["opps_updated"].append((opp_name, old_stage, new_stage))
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"    FAILED: {error_msg}")
            failed += 1
            summary["opps_failed"].append((opp_name, error_msg))

        time.sleep(0.2)

    print(f"\n  Updated: {updated} | Unchanged: {unchanged} | Failed: {failed}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def print_summary():
    print("\n" + "=" * 70)
    print("REBUILD SUMMARY")
    print("=" * 70)

    print(f"\n  TASK 1 - Opportunity Stages: {'DEPLOYED' if summary['stages_deployed'] else 'FAILED'}")
    if summary["stages_deployed"]:
        print("    Stages: Prospecting | Under Contract | Ready for Engineering |")
        print("            Under Construction | Activation | Closed Won | Closed Lost")

    print(f"\n  TASK 2 - Agreement__c Object: {'CREATED' if summary['agreement_object_created'] else 'FAILED'}")
    if summary["agreement_object_created"]:
        print("    Fields: Opportunity__c (MD), Agreement_Type__c, Status__c,")
        print("            Requested_Date__c, Signed_Date__c, Expiration_Date__c,")
        print("            Signer__c (Lookup), IronClad_ID__c, IronClad_URL__c, Notes__c")

    print(f"\n  TASK 3 - Opportunity Integration Fields:")
    if summary["opp_fields_created"]:
        print(f"    Created: {', '.join(summary['opp_fields_created'])}")
    if summary["opp_fields_skipped"]:
        print(f"    Skipped (existed): {', '.join(summary['opp_fields_skipped'])}")
    if summary["opp_fields_failed"]:
        print(f"    Failed: {', '.join(f[0] for f in summary['opp_fields_failed'])}")

    print(f"\n  TASK 4 - Opportunity Stage Updates:")
    print(f"    Updated: {len(summary['opps_updated'])}")
    print(f"    Unchanged: {len(summary['opps_unchanged'])}")
    print(f"    Failed: {len(summary['opps_failed'])}")
    if summary["opps_updated"]:
        print("    Transitions:")
        for name, old, new in summary["opps_updated"]:
            print(f"      {name}: {old} -> {new}")
    if summary["opps_failed"]:
        print("    Failures:")
        for name, err in summary["opps_failed"]:
            print(f"      {name}: {err}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


def main():
    print("=" * 70)
    print("REBUILD MDU SALES ARCHITECTURE")
    print("=" * 70)

    # Authenticate
    print("\nAuthenticating via SOAP...")
    session_id = soap_login()
    print("Authenticated successfully.\n")

    # Task 1: Deploy stages FIRST (needed before Task 4 can update records)
    task1_update_stages(session_id)

    # Task 2: Create Agreement__c object
    task2_create_agreement_object(session_id)

    # Task 3: Add integration fields to Opportunity
    task3_add_opp_fields(session_id)

    # Task 4: Update existing Opportunities to new stages
    # (uses simple_salesforce separately)
    task4_update_opportunities()

    # Print summary
    print_summary()


if __name__ == "__main__":
    main()
