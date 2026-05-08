"""
Setup Record Types on Opportunity to separate MDU from Business deals.

Task 1: Deploy MDU and Business Record Types via Metadata API.
Task 2: Tag existing Opportunities (Monday_Item_ID -> MDU, else -> Business).
Task 3: Deploy 6 filtered list views via Metadata API.
"""

import requests
import time
import base64
import io
import zipfile
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "v59.0"
API_VERSION_NUM = "59.0"

SF_PASSWORD = "Karate88!"
SF_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"


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
    print("AUTHENTICATING (SOAP)")
    print("=" * 70)
    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)
    if resp.status_code != 200:
        print(f"SOAP login failed ({resp.status_code}): {resp.text[:1000]}")
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


# ── Metadata Deploy Helper ──────────────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════
# TASK 1: Deploy Record Types
# ═══════════════════════════════════════════════════════════════════════
def task1_deploy_record_types(session_id):
    print("\n" + "=" * 70)
    print("TASK 1: Deploy Record Types (MDU + Business) on Opportunity")
    print("=" * 70)

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Opportunity</members>
    <name>CustomObject</name>
  </types>
  <types>
    <members>Admin</members>
    <name>Profile</name>
  </types>
  <version>59.0</version>
</Package>"""

    # Opportunity object with business processes + record types
    # Opportunity RecordTypes require a BusinessProcess (Sales Process)
    opportunity_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <businessProcesses>
        <fullName>MDU Sales Process</fullName>
        <isActive>true</isActive>
        <values>
            <fullName>Prospecting</fullName>
        </values>
        <values>
            <fullName>Under Contract</fullName>
        </values>
        <values>
            <fullName>Ready for Engineering</fullName>
        </values>
        <values>
            <fullName>Under Construction</fullName>
        </values>
        <values>
            <fullName>Activation</fullName>
        </values>
        <values>
            <fullName>Closed Won</fullName>
        </values>
        <values>
            <fullName>Closed Lost</fullName>
        </values>
    </businessProcesses>
    <businessProcesses>
        <fullName>Business Sales Process</fullName>
        <isActive>true</isActive>
        <values>
            <fullName>Prospecting</fullName>
        </values>
        <values>
            <fullName>Under Contract</fullName>
        </values>
        <values>
            <fullName>Ready for Engineering</fullName>
        </values>
        <values>
            <fullName>Under Construction</fullName>
        </values>
        <values>
            <fullName>Activation</fullName>
        </values>
        <values>
            <fullName>Closed Won</fullName>
        </values>
        <values>
            <fullName>Closed Lost</fullName>
        </values>
    </businessProcesses>
    <recordTypes>
        <fullName>MDU</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>MDU</label>
        <description>Multi-Dwelling Unit property pursuits</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business</fullName>
        <active>true</active>
        <businessProcess>Business Sales Process</businessProcess>
        <label>Business</label>
        <description>Business/commercial sales</description>
    </recordTypes>
</CustomObject>"""

    # Profile metadata to make both record types visible to System Administrator
    # "Admin" is the API name for "System Administrator" profile
    profile_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <recordTypeVisibilities>
        <recordType>Opportunity.MDU</recordType>
        <visible>true</visible>
        <default>true</default>
        <personAccountDefault>false</personAccountDefault>
    </recordTypeVisibilities>
    <recordTypeVisibilities>
        <recordType>Opportunity.Business</recordType>
        <visible>true</visible>
        <default>false</default>
        <personAccountDefault>false</personAccountDefault>
    </recordTypeVisibilities>
</Profile>"""

    files = {
        "package.xml": package_xml,
        "objects/Opportunity.object": opportunity_xml,
        "profiles/Admin.profile": profile_xml,
    }

    return deploy_metadata_package(session_id, files, "Opportunity Record Types (MDU + Business)")


# ═══════════════════════════════════════════════════════════════════════
# TASK 2: Tag Existing Records
# ═══════════════════════════════════════════════════════════════════════
def task2_tag_records():
    print("\n" + "=" * 70)
    print("TASK 2: Tag Existing Opportunities with Record Types")
    print("=" * 70)

    sf = Salesforce(
        username=USERNAME,
        password=SF_PASSWORD,
        security_token=SF_TOKEN,
        domain="login",
    )

    # Get Record Type IDs
    print("\n  Querying Record Types on Opportunity...")
    rt_result = sf.query(
        "SELECT Id, Name, DeveloperName FROM RecordType WHERE SObjectType = 'Opportunity'"
    )
    print(f"  Found {rt_result['totalSize']} Record Types:")
    rt_map = {}
    for rt in rt_result["records"]:
        print(f"    {rt['DeveloperName']}: {rt['Id']}")
        rt_map[rt["DeveloperName"]] = rt["Id"]

    mdu_id = rt_map.get("MDU")
    biz_id = rt_map.get("Business")
    if not mdu_id or not biz_id:
        print("  ERROR: Could not find both MDU and Business record type IDs.")
        return False

    # Query opportunities WITH Monday_Item_ID__c (MDU deals)
    print("\n  Querying Opportunities WITH Monday_Item_ID__c (MDU)...")
    mdu_opps = sf.query_all(
        "SELECT Id, Name FROM Opportunity WHERE Monday_Item_ID__c != null"
    )
    mdu_count = mdu_opps["totalSize"]
    print(f"  Found {mdu_count} MDU opportunities.")

    # Query opportunities WITHOUT Monday_Item_ID__c (Business deals)
    print("  Querying Opportunities WITHOUT Monday_Item_ID__c (Business)...")
    biz_opps = sf.query_all(
        "SELECT Id, Name FROM Opportunity WHERE Monday_Item_ID__c = null"
    )
    biz_count = biz_opps["totalSize"]
    print(f"  Found {biz_count} Business opportunities.")

    # Update MDU records
    if mdu_count > 0:
        print(f"\n  Updating {mdu_count} Opportunities -> MDU...")
        mdu_updates = [
            {"Id": rec["Id"], "RecordTypeId": mdu_id}
            for rec in mdu_opps["records"]
        ]
        # Batch in chunks of 200
        for i in range(0, len(mdu_updates), 200):
            batch = mdu_updates[i : i + 200]
            results = sf.bulk.Opportunity.update(batch)
            errors = [r for r in results if not r.get("success", True)]
            if errors:
                print(f"    Batch errors: {errors[:5]}")
            else:
                print(f"    Batch {i // 200 + 1}: {len(batch)} records updated successfully.")

    # Update Business records
    if biz_count > 0:
        print(f"\n  Updating {biz_count} Opportunities -> Business...")
        biz_updates = [
            {"Id": rec["Id"], "RecordTypeId": biz_id}
            for rec in biz_opps["records"]
        ]
        for i in range(0, len(biz_updates), 200):
            batch = biz_updates[i : i + 200]
            results = sf.bulk.Opportunity.update(batch)
            errors = [r for r in results if not r.get("success", True)]
            if errors:
                print(f"    Batch errors: {errors[:5]}")
            else:
                print(f"    Batch {i // 200 + 1}: {len(batch)} records updated successfully.")

    print(f"\n  DONE: {mdu_count} -> MDU, {biz_count} -> Business")
    return mdu_count, biz_count


# ═══════════════════════════════════════════════════════════════════════
# TASK 3: Deploy List Views
# ═══════════════════════════════════════════════════════════════════════
def task3_deploy_list_views(session_id):
    print("\n" + "=" * 70)
    print("TASK 3: Deploy Filtered List Views on Opportunity")
    print("=" * 70)

    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Opportunity.All_MDU_Deals</members>
    <members>Opportunity.MDU_Open</members>
    <members>Opportunity.MDU_Under_Contract</members>
    <members>Opportunity.MDU_Prospecting</members>
    <members>Opportunity.Business_All</members>
    <members>Opportunity.Business_Open</members>
    <name>ListView</name>
  </types>
  <version>59.0</version>
</Package>"""

    mdu_columns = """        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Units__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>Property_Category__c</columns>
        <columns>Agreement_Name__c</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>"""

    biz_columns = """        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>OPPORTUNITY.AMOUNT</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>"""

    # ListView 1: All MDU Deals
    lv_all_mdu = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>All_MDU_Deals</fullName>
        <label>All MDU Deals</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
{mdu_columns}
    </listViews>
</CustomObject>"""

    # ListView 2: MDU - Open
    lv_mdu_open = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>MDU_Open</fullName>
        <label>MDU - Open</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
{mdu_columns}
    </listViews>
</CustomObject>"""

    # ListView 3: MDU - Under Contract
    lv_mdu_contract = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>MDU_Under_Contract</fullName>
        <label>MDU - Under Contract</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Under Contract</value>
        </filters>
{mdu_columns}
    </listViews>
</CustomObject>"""

    # ListView 4: MDU - Prospecting
    lv_mdu_prospect = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>MDU_Prospecting</fullName>
        <label>MDU - Prospecting</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Prospecting</value>
        </filters>
{mdu_columns}
    </listViews>
</CustomObject>"""

    # ListView 5: Business - All
    lv_biz_all = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>Business_All</fullName>
        <label>Business - All</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business</value>
        </filters>
{biz_columns}
    </listViews>
</CustomObject>"""

    # ListView 6: Business - Open
    lv_biz_open = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>Business_Open</fullName>
        <label>Business - Open</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
{biz_columns}
    </listViews>
</CustomObject>"""

    # Combine all list views into a single Opportunity.object file
    combined_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>All_MDU_Deals</fullName>
        <label>All MDU Deals</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
{mdu_columns}
    </listViews>
    <listViews>
        <fullName>MDU_Open</fullName>
        <label>MDU - Open</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
{mdu_columns}
    </listViews>
    <listViews>
        <fullName>MDU_Under_Contract</fullName>
        <label>MDU - Under Contract</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Under Contract</value>
        </filters>
{mdu_columns}
    </listViews>
    <listViews>
        <fullName>MDU_Prospecting</fullName>
        <label>MDU - Prospecting</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>Prospecting</value>
        </filters>
{mdu_columns}
    </listViews>
    <listViews>
        <fullName>Business_All</fullName>
        <label>Business - All</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business</value>
        </filters>
{biz_columns}
    </listViews>
    <listViews>
        <fullName>Business_Open</fullName>
        <label>Business - Open</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
{biz_columns}
    </listViews>
</CustomObject>"""

    files = {
        "package.xml": package_xml,
        "objects/Opportunity.object": combined_xml,
    }

    return deploy_metadata_package(session_id, files, "6 Opportunity List Views")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    session_id = soap_login()
    if not session_id:
        print("FATAL: Could not authenticate. Aborting.")
        return

    # Task 1: Deploy Record Types
    rt_ok = task1_deploy_record_types(session_id)
    if not rt_ok:
        print("\nTask 1 FAILED. Aborting remaining tasks.")
        return

    # Task 2: Tag existing records
    tag_result = task2_tag_records()
    if not tag_result:
        print("\nTask 2 FAILED. Continuing to Task 3 anyway...")
        mdu_count, biz_count = 0, 0
    else:
        mdu_count, biz_count = tag_result

    # Task 3: Deploy List Views
    lv_ok = task3_deploy_list_views(session_id)

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Task 1 - Record Types:  {'SUCCESS' if rt_ok else 'FAILED'}")
    print(f"    - MDU (Multi-Dwelling Unit property pursuits)")
    print(f"    - Business (Business/commercial sales)")
    print(f"  Task 2 - Tagged Records: {mdu_count} -> MDU, {biz_count} -> Business")
    print(f"  Task 3 - List Views:    {'SUCCESS' if lv_ok else 'FAILED'}")
    if lv_ok:
        print(f"    - All MDU Deals")
        print(f"    - MDU - Open")
        print(f"    - MDU - Under Contract")
        print(f"    - MDU - Prospecting")
        print(f"    - Business - All")
        print(f"    - Business - Open")
    print("=" * 70)


if __name__ == "__main__":
    main()
