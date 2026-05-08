from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

# Step 1: Create custom object Opportunity_Contact__c (junction)
print("Step 1: Creating Opportunity_Contact__c object...")

obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Opportunity Contact</label>
    <pluralLabel>Opportunity Contacts</pluralLabel>
    <nameField>
        <label>Opportunity Contact Name</label>
        <type>AutoNumber</type>
        <displayFormat>OC-{0000}</displayFormat>
    </nameField>
    <deploymentStatus>Deployed</deploymentStatus>
    <sharingModel>ControlledByParent</sharingModel>
    <fields>
        <fullName>Opportunity__c</fullName>
        <label>Opportunity</label>
        <type>MasterDetail</type>
        <referenceTo>Opportunity</referenceTo>
        <relationshipLabel>Contacts</relationshipLabel>
        <relationshipName>Opportunity_Contacts</relationshipName>
        <relationshipOrder>0</relationshipOrder>
        <reparentableMasterDetail>false</reparentableMasterDetail>
        <writeRequiresMasterRead>false</writeRequiresMasterRead>
    </fields>
    <fields>
        <fullName>Contact__c</fullName>
        <label>Contact</label>
        <type>Lookup</type>
        <referenceTo>Contact</referenceTo>
        <relationshipLabel>Opportunities</relationshipLabel>
        <relationshipName>Opportunity_Contacts</relationshipName>
    </fields>
    <fields>
        <fullName>Role__c</fullName>
        <label>Role</label>
        <type>Picklist</type>
        <valueSet>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Property Manager</fullName><default>false</default><label>Property Manager</label></value>
                <value><fullName>Property Owner</fullName><default>false</default><label>Property Owner</label></value>
                <value><fullName>Leasing Contact</fullName><default>false</default><label>Leasing Contact</label></value>
                <value><fullName>HOA Contact</fullName><default>false</default><label>HOA Contact</label></value>
                <value><fullName>General Contractor</fullName><default>false</default><label>General Contractor</label></value>
                <value><fullName>Developer</fullName><default>false</default><label>Developer</label></value>
                <value><fullName>Legal Contact</fullName><default>false</default><label>Legal Contact</label></value>
                <value><fullName>Broker</fullName><default>false</default><label>Broker</label></value>
                <value><fullName>Other</fullName><default>false</default><label>Other</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity_Contact__c</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('objects/Opportunity_Contact__c.object', obj_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f'{sf.base_url}metadata/deployRequest'
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

resp = requests.post(deploy_url, headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}, data=body_str)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
        time.sleep(3)
        check = requests.get(f'{deploy_url}/{deploy_id}?includeDetails=true', headers={'Authorization': f'Bearer {sf.session_id}'})
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
