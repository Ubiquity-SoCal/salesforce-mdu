"""
Clean up Opportunity and Agreement list views.

Target state:
  Opportunities: All Opportunities, MDU - All, MDU - Open, BUS - All, BUS - Open
  Agreements: All Agreements, MDU - All, BUS - All

Deletes all other custom views. Renames existing views where possible.
Creates missing views.
"""

import requests
import base64
import io
import zipfile
import time
import re
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
V = "59.0"


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
    resp = requests.post(LOGIN_URL, data=soap_body, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"
    })
    sid = ET.fromstring(resp.text).find(".//{urn:partner.soap.sforce.com}sessionId")
    if sid is None:
        print("[ERROR] Login failed")
        return None
    print("[OK] Logged in")
    return sid.text


def deploy_zip(session_id, zip_bytes, description):
    print(f"\n  Deploying: {description}")
    meta_url = f"{INSTANCE_URL}/services/Soap/m/{V}"
    z64 = base64.b64encode(zip_bytes).decode("utf-8")

    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{z64}</met:ZipFile>
      <met:DeployOptions>
        <met:singlePackage>true</met:singlePackage>
        <met:rollbackOnError>true</met:rollbackOnError>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(meta_url, data=soap, headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"
    })
    deploy_id = ET.fromstring(resp.text).find(
        ".//{http://soap.sforce.com/2006/04/metadata}id"
    )
    if deploy_id is None:
        print("  [ERROR] No deploy ID")
        return False

    print(f"  Deploy ID: {deploy_id.text}")
    for _ in range(30):
        time.sleep(2)
        check = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader><met:sessionId>{session_id}</met:sessionId></met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id.text}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(meta_url, data=check, headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"
        })
        croot = ET.fromstring(cr.text)
        done = croot.find(".//{http://soap.sforce.com/2006/04/metadata}done")
        if done is not None and done.text == "true":
            ok = croot.find(".//{http://soap.sforce.com/2006/04/metadata}success")
            if ok is not None and ok.text == "true":
                print(f"  [OK] {description}")
                return True
            else:
                print(f"  [ERROR] {description} failed!")
                for m in croot.iter():
                    tag = m.tag.split("}")[-1] if "}" in m.tag else m.tag
                    if "problem" in tag.lower() and m.text:
                        print(f"    {m.text}")
                return False

    print("  [ERROR] Timed out")
    return False


def build_opp_listview_xml(dev_name, label, record_type_filter=None, open_only=False):
    """Build a ListView XML for Opportunity."""
    filters = ""
    filter_idx = 1

    if record_type_filter:
        filters += f"""
    <filters>
        <field>OPPORTUNITY.RECORD_TYPE</field>
        <operation>equals</operation>
        <value>{record_type_filter}</value>
    </filters>"""
        filter_idx += 1

    if open_only:
        filters += f"""
    <filters>
        <field>OPPORTUNITY.CLOSED</field>
        <operation>equals</operation>
        <value>0</value>
    </filters>"""

    bool_filter = ""
    if record_type_filter and open_only:
        bool_filter = "\n    <booleanFilter>1 AND 2</booleanFilter>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{dev_name}</fullName>
    <label>{label}</label>{bool_filter}{filters}
    <columns>OPPORTUNITY.NAME</columns>
    <columns>ACCOUNT.NAME</columns>
    <columns>OPPORTUNITY.STAGE_NAME</columns>
    <columns>OPPORTUNITY.AMOUNT</columns>
    <columns>OPPORTUNITY.CLOSE_DATE</columns>
    <filterScope>Everything</filterScope>
    <sharedTo>
        <allInternalUsers></allInternalUsers>
    </sharedTo>
</ListView>"""


def build_agreement_listview_xml(dev_name, label, record_type_filter=None):
    """Build a ListView XML for Agreement__c."""
    filters = ""
    if record_type_filter:
        filters = f"""
    <filters>
        <field>CUST_RECORDTYPE</field>
        <operation>equals</operation>
        <value>{record_type_filter}</value>
    </filters>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ListView xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{dev_name}</fullName>
    <label>{label}</label>{filters}
    <columns>NAME</columns>
    <columns>Agreement_Type__c</columns>
    <columns>Status__c</columns>
    <columns>Opportunity__c</columns>
    <filterScope>Everything</filterScope>
    <sharedTo>
        <allInternalUsers></allInternalUsers>
    </sharedTo>
</ListView>"""


def main():
    session_id = soap_login()
    if not session_id:
        return

    # Connect with simple_salesforce for querying
    sf = Salesforce(
        username='cass1@ubiquitygp.com',
        password='Karate88!',
        security_token='Ktc1n9mLmD9vwEcVcl45q0iAD'
    )

    # ── Get record type developer names ─────────────────────────────
    print("\n--- Record Types ---")
    rt_result = sf.query(
        "SELECT Id, DeveloperName, Name FROM RecordType "
        "WHERE SobjectType = 'Opportunity' ORDER BY Name"
    )
    for r in rt_result['records']:
        print(f"  {r['Name']} ({r['DeveloperName']})")

    rt_agr = sf.query(
        "SELECT Id, DeveloperName, Name FROM RecordType "
        "WHERE SobjectType = 'Agreement__c' ORDER BY Name"
    )
    for r in rt_agr['records']:
        print(f"  Agreement: {r['Name']} ({r['DeveloperName']})")

    # ── Step 1: Deploy new/updated list views ───────────────────────
    print("\n" + "=" * 60)
    print("STEP 1: DEPLOY LIST VIEWS")
    print("=" * 60)

    # Build all the list view XMLs
    opp_views = {
        "MDU_All": build_opp_listview_xml("MDU_All", "MDU - All", "Opportunity.MDU"),
        "MDU_Open": build_opp_listview_xml("MDU_Open", "MDU - Open", "Opportunity.MDU", open_only=True),
        "BUS_All": build_opp_listview_xml("BUS_All", "BUS - All", "Opportunity.Business"),
        "BUS_Open": build_opp_listview_xml("BUS_Open", "BUS - Open", "Opportunity.Business", open_only=True),
    }

    agr_views = {
        "MDU_All": build_agreement_listview_xml("MDU_All", "MDU - All", "Agreement__c.MDU"),
        "BUS_All": build_agreement_listview_xml("BUS_All", "BUS - All", "Agreement__c.Business"),
    }

    # Build package
    members_opp = "\n".join(f"        <members>Opportunity.{name}</members>" for name in opp_views)
    members_agr = "\n".join(f"        <members>Agreement__c.{name}</members>" for name in agr_views)

    pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{members_opp}
        <name>ListView</name>
    </types>
    <types>
{members_agr}
        <name>ListView</name>
    </types>
    <version>{V}</version>
</Package>"""

    files = {"package.xml": pkg_xml}
    for name, xml in opp_views.items():
        files[f"objects/Opportunity.object"] = files.get(
            "objects/Opportunity.object", ""
        )

    # Metadata API needs listviews inside the object file or as separate files
    # Using the deploy approach with individual listview files
    # Actually, listviews deploy as part of the object — let me build object files

    opp_object = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
"""
    for name, xml_content in opp_views.items():
        # Extract the ListView content (between <ListView> tags) and embed
        inner = xml_content.split("<ListView")[1].split("</ListView>")[0]
        inner = inner.split(">", 1)[1]  # remove the xmlns part
        opp_object += f"    <listViews>\n        <fullName>{name}</fullName>\n"
        # Parse fields from XML
        root = ET.fromstring(xml_content)
        ns = "http://soap.sforce.com/2006/04/metadata"
        label = root.find(f"{{{ns}}}label").text
        opp_object += f"        <label>{label}</label>\n"

        bool_filter = root.find(f"{{{ns}}}booleanFilter")
        if bool_filter is not None:
            opp_object += f"        <booleanFilter>{bool_filter.text}</booleanFilter>\n"

        for f in root.findall(f"{{{ns}}}filters"):
            field = f.find(f"{{{ns}}}field").text
            op = f.find(f"{{{ns}}}operation").text
            val = f.find(f"{{{ns}}}value").text
            opp_object += f"        <filters>\n"
            opp_object += f"            <field>{field}</field>\n"
            opp_object += f"            <operation>{op}</operation>\n"
            opp_object += f"            <value>{val}</value>\n"
            opp_object += f"        </filters>\n"

        for c in root.findall(f"{{{ns}}}columns"):
            opp_object += f"        <columns>{c.text}</columns>\n"

        scope = root.find(f"{{{ns}}}filterScope").text
        opp_object += f"        <filterScope>{scope}</filterScope>\n"
        opp_object += f"        <sharedTo>\n            <allInternalUsers></allInternalUsers>\n        </sharedTo>\n"
        opp_object += f"    </listViews>\n"

    opp_object += "</CustomObject>"

    agr_object = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
"""
    for name, xml_content in agr_views.items():
        root = ET.fromstring(xml_content)
        ns = "http://soap.sforce.com/2006/04/metadata"
        label = root.find(f"{{{ns}}}label").text
        agr_object += f"    <listViews>\n        <fullName>{name}</fullName>\n"
        agr_object += f"        <label>{label}</label>\n"

        for f in root.findall(f"{{{ns}}}filters"):
            field = f.find(f"{{{ns}}}field").text
            op = f.find(f"{{{ns}}}operation").text
            val = f.find(f"{{{ns}}}value").text
            agr_object += f"        <filters>\n"
            agr_object += f"            <field>{field}</field>\n"
            agr_object += f"            <operation>{op}</operation>\n"
            agr_object += f"            <value>{val}</value>\n"
            agr_object += f"        </filters>\n"

        for c in root.findall(f"{{{ns}}}columns"):
            agr_object += f"        <columns>{c.text}</columns>\n"

        scope = root.find(f"{{{ns}}}filterScope").text
        agr_object += f"        <filterScope>{scope}</filterScope>\n"
        agr_object += f"        <sharedTo>\n            <allInternalUsers></allInternalUsers>\n        </sharedTo>\n"
        agr_object += f"    </listViews>\n"

    agr_object += "</CustomObject>"

    pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{members_opp}
{members_agr}
        <name>ListView</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg_xml)
        zf.writestr("objects/Opportunity.object", opp_object)
        zf.writestr("objects/Agreement__c.object", agr_object)
    buf.seek(0)

    deploy_zip(session_id, buf.read(), "Create MDU/BUS list views")

    # ── Step 2: Delete old custom list views ────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: DELETE OLD LIST VIEWS")
    print("=" * 60)

    # Views to keep (developer names)
    opp_keep = {
        "AllOpportunities",          # All Opportunities (standard)
        "RecentlyViewedOpportunities",  # Recently Viewed (standard)
        "MDU_All",
        "MDU_Open",
        "BUS_All",
        "BUS_Open",
    }

    agr_keep = {
        "All_Agreements",
        "MDU_All",
        "BUS_All",
    }

    # Get current views
    opp_result = sf.query(
        "SELECT Id, Name, DeveloperName, IsSoqlCompatible "
        "FROM ListView WHERE SobjectType = 'Opportunity'"
    )
    agr_result = sf.query(
        "SELECT Id, Name, DeveloperName, IsSoqlCompatible "
        "FROM ListView WHERE SobjectType = 'Agreement__c'"
    )

    opp_to_delete = []
    for r in opp_result['records']:
        dev = r['DeveloperName']
        if dev not in opp_keep:
            opp_to_delete.append(dev)
            print(f"  Will delete Opportunity.{dev} ({r['Name']})")

    agr_to_delete = []
    for r in agr_result['records']:
        dev = r['DeveloperName']
        if dev not in agr_keep:
            agr_to_delete.append(dev)
            print(f"  Will delete Agreement__c.{dev} ({r['Name']})")

    if not opp_to_delete and not agr_to_delete:
        print("  Nothing to delete!")
    else:
        del_members = ""
        for d in opp_to_delete:
            del_members += f"        <members>Opportunity.{d}</members>\n"
        for d in agr_to_delete:
            del_members += f"        <members>Agreement__c.{d}</members>\n"

        destructive = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{del_members}        <name>ListView</name>
    </types>
    <version>{V}</version>
</Package>"""

        empty_pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <version>{V}</version>
</Package>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.xml", empty_pkg)
            zf.writestr("destructiveChanges.xml", destructive)
        buf.seek(0)

        deploy_zip(session_id, buf.read(), "Delete old list views")

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)

    opp_final = sf.query(
        "SELECT Name, DeveloperName FROM ListView "
        "WHERE SobjectType = 'Opportunity' ORDER BY Name"
    )
    print("\n  Opportunity views:")
    for r in opp_final['records']:
        print(f"    {r['Name']} ({r['DeveloperName']})")

    agr_final = sf.query(
        "SELECT Name, DeveloperName FROM ListView "
        "WHERE SobjectType = 'Agreement__c' ORDER BY Name"
    )
    print("\n  Agreement views:")
    for r in agr_final['records']:
        print(f"    {r['Name']} ({r['DeveloperName']})")


if __name__ == "__main__":
    main()
