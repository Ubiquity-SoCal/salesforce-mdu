"""
1. Add Pipeline__c formula field to Agreement__c (pulls Opportunity record type name)
2. Deploy all missing list views (Opp + Agreement) in one shot
"""

import requests
import base64
import io
import zipfile
import time
from xml.etree import ElementTree as ET

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


def main():
    session_id = soap_login()
    if not session_id:
        return

    # ── Step 1: Deploy Pipeline__c formula field on Agreement__c ────
    print("\n" + "=" * 60)
    print("STEP 1: ADD Pipeline__c FORMULA FIELD TO Agreement__c")
    print("=" * 60)

    field_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Pipeline__c</fullName>
        <label>Pipeline</label>
        <type>Text</type>
        <formula>Opportunity__r.RecordType.Name</formula>
        <formulaTreatBlanksAs>BlankAsZero</formulaTreatBlanksAs>
        <externalId>false</externalId>
    </fields>
</CustomObject>"""

    pkg1 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Agreement__c.Pipeline__c</members>
        <name>CustomField</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf1 = io.BytesIO()
    with zipfile.ZipFile(buf1, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg1)
        zf.writestr("objects/Agreement__c.object", field_xml)
    buf1.seek(0)

    field_ok = deploy_zip(session_id, buf1.read(), "Agreement__c.Pipeline__c formula field")
    if not field_ok:
        print("\n  Cannot proceed without field. Exiting.")
        return

    # ── Step 2: Deploy all missing list views ───────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: DEPLOY ALL LIST VIEWS")
    print("=" * 60)

    opp_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>MDU_All</fullName>
        <label>MDU - All</label>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Units__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>Property_Category__c</columns>
        <columns>Agreement_Name__c</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>
    <listViews>
        <fullName>BUS_All</fullName>
        <label>BUS - All</label>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>OPPORTUNITY.AMOUNT</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business</value>
        </filters>
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>
    <listViews>
        <fullName>BUS_Open</fullName>
        <label>BUS - Open</label>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>OPPORTUNITY.AMOUNT</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>
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
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>
</CustomObject>"""

    agr_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>MDU_All</fullName>
        <label>MDU - All</label>
        <columns>NAME</columns>
        <columns>Agreement_Type__c</columns>
        <columns>Status__c</columns>
        <columns>Opportunity__c</columns>
        <columns>Pipeline__c</columns>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Pipeline__c</field>
            <operation>equals</operation>
            <value>MDU</value>
        </filters>
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>
    <listViews>
        <fullName>BUS_All</fullName>
        <label>BUS - All</label>
        <columns>NAME</columns>
        <columns>Agreement_Type__c</columns>
        <columns>Status__c</columns>
        <columns>Opportunity__c</columns>
        <columns>Pipeline__c</columns>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Pipeline__c</field>
            <operation>equals</operation>
            <value>Business</value>
        </filters>
        <sharedTo>
            <allInternalUsers></allInternalUsers>
        </sharedTo>
    </listViews>
</CustomObject>"""

    pkg2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity.MDU_All</members>
        <members>Opportunity.BUS_All</members>
        <members>Opportunity.BUS_Open</members>
        <members>Agreement__c.MDU_All</members>
        <members>Agreement__c.BUS_All</members>
        <name>ListView</name>
    </types>
    <version>{V}</version>
</Package>"""

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg2)
        zf.writestr("objects/Opportunity.object", opp_xml)
        zf.writestr("objects/Agreement__c.object", agr_xml)
    buf2.seek(0)

    deploy_zip(session_id, buf2.read(), "All MDU/BUS list views")

    # ── Verify ──────────────────────────────────────────────────────
    from simple_salesforce import Salesforce
    sf = Salesforce(
        username='cass1@ubiquitygp.com',
        password='Karate88!',
        security_token='Ktc1n9mLmD9vwEcVcl45q0iAD'
    )

    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)

    for obj in ['Opportunity', 'Agreement__c']:
        result = sf.query(
            f"SELECT Name, DeveloperName FROM ListView "
            f"WHERE SobjectType = '{obj}' ORDER BY Name"
        )
        print(f"\n  {obj} views:")
        for r in result['records']:
            print(f"    {r['Name']} ({r['DeveloperName']})")


if __name__ == "__main__":
    main()
