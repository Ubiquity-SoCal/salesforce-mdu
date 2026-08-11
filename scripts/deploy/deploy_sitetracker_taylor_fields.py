"""
Deploy Taylor's requested changes to SiteTracker_Project__c:
1. Create 13 new milestone/date fields
2. Update page layout: remove 6 fields, add 13 new fields in organized sections

Taylor's email: March 30, 2026
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

# ── New fields to create on SiteTracker_Project__c ──────────────────────────

NEW_FIELDS = [
    # (API name, Label, Type, Length/extra)
    ("Total_Units__c", "Total Units", "Number", {"precision": 8, "scale": 0}),
    ("Total_Living_Units__c", "Total # of Living Units", "Number", {"precision": 8, "scale": 0}),
    ("Reason_for_Hold__c", "Reason for Hold", "LongTextArea", {"length": 2000, "visibleLines": 3}),
    ("Confirmed_Client_Eng_Walk_Date__c", "Confirmed w/Client Eng Walk Date", "Date", {}),
    ("Eng_Site_Walk_A__c", "Eng Site Walk (A)", "Date", {}),
    ("Design_1st_Draft_Complete_A__c", "Design (1st Draft) Complete based on (A)", "Date", {}),
    ("Design_Phase_Complete_A__c", "Design Phase Complete (A)", "Date", {}),
    ("Submit_Design_to_Client_A__c", "Submit the design to the Client (A)", "Date", {}),
    ("Complete_PreCon_Walk_GC_A__c", "Complete PreCon walk with GC (A)", "Date", {}),
    ("MDU_Construction_Start_F__c", "MDU Construction Start (F)", "Date", {}),
    ("MDU_Construction_Start_A__c", "MDU Construction Start (A)", "Date", {}),
    ("MDU_Construction_Complete_F__c", "MDU Construction Complete (F)", "Date", {}),
    ("MDU_Construction_Complete_A__c", "MDU Construction Complete (A)", "Date", {}),
]


def build_field_xml(api_name, label, field_type, extra):
    """Build Metadata API XML for a custom field."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{api_name}</fullName>
    <label>{label}</label>"""

    if field_type == "Date":
        xml += """
    <type>Date</type>"""
    elif field_type == "Number":
        xml += f"""
    <type>Number</type>
    <precision>{extra['precision']}</precision>
    <scale>{extra['scale']}</scale>"""
    elif field_type == "LongTextArea":
        xml += f"""
    <type>LongTextArea</type>
    <length>{extra['length']}</length>
    <visibleLines>{extra['visibleLines']}</visibleLines>"""

    xml += """
</CustomField>"""
    return xml


def build_layout_xml():
    """Build the updated page layout XML."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>SiteTracker_Project__c-SiteTracker Project Layout</fullName>
    <layoutSections>
        <label>Project Info</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Required</behavior><field>Name</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Site_Name__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Site_Status__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Build_Status__c</field></layoutItems>
            <layoutItems><behavior>Readonly</behavior><field>Build_Icon__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>MDU_Category__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Opportunity__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Total_Units__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Total_Living_Units__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Reason_for_Hold__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Activation_Forecast__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Activation_Actual__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Engineering &amp; Design Milestones</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Confirmed_Client_Eng_Walk_Date__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Eng_Site_Walk_A__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Design_1st_Draft_Complete_A__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Design_Phase_Complete_A__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Submit_Design_to_Client_A__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Complete_PreCon_Walk_GC_A__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Construction Milestones</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>MDU_Construction_Start_F__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>MDU_Construction_Complete_F__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>MDU_Construction_Start_A__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>MDU_Construction_Complete_A__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Sync Info</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>SiteTracker_Record_Id__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>Last_Synced__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
</Layout>"""


def do_deploy(zip_bytes, label="deploy"):
    """Send a Metadata API deploy and wait for result."""
    deploy_url = f'{sf.base_url}metadata/deployRequest'
    deploy_body = {
        'deployOptions': {
            'checkOnly': False,
            'ignoreWarnings': True,
            'rollbackOnError': True,
            'singlePackage': True
        }
    }
    boundary = '----DeployBoundary'

    # Use raw binary upload (not base64) to avoid line-length issues
    body_parts = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="json"\r\n'
        f'Content-Type: application/json\r\n\r\n'
        f'{json.dumps(deploy_body)}\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
        f'Content-Type: application/zip\r\n\r\n'
    ).encode('utf-8')
    body_end = f'\r\n--{boundary}--'.encode('utf-8')
    full_body = body_parts + zip_bytes + body_end

    headers = {
        'Authorization': f'Bearer {sf.session_id}',
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }
    resp = requests.post(deploy_url, headers=headers, data=full_body)
    print(f'[{label}] Deploy request: {resp.status_code}')

    if resp.status_code == 201:
        deploy_id = resp.json().get('id')
        print(f'[{label}] Deploy ID: {deploy_id}')
        for i in range(30):
            time.sleep(3)
            check = requests.get(
                f'{deploy_url}/{deploy_id}?includeDetails=true',
                headers={'Authorization': f'Bearer {sf.session_id}'}
            )
            result = check.json()
            status = result.get('deployResult', {}).get('status', 'unknown')
            print(f'  Status: {status}')
            if status in ('Succeeded', 'Failed', 'Canceled'):
                if status == 'Failed':
                    details = result.get('deployResult', {}).get('details', {})
                    failures = details.get('componentFailures', [])
                    if isinstance(failures, dict):
                        failures = [failures]
                    for f in failures:
                        print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
                    return False
                elif status == 'Succeeded':
                    print(f'  [{label}] Deployed successfully!')
                    return True
                break
        else:
            print(f"  [{label}] Timed out waiting for deploy")
            return False
    else:
        print(f'Error: {resp.text[:500]}')
        return False


def deploy():
    # ── Step 1: Deploy fields ──
    print("=" * 50)
    print("Step 1: Creating 13 new fields...")
    print("=" * 50)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        members_xml = ""
        fields_xml = ""
        for api_name, label, ftype, extra in NEW_FIELDS:
            members_xml += f"        <members>SiteTracker_Project__c.{api_name}</members>\n"
            # Build field XML fragment (no standalone header)
            field_frag = f"    <fields>\n        <fullName>{api_name}</fullName>\n        <label>{label}</label>\n"
            if ftype == "Date":
                field_frag += "        <type>Date</type>\n"
            elif ftype == "Number":
                field_frag += f"        <type>Number</type>\n        <precision>{extra['precision']}</precision>\n        <scale>{extra['scale']}</scale>\n"
            elif ftype == "LongTextArea":
                field_frag += f"        <type>LongTextArea</type>\n        <length>{extra['length']}</length>\n        <visibleLines>{extra['visibleLines']}</visibleLines>\n"
            field_frag += "    </fields>\n"
            fields_xml += field_frag

        # All fields go inside a single object XML
        obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
{fields_xml}</CustomObject>"""
        zf.writestr('objects/SiteTracker_Project__c.object', obj_xml)

        package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{members_xml}        <name>CustomField</name>
    </types>
    <version>59.0</version>
</Package>"""
        zf.writestr('package.xml', package_xml)

    buf.seek(0)
    if not do_deploy(buf.read(), "Fields"):
        print("Field deploy failed — aborting.")
        return

    # ── Step 2: Deploy layout ──
    print()
    print("=" * 50)
    print("Step 2: Updating page layout...")
    print("=" * 50)

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf:
        package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>SiteTracker_Project__c-SiteTracker Project Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""
        zf.writestr('package.xml', package_xml)
        zf.writestr(
            'layouts/SiteTracker_Project__c-SiteTracker Project Layout.layout',
            build_layout_xml()
        )

    buf2.seek(0)
    if not do_deploy(buf2.read(), "Layout"):
        print("Layout deploy failed.")
        return

    print()
    print("All done! 13 fields created + layout updated.")


if __name__ == '__main__':
    deploy()
