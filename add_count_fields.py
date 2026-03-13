"""Add Agreement Count (rollup) and Notes Count fields to Opportunity."""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time, re

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')
soap_url = "https://fun-power-747.my.salesforce.com/services/Soap/m/59.0"

# Deploy both fields via a single CustomObject package (the way that works)
print("Step 1: Creating count fields...")

obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Agreement_Count__c</fullName>
        <label>Agreement Count</label>
        <type>Summary</type>
        <summaryForeignKey>Agreement__c.Opportunity__c</summaryForeignKey>
        <summaryOperation>count</summaryOperation>
        <inlineHelpText>Number of agreements linked to this opportunity</inlineHelpText>
    </fields>
    <fields>
        <fullName>Notes_Count__c</fullName>
        <label>Notes Count</label>
        <type>Number</type>
        <precision>5</precision>
        <scale>0</scale>
        <defaultValue>0</defaultValue>
        <inlineHelpText>Number of notes on this opportunity</inlineHelpText>
    </fields>
</CustomObject>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('objects/Opportunity.object', obj_xml)
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
print(f"  Deploy: {resp.status_code}")

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
            elif status == 'Succeeded':
                print("  Fields created!")
            break
else:
    print(f"  Error: {resp.text[:500]}")

# Step 2: Update Notes_Count__c for sample Opportunities
print("\nStep 2: Updating Notes Count for sample Opps...")

sample_opp_ids = [
    "006WR00000udaZhYAI",  # Waterstone
    "006WR00000udTrcYAE",  # Olympus Waterford
    "006WR00000ucC3BYAU",  # Town East
    "006WR00000udDmlYAE",  # 120 Sunset Dr
]

for opp_id in sample_opp_ids:
    count_result = sf.query(f"SELECT COUNT() FROM ContentDocumentLink WHERE LinkedEntityId = '{opp_id}' AND ContentDocument.FileType = 'SNOTE'")
    count = count_result['totalSize']

    opp = sf.query(f"SELECT Name FROM Opportunity WHERE Id = '{opp_id}'")
    name = opp['records'][0]['Name']

    sf.Opportunity.update(opp_id, {'Notes_Count__c': count})
    print(f"  {name}: {count} notes")

# Step 3: Add count fields to Opportunity page layout
print("\nStep 3: Adding count fields to page layout...")

soap_retrieve = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sf.session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:retrieve><met:retrieveRequest><met:apiVersion>59.0</met:apiVersion>
    <met:unpackaged><met:types><met:members>Opportunity-Opportunity Layout</met:members><met:name>Layout</met:name></met:types></met:unpackaged>
  </met:retrieveRequest></met:retrieve></soapenv:Body>
</soapenv:Envelope>"""

resp = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'retrieve'}, data=soap_retrieve)
rid = re.search(r'<id>([^<]+)</id>', resp.text).group(1)

layout_content = None
for i in range(15):
    time.sleep(3)
    check_soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sf.session_id}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkRetrieveStatus><met:asyncProcessId>{rid}</met:asyncProcessId><met:includeZip>true</met:includeZip></met:checkRetrieveStatus></soapenv:Body>
</soapenv:Envelope>"""
    cr = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'checkRetrieveStatus'}, data=check_soap)
    if '<done>true</done>' in cr.text:
        zm = re.search(r'<zipFile>([^<]+)</zipFile>', cr.text)
        zd = base64.b64decode(zm.group(1))
        with zipfile.ZipFile(io.BytesIO(zd)) as zf:
            for name in zf.namelist():
                if name.endswith('.layout'):
                    layout_content = zf.read(name).decode('utf-8')
        break

if layout_content:
    # Add after Agreement_Name__c field
    if 'Agreement_Count__c' not in layout_content:
        count_fields = """            <layoutItems>
                <behavior>Readonly</behavior>
                <field>Agreement_Count__c</field>
            </layoutItems>
            <layoutItems>
                <behavior>Readonly</behavior>
                <field>Notes_Count__c</field>
            </layoutItems>"""

        layout_content = layout_content.replace(
            '                <field>Agreement_Name__c</field>\n            </layoutItems>\n        </layoutColumns>',
            '                <field>Agreement_Name__c</field>\n            </layoutItems>\n' + count_fields + '\n        </layoutColumns>'
        )

        pkg = '<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata"><types><members>Opportunity-Opportunity Layout</members><name>Layout</name></types><version>59.0</version></Package>'
        dbuf = io.BytesIO()
        with zipfile.ZipFile(dbuf, 'w', zipfile.ZIP_DEFLATED) as dzf:
            dzf.writestr('package.xml', pkg)
            dzf.writestr('layouts/Opportunity-Opportunity Layout.layout', layout_content)
        dbuf.seek(0)

        body2 = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="json"\r\n'
            f'Content-Type: application/json\r\n\r\n'
            f'{json.dumps(deploy_body)}\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
            f'Content-Type: application/zip\r\n'
            f'Content-Transfer-Encoding: base64\r\n\r\n'
            f'{base64.b64encode(dbuf.read()).decode()}\r\n'
            f'--{boundary}--'
        )

        resp2 = requests.post(deploy_url, headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}, data=body2)
        print(f"  Layout deploy: {resp2.status_code}")
        if resp2.status_code == 201:
            did = resp2.json().get('id')
            for j in range(15):
                time.sleep(3)
                cr2 = requests.get(f'{deploy_url}/{did}?includeDetails=true', headers={'Authorization': f'Bearer {sf.session_id}'})
                s = cr2.json().get('deployResult', {}).get('status', '?')
                print(f'  {s}')
                if s in ('Succeeded', 'Failed', 'Canceled'):
                    if s == 'Failed':
                        fails = cr2.json()['deployResult']['details'].get('componentFailures', [])
                        if isinstance(fails, dict): fails = [fails]
                        for ff in fails:
                            print(f'  FAIL: {ff.get("problem")}')
                    break
    else:
        print("  Count fields already on layout")

print("\nDone!")
