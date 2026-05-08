"""
Fix Standard User - Custom profile for MDU Sales app.

Deploys via Metadata API:
1. FLS on all 38 Opportunity custom fields (read + edit)
2. FLS on Agreement__c, SiteTracker_Project__c, Tracker_View__c fields
3. MDU Sales app visibility
4. Tab visibility for Tracker and other custom tabs
5. Object permissions for custom objects (Agreement__c, SiteTracker_Project__c, etc.)
"""

import requests
import re
import base64
import zipfile
import io
import time
import sys

# --- Auth ---
LOGIN_DATA = '''<?xml version="1.0" encoding="utf-8"?>
<env:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <n1:login xmlns:n1="urn:partner.soap.sforce.com">
      <n1:username>cass1@ubiquitygp.com</n1:username>
      <n1:password>Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD</n1:password>
    </n1:login>
  </env:Body>
</env:Envelope>'''

PROFILE_NAME = "Standard User - Custom"

def login():
    r = requests.post('https://login.salesforce.com/services/Soap/u/59.0',
        data=LOGIN_DATA, headers={'Content-Type': 'text/xml', 'SOAPAction': 'login'})
    token = re.search(r'<sessionId>(.*?)</sessionId>', r.text).group(1)
    instance = re.search(r'<serverUrl>(https://.*?)/services', r.text).group(1)
    return token, instance


def get_metadata_url(instance_url):
    return instance_url + '/services/Soap/m/59.0'


def describe_objects(token, instance_url):
    """Get all custom fields for objects we need FLS on."""
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    base = instance_url

    objects_to_fix = {}

    for obj_name in ['Opportunity', 'Agreement__c', 'SiteTracker_Project__c',
                     'Tracker_View__c', 'Opportunity_Contact__c', 'IronClad__c']:
        try:
            r = requests.get(f'{base}/services/data/v59.0/sobjects/{obj_name}/describe',
                           headers=headers)
            if r.status_code == 200:
                fields = r.json()['fields']
                # Exclude master-detail (relationship) fields and formula/rollup fields
                # that can't have FLS deployed
                skip_types = {'reference'}
                custom_fields = []
                for f in fields:
                    if not f['custom']:
                        continue
                    # Skip master-detail relationships (not nillable = master-detail)
                    if f['type'] == 'reference' and not f['nillable']:
                        print(f"    Skipping master-detail: {obj_name}.{f['name']}")
                        continue
                    # Skip formula and rollup summary fields (calculated, not editable via FLS)
                    if f.get('calculated', False):
                        print(f"    Skipping formula/rollup: {obj_name}.{f['name']}")
                        continue
                    # Skip required fields (can't deploy FLS to required fields)
                    if not f['nillable'] and not f['defaultedOnCreate']:
                        print(f"    Skipping required: {obj_name}.{f['name']}")
                        continue
                    custom_fields.append(f['name'])
                objects_to_fix[obj_name] = custom_fields
                print(f"  {obj_name}: {len(custom_fields)} deployable custom fields")
            else:
                print(f"  {obj_name}: skipped (not found)")
        except Exception as e:
            print(f"  {obj_name}: skipped ({e})")

    return objects_to_fix


def build_profile_xml(objects_to_fix):
    """Build profile metadata XML with FLS, app visibility, tab visibility, and object permissions."""

    field_perms = ""
    for obj_name, fields in objects_to_fix.items():
        for field in fields:
            field_perms += f"""
    <fieldPermissions>
        <editable>true</editable>
        <field>{obj_name}.{field}</field>
        <readable>true</readable>
    </fieldPermissions>"""

    # Object permissions for custom objects
    object_perms = ""
    custom_objects = [o for o in objects_to_fix.keys() if o.endswith('__c')]
    for obj_name in custom_objects:
        object_perms += f"""
    <objectPermissions>
        <allowCreate>true</allowCreate>
        <allowDelete>false</allowDelete>
        <allowEdit>true</allowEdit>
        <allowRead>true</allowRead>
        <modifyAllRecords>false</modifyAllRecords>
        <object>{obj_name}</object>
        <viewAllRecords>false</viewAllRecords>
    </objectPermissions>"""

    # App visibility — must include standard-__LightningSales as default to avoid
    # "can't remove only default app" error. MDU_Sales and Inside_Sales made visible.
    app_visibility = """
    <applicationVisibilities>
        <application>standard__LightningSales</application>
        <default>true</default>
        <visible>true</visible>
    </applicationVisibilities>
    <applicationVisibilities>
        <application>MDU_Sales</application>
        <default>false</default>
        <visible>true</visible>
    </applicationVisibilities>
    <applicationVisibilities>
        <application>Inside_Sales</application>
        <default>false</default>
        <visible>true</visible>
    </applicationVisibilities>"""

    # Tab visibility for all custom tabs used in MDU Sales and Business Sales apps
    custom_tabs = [
        'MDU_Tracker', 'Business_Tracker', 'Tracker',
        'Agreement__c', 'SiteTracker_Project__c', 'IronClad__c',
        'Special_Project__c',
    ]
    tab_visibility = ""
    for tab in custom_tabs:
        tab_visibility += f"""
    <tabVisibilities>
        <tab>{tab}</tab>
        <visibility>DefaultOn</visibility>
    </tabVisibilities>"""

    # Layout assignments for MDU and Business record types
    layout_assignments = """
    <layoutAssignments>
        <layout>Opportunity-MDU Opportunity Layout</layout>
        <recordType>Opportunity.MDU</recordType>
    </layoutAssignments>
    <layoutAssignments>
        <layout>Opportunity-MDU Opportunity Layout</layout>
        <recordType>Opportunity.SFU</recordType>
    </layoutAssignments>
    <layoutAssignments>
        <layout>Opportunity-Business Opportunity Layout</layout>
        <recordType>Opportunity.Business</recordType>
    </layoutAssignments>"""

    # Record type visibility
    record_type_visibility = """
    <recordTypeVisibilities>
        <default>true</default>
        <recordType>Opportunity.MDU</recordType>
        <visible>true</visible>
    </recordTypeVisibilities>
    <recordTypeVisibilities>
        <default>false</default>
        <recordType>Opportunity.SFU</recordType>
        <visible>true</visible>
    </recordTypeVisibilities>
    <recordTypeVisibilities>
        <default>false</default>
        <recordType>Opportunity.Business</recordType>
        <visible>true</visible>
    </recordTypeVisibilities>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    {app_visibility}
    {field_perms}
    {object_perms}
    {tab_visibility}
    {layout_assignments}
    {record_type_visibility}
</Profile>"""

    return xml


def build_package_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Standard User - Custom</members>
        <name>Profile</name>
    </types>
    <version>59.0</version>
</Package>"""


def create_zip(profile_xml, package_xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('profiles/Standard User - Custom.profile', profile_xml)
        zf.writestr('package.xml', package_xml)
    return base64.b64encode(buf.getvalue()).decode()


def deploy(token, metadata_url, zip_b64):
    deploy_soap = f'''<?xml version="1.0" encoding="utf-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <env:Header>
    <met:SessionHeader>
      <met:sessionId>{token}</met:sessionId>
    </met:SessionHeader>
  </env:Header>
  <env:Body>
    <met:deploy>
      <met:ZipFile>{zip_b64}</met:ZipFile>
      <met:DeployOptions>
        <met:singlePackage>true</met:singlePackage>
        <met:rollbackOnError>true</met:rollbackOnError>
      </met:DeployOptions>
    </met:deploy>
  </env:Body>
</env:Envelope>'''

    r = requests.post(metadata_url, data=deploy_soap,
        headers={'Content-Type': 'text/xml', 'SOAPAction': 'deploy'})

    deploy_id = re.search(r'<id>(.*?)</id>', r.text)
    if not deploy_id:
        print(f"Deploy failed: {r.text[:500]}")
        sys.exit(1)
    return deploy_id.group(1)


def check_deploy(token, metadata_url, deploy_id):
    check_soap = f'''<?xml version="1.0" encoding="utf-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <env:Header>
    <met:SessionHeader>
      <met:sessionId>{token}</met:sessionId>
    </met:SessionHeader>
  </env:Header>
  <env:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </env:Body>
</env:Envelope>'''

    for i in range(30):
        time.sleep(2)
        r = requests.post(metadata_url, data=check_soap,
            headers={'Content-Type': 'text/xml', 'SOAPAction': 'checkDeployStatus'})

        done = re.search(r'<done>(.*?)</done>', r.text)
        status = re.search(r'<status>(.*?)</status>', r.text)
        success = re.search(r'<success>(.*?)</success>', r.text)

        if done and done.group(1) == 'true':
            if success and success.group(1) == 'true':
                print(f"  Deploy succeeded!")
                return True
            else:
                # Extract error details
                errors = re.findall(r'<problem>(.*?)</problem>', r.text)
                print(f"  Deploy failed!")
                for err in errors:
                    print(f"    Error: {err}")
                # Print more context
                comp_status = re.findall(r'<componentFailures>.*?</componentFailures>', r.text, re.DOTALL)
                for cs in comp_status:
                    print(f"    Detail: {cs[:300]}")
                return False

        print(f"  Checking... ({status.group(1) if status else 'unknown'})")

    print("  Timed out waiting for deploy")
    return False


def main():
    print("=== Fix Standard User - Custom Profile ===\n")

    print("1. Logging in...")
    token, instance_url = login()
    metadata_url = get_metadata_url(instance_url)
    print(f"   Connected to {instance_url}\n")

    print("2. Discovering custom fields...")
    objects_to_fix = describe_objects(token, instance_url)
    total_fields = sum(len(f) for f in objects_to_fix.values())
    print(f"   Total: {total_fields} custom fields across {len(objects_to_fix)} objects\n")

    print("3. Building profile metadata...")
    profile_xml = build_profile_xml(objects_to_fix)
    package_xml = build_package_xml()
    zip_b64 = create_zip(profile_xml, package_xml)
    print(f"   Package built ({len(zip_b64)} bytes)\n")

    print("4. Deploying to Salesforce...")
    deploy_id = deploy(token, metadata_url, zip_b64)
    print(f"   Deploy ID: {deploy_id}")
    success = check_deploy(token, metadata_url, deploy_id)

    if success:
        print(f"\n=== DONE ===")
        print(f"Profile '{PROFILE_NAME}' updated with:")
        print(f"  - FLS on {total_fields} custom fields ({len(objects_to_fix)} objects)")
        print(f"  - MDU Sales + Business Sales app visibility")
        print(f"  - Tracker tab visibility")
        print(f"  - Layout assignments for MDU/SFU/Business record types")
        print(f"  - Record type visibility")
        print(f"\nAffects all 15 active users on this profile.")
    else:
        print(f"\nDeploy failed. Check errors above.")


if __name__ == '__main__':
    main()
