"""
Deploy Business Sales Dashboard for B2B Vendor profile.

1. Creates BusinessSalesDashboard VF page (Business-only, no MDU slicer)
2. Creates BusinessSales_Home FlexiPage (embeds the VF page)
3. Updates B2B Vendor profile with:
   - VF page access
   - Business Sales (Inside_Sales) app visibility
   - FLS on Opportunity + Agreement custom fields
   - Business record type visibility
   - Business Tracker + Agreement tabs
"""

import requests
import re
import base64
import zipfile
import io
import time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()



def login():
    login_data = f'''<?xml version="1.0" encoding="utf-8"?>
<env:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <n1:login xmlns:n1="urn:partner.soap.sforce.com">
      <n1:username>{_SF["username"]}</n1:username>
      <n1:password>{_SF["password"]}{_SF["token"]}</n1:password>
    </n1:login>
  </env:Body>
</env:Envelope>'''
    r = requests.post('https://login.salesforce.com/services/Soap/u/59.0',
        data=login_data, headers={'Content-Type': 'text/xml', 'SOAPAction': 'login'})
    token = re.search(r'<sessionId>(.*?)</sessionId>', r.text).group(1)
    instance = re.search(r'<serverUrl>(https://.*?)/services', r.text).group(1)
    return token, instance


def deploy_zip(token, metadata_url, zip_bytes):
    zip_b64 = base64.b64encode(zip_bytes).decode()
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
    deploy_id = re.search(r'<id>(.*?)</id>', r.text).group(1)
    print(f"  Deploy ID: {deploy_id}")

    for i in range(30):
        time.sleep(2)
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
        r = requests.post(metadata_url, data=check_soap,
            headers={'Content-Type': 'text/xml', 'SOAPAction': 'checkDeployStatus'})
        done = re.search(r'<done>(.*?)</done>', r.text)
        success = re.search(r'<success>(.*?)</success>', r.text)
        if done and done.group(1) == 'true':
            if success and success.group(1) == 'true':
                print("  Deploy succeeded!")
                return True
            else:
                errors = re.findall(r'<problem>(.*?)</problem>', r.text)
                print("  Deploy failed!")
                for e in errors:
                    print(f"    Error: {e}")
                return False
        print(f"  Checking...")
    print("  Timed out")
    return False


def get_deployable_fields(instance, token, obj_name):
    """Get custom fields that can have FLS deployed."""
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    r = requests.get(f'{instance}/services/data/v59.0/sobjects/{obj_name}/describe', headers=headers)
    if r.status_code != 200:
        return []
    fields = []
    for f in r.json()['fields']:
        if not f['custom']:
            continue
        if f['type'] == 'reference' and not f['nillable']:
            continue  # master-detail
        if f.get('calculated', False):
            continue  # formula/rollup
        if not f['nillable'] and not f['defaultedOnCreate']:
            continue  # required
        fields.append(f['name'])
    return fields


def main():
    print("=== Deploy B2B Vendor Business Sales Dashboard ===\n")

    print("1. Logging in...")
    token, instance = login()
    metadata_url = instance + '/services/Soap/m/59.0'
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    print(f"   Connected to {instance}\n")

    # VF page will be deployed via Metadata API along with everything else
    print("2. Reading BusinessSalesDashboard VF page markup...")
    with open('C:/Users/cass/Work_Projects/SalesForce/businessSalesDashboard.vfp', 'r', encoding='utf-8') as f:
        vf_markup = f.read()
    print(f"   Markup loaded ({len(vf_markup)} chars)")

    # Step 2: Build FLS for B2B profile
    print("\n3. Building B2B Vendor profile permissions...")
    field_perms = ""
    for obj in ['Opportunity', 'Agreement__c']:
        fields = get_deployable_fields(instance, token, obj)
        print(f"   {obj}: {len(fields)} fields")
        for fname in fields:
            field_perms += f"""
    <fieldPermissions>
        <editable>true</editable>
        <field>{obj}.{fname}</field>
        <readable>true</readable>
    </fieldPermissions>"""

    # Step 3: Deploy FlexiPage + Profile
    print("\n4. Deploying FlexiPage + B2B Vendor profile...")

    flexipage_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<FlexiPage xmlns="http://soap.sforce.com/2006/04/metadata">
    <flexiPageRegions>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>height</name>
                    <value>900</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>pageName</name>
                    <value>BusinessSalesDashboard</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>showLabel</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentName>flexipage:visualforcePage</componentName>
                <identifier>businessSalesDashboardVF</identifier>
            </componentInstance>
        </itemInstances>
        <name>main</name>
        <type>Region</type>
    </flexiPageRegions>
    <masterLabel>Business Sales Home</masterLabel>
    <template>
        <name>industries_common:homeTemplateOneRegion</name>
    </template>
    <type>HomePage</type>
</FlexiPage>'''

    profile_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <applicationVisibilities>
        <application>standard__LightningSales</application>
        <default>true</default>
        <visible>true</visible>
    </applicationVisibilities>
    <applicationVisibilities>
        <application>Inside_Sales</application>
        <default>false</default>
        <visible>true</visible>
    </applicationVisibilities>
    <pageAccesses>
        <apexPage>BusinessSalesDashboard</apexPage>
        <enabled>true</enabled>
    </pageAccesses>
    {field_perms}
    <objectPermissions>
        <allowCreate>true</allowCreate>
        <allowDelete>false</allowDelete>
        <allowEdit>true</allowEdit>
        <allowRead>true</allowRead>
        <modifyAllRecords>false</modifyAllRecords>
        <object>Agreement__c</object>
        <viewAllRecords>false</viewAllRecords>
    </objectPermissions>
    <tabVisibilities>
        <tab>Business_Tracker</tab>
        <visibility>DefaultOn</visibility>
    </tabVisibilities>
    <tabVisibilities>
        <tab>Agreement__c</tab>
        <visibility>DefaultOn</visibility>
    </tabVisibilities>
    <layoutAssignments>
        <layout>Opportunity-Business Opportunity Layout</layout>
        <recordType>Opportunity.Business</recordType>
    </layoutAssignments>
    <recordTypeVisibilities>
        <default>true</default>
        <recordType>Opportunity.Business</recordType>
        <visible>true</visible>
    </recordTypeVisibilities>
</Profile>'''

    # VF page metadata XML
    vf_meta_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<ApexPage xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <availableInTouch>true</availableInTouch>
    <confirmationTokenRequired>false</confirmationTokenRequired>
    <label>Business Sales Dashboard</label>
</ApexPage>'''

    package_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>BusinessSalesDashboard</members>
        <name>ApexPage</name>
    </types>
    <types>
        <members>BusinessSales_Home</members>
        <name>FlexiPage</name>
    </types>
    <types>
        <members>B2B Vendor</members>
        <name>Profile</name>
    </types>
    <version>59.0</version>
</Package>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('pages/BusinessSalesDashboard.page', vf_markup)
        zf.writestr('pages/BusinessSalesDashboard.page-meta.xml', vf_meta_xml)
        zf.writestr('flexipages/BusinessSales_Home.flexipage', flexipage_xml)
        zf.writestr('profiles/B2B Vendor.profile', profile_xml)
        zf.writestr('package.xml', package_xml)

    success = deploy_zip(token, metadata_url, buf.getvalue())

    if success:
        print(f"\n=== DONE ===")
        print("Deployed for B2B Vendor (Jamie Doyle, Julian Harrell):")
        print("  - BusinessSalesDashboard VF page (Business-only, no MDU data)")
        print("  - BusinessSales_Home FlexiPage (embeds the VF page)")
        print("  - Business Sales app visible")
        print("  - FLS on Opportunity + Agreement custom fields")
        print("  - Business record type + layout")
        print("  - Business Tracker + Agreement tabs")
        print("\nNext step: Assign BusinessSales_Home as the Home page")
        print("for B2B Vendor profile in Lightning App Builder.")


if __name__ == '__main__':
    main()
