from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Karate88!',
    security_token='Ktc1n9mLmD9vwEcVcl45q0iAD'
)

# Assign layouts to record types via Profile metadata
profile_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
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
    </layoutAssignments>
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
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('profiles/Admin.profile', profile_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

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

headers = {
    'Authorization': f'Bearer {sf.session_id}',
    'Content-Type': f'multipart/form-data; boundary={boundary}'
}
resp = requests.post(deploy_url, headers=headers, data=body_str)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
        time.sleep(3)
        check = requests.get(
            f'{deploy_url}/{deploy_id}?includeDetails=true',
            headers={'Authorization': f'Bearer {sf.session_id}'}
        )
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict):
                    failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            break
else:
    print(resp.text[:500])
