from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time, re, os

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
soap_url = "https://fun-power-747.my.salesforce.com/services/Soap/m/59.0"

# Step 1: Retrieve the Opportunity page layout
print("Step 1: Retrieving Opportunity layout...")

soap_retrieve = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{sf.session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>59.0</met:apiVersion>
        <met:unpackaged>
          <met:types>
            <met:members>Opportunity-Opportunity Layout</met:members>
            <met:name>Layout</met:name>
          </met:types>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

resp = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'retrieve'}, data=soap_retrieve)
retrieve_id = re.search(r'<id>([^<]+)</id>', resp.text).group(1)

layout_content = None
layout_path = None

for i in range(15):
    time.sleep(3)
    check_soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header>
    <met:SessionHeader>
      <met:sessionId>{sf.session_id}</met:sessionId>
    </met:SessionHeader>
  </soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus>
      <met:asyncProcessId>{retrieve_id}</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""

    check_resp = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'checkRetrieveStatus'}, data=check_soap)

    if '<done>true</done>' in check_resp.text:
        print("  Retrieved!")
        zip_match = re.search(r'<zipFile>([^<]+)</zipFile>', check_resp.text)
        if zip_match:
            zip_data = base64.b64decode(zip_match.group(1))
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for name in zf.namelist():
                    if name.endswith('.layout'):
                        layout_content = zf.read(name).decode('utf-8')
                        layout_path = name
                        save_path = os.path.join(SCRIPT_DIR, 'Opportunity_Layout_Current.xml')
                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(layout_content)
                        print(f"  Saved ({len(layout_content)} chars)")
        break
    elif '<done>false</done>' in check_resp.text:
        print("  Still retrieving...")

if not layout_content:
    print("ERROR: Could not retrieve layout")
    exit(1)

# Check existing related lists
print("\n  Current related lists:")
for m in re.finditer(r'<relatedList>([^<]+)</relatedList>', layout_content):
    print(f"    - {m.group(1)}")

has_notes = 'RelatedNoteList' in layout_content or 'AttachedContentNotes' in layout_content
print(f"\n  Has Notes related list: {has_notes}")

if has_notes:
    print("  Already there!")
    exit(0)

# Step 2: Add Notes related list
print("\nStep 2: Adding Notes & Attachments related list...")

notes_related = """    <relatedLists>
        <relatedList>RelatedNoteList</relatedList>
    </relatedLists>
"""

# Insert before the last </relatedLists> closing, or before </Layout>
last_related_end = layout_content.rfind('</relatedLists>')
if last_related_end > 0:
    insert_pos = last_related_end + len('</relatedLists>')
    layout_content = layout_content[:insert_pos] + '\n' + notes_related + layout_content[insert_pos:]
    print("  Injected after last related list")
else:
    layout_content = layout_content.replace('</Layout>', notes_related + '</Layout>')
    print("  Injected before closing tag")

# Step 3: Deploy
print("\nStep 3: Deploying...")

deploy_name = layout_path.replace('unpackaged/', '')

deploy_package = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity-Opportunity Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""

deploy_buf = io.BytesIO()
with zipfile.ZipFile(deploy_buf, 'w', zipfile.ZIP_DEFLATED) as dzf:
    dzf.writestr('package.xml', deploy_package)
    dzf.writestr(deploy_name, layout_content)
deploy_buf.seek(0)
deploy_b64 = base64.b64encode(deploy_buf.read()).decode()

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
    f'{deploy_b64}\r\n'
    f'--{boundary}--'
)

deploy_resp = requests.post(deploy_url, headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}, data=body_str)
print(f"  Deploy: {deploy_resp.status_code}")

if deploy_resp.status_code == 201:
    deploy_id = deploy_resp.json().get('id')
    for j in range(15):
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
                print("\n  Opportunity layout updated! Notes related list added.")
                print("  That grey box should now show Notes properly.")
            break
else:
    print(f"  Deploy error: {deploy_resp.text[:500]}")

print("\nDone!")
