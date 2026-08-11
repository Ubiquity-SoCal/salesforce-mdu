from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Step 1: Retrieve current Contact layout to see what we're working with
print("Step 1: Reading current Contact page layout...")
try:
    result = sf.restful(f'tooling/query?q=SELECT+Id,Name,FullName+FROM+Layout+WHERE+EntityDefinitionId=\'Contact\'', method='GET')
    for r in result.get('records', []):
        print(f"  Layout: {r['FullName']} (ID: {r['Id']})")
except Exception as e:
    print(f"  Query error: {e}")

# Step 2: Deploy updated Contact layout with Opportunity_Contacts related list
print("\nStep 2: Adding Opportunity_Contact__c related list to Contact layout...")

layout_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <relatedLists>
        <relatedList>Opportunity_Contact__c.Contact__c</relatedList>
        <fields>Opportunity__c</fields>
        <fields>Role__c</fields>
        <fields>NAME</fields>
        <columns>4</columns>
        <sortField>NAME</sortField>
        <sortOrder>Asc</sortOrder>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedActivityList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedActivityHistoryList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedNoteList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedFileList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>CaseRelatedList</relatedList>
    </relatedLists>
    <showEmailCheckbox>false</showEmailCheckbox>
    <showHighlightsPanel>true</showHighlightsPanel>
    <showRunAssignmentRulesCheckbox>false</showRunAssignmentRulesCheckbox>
    <showSubmitAndAttachButton>false</showSubmitAndAttachButton>
</Layout>"""

# Problem: deploying a bare layout will wipe the field sections.
# Better approach: use the Metadata API to READ the current layout, inject our related list, then redeploy.

print("\nStep 2b: Retrieving full Contact layout via Metadata API...")

# Build retrieve request
retrieve_package = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Contact-Contact Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', retrieve_package)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

# Use SOAP API for retrieve
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
            <met:members>Contact-Contact Layout</met:members>
            <met:name>Layout</met:name>
          </met:types>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

metadata_url = sf.base_url.replace('/data/', '/metadata/')
soap_url = f"https://fun-power-747.my.salesforce.com/services/Soap/m/59.0/{sf.sf_instance.split('.')[0] if '.' in sf.sf_instance else ''}"
# Use the proper metadata SOAP endpoint
soap_url = f"https://fun-power-747.my.salesforce.com/services/Soap/m/59.0"

resp = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'retrieve'}, data=soap_retrieve)
print(f"  Retrieve request: {resp.status_code}")

if resp.status_code == 200 and '<id>' in resp.text:
    import re
    retrieve_id = re.search(r'<id>([^<]+)</id>', resp.text).group(1)
    print(f"  Retrieve ID: {retrieve_id}")

    # Poll for retrieve result
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
            print("  Retrieve complete!")

            # Extract the zip
            zip_match = re.search(r'<zipFile>([^<]+)</zipFile>', check_resp.text)
            if zip_match:
                zip_data = base64.b64decode(zip_match.group(1))
                with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                    print(f"  Files in retrieved package: {zf.namelist()}")

                    # Find and read the layout
                    for name in zf.namelist():
                        if 'layout' in name.lower() and name.endswith('.layout'):
                            layout_content = zf.read(name).decode('utf-8')
                            print(f"\n  Current layout file: {name}")
                            print(f"  Layout length: {len(layout_content)} chars")

                            # Check if Opportunity_Contact__c related list already exists
                            if 'Opportunity_Contact__c' in layout_content:
                                print("\n  Opportunity_Contact__c related list ALREADY on Contact layout!")
                                break

                            # Inject our related list before the first existing relatedList
                            opp_contact_related = """    <relatedLists>
        <relatedList>Opportunity_Contact__c.Contact__c</relatedList>
        <fields>Opportunity__c</fields>
        <fields>Role__c</fields>
        <fields>NAME</fields>
        <sortField>NAME</sortField>
        <sortOrder>Asc</sortOrder>
    </relatedLists>
"""

                            if '<relatedLists>' in layout_content:
                                # Insert before the first relatedLists block
                                layout_content = layout_content.replace(
                                    '    <relatedLists>',
                                    opp_contact_related + '    <relatedLists>',
                                    1  # Only replace first occurrence
                                )
                            else:
                                # No related lists yet — add before closing tag
                                layout_content = layout_content.replace(
                                    '</Layout>',
                                    opp_contact_related + '</Layout>'
                                )

                            print("  Injected Opportunity_Contact__c related list")

                            # Deploy the modified layout
                            print("\nStep 3: Deploying updated Contact layout...")

                            deploy_package = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Contact-Contact Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""

                            # Strip 'unpackaged/' prefix for deploy
                            deploy_name = name.replace('unpackaged/', '')
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
                                            print("\n  Contact layout updated! Opportunity_Contact__c related list now shows on Contact records.")
                                            print("  Columns: Opportunity, Role, Record Name")
                                        break
                            else:
                                print(f"  Deploy error: {deploy_resp.text[:500]}")
                            break
            else:
                print("  No zip data in retrieve response")
            break
        elif '<done>false</done>' in check_resp.text:
            print(f"  Still retrieving...")
        else:
            print(f"  Unexpected response")
else:
    print(f"  Error: {resp.text[:500]}")

print("\nDone!")
