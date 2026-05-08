from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

# Connect to both orgs
sf_main = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')
sf_st = Salesforce(username='cass@ubiquitygp.com', password='Hawaiian84', security_token='fe2pen6ceQeqGhWXhBeOIjqP')

# Step 1: Create SiteTracker_Project__c object in main org
print("Step 1: Creating SiteTracker_Project__c object...")

obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>SiteTracker Project</label>
    <pluralLabel>SiteTracker Projects</pluralLabel>
    <nameField>
        <label>Project Number</label>
        <type>Text</type>
    </nameField>
    <deploymentStatus>Deployed</deploymentStatus>
    <sharingModel>ReadWrite</sharingModel>
    <fields>
        <fullName>Opportunity__c</fullName>
        <label>Opportunity</label>
        <type>Lookup</type>
        <referenceTo>Opportunity</referenceTo>
        <relationshipLabel>SiteTracker Projects</relationshipLabel>
        <relationshipName>SiteTracker_Projects</relationshipName>
    </fields>
    <fields>
        <fullName>Site_Name__c</fullName>
        <label>Site Name</label>
        <type>Text</type>
        <length>255</length>
    </fields>
    <fields>
        <fullName>Monday_Name__c</fullName>
        <label>Monday.com Name</label>
        <type>Text</type>
        <length>255</length>
        <externalId>true</externalId>
        <unique>false</unique>
    </fields>
    <fields>
        <fullName>City__c</fullName>
        <label>City</label>
        <type>Text</type>
        <length>100</length>
    </fields>
    <fields>
        <fullName>State__c</fullName>
        <label>State</label>
        <type>Text</type>
        <length>10</length>
    </fields>
    <fields>
        <fullName>Site_Status__c</fullName>
        <label>Site Status</label>
        <type>Text</type>
        <length>50</length>
    </fields>
    <fields>
        <fullName>Build_Status__c</fullName>
        <label>Build Status</label>
        <type>Text</type>
        <length>100</length>
    </fields>
    <fields>
        <fullName>PAL_Signed_Date__c</fullName>
        <label>PAL Signed Date</label>
        <type>Date</type>
    </fields>
    <fields>
        <fullName>Activation_Forecast__c</fullName>
        <label>Activation (Forecast)</label>
        <type>Date</type>
    </fields>
    <fields>
        <fullName>Activation_Actual__c</fullName>
        <label>Activation (Actual)</label>
        <type>Date</type>
    </fields>
    <fields>
        <fullName>MDU_Category__c</fullName>
        <label>MDU Category</label>
        <type>Text</type>
        <length>50</length>
    </fields>
    <fields>
        <fullName>SiteTracker_Record_Id__c</fullName>
        <label>SiteTracker Record ID</label>
        <type>Text</type>
        <length>18</length>
        <externalId>true</externalId>
        <unique>true</unique>
    </fields>
    <fields>
        <fullName>Last_Synced__c</fullName>
        <label>Last Synced</label>
        <type>DateTime</type>
    </fields>
</CustomObject>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>SiteTracker_Project__c</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('objects/SiteTracker_Project__c.object', obj_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f'{sf_main.base_url}metadata/deployRequest'
deploy_body = {'deployOptions': {'checkOnly': False, 'ignoreWarnings': True, 'rollbackOnError': True, 'singlePackage': True}}
boundary = '----DeployBoundary'
body_str = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
    f'{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
    f'Content-Type: application/zip\r\n'
    f'Content-Transfer-Encoding: base64\r\n\r\n'
    f'{zip_b64}\r\n'
    f'--{boundary}--'
)

headers = {'Authorization': f'Bearer {sf_main.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}
resp = requests.post(deploy_url, headers=headers, data=body_str)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
        time.sleep(3)
        check = requests.get(f'{deploy_url}/{deploy_id}?includeDetails=true', headers={'Authorization': f'Bearer {sf_main.session_id}'})
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict): failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            break
else:
    print(resp.text[:500])
