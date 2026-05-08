from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time, re, os

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
soap_url = "https://fun-power-747.my.salesforce.com/services/Soap/m/59.0"

page_name = 'Contact_Record_Page_Three_Column'

print(f"Step 1: Retrieving {page_name}...")

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
            <met:members>{page_name}</met:members>
            <met:name>FlexiPage</met:name>
          </met:types>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

resp = requests.post(soap_url, headers={'Content-Type': 'text/xml', 'SOAPAction': 'retrieve'}, data=soap_retrieve)
retrieve_id = re.search(r'<id>([^<]+)</id>', resp.text).group(1)

flexipage_content = None
flexipage_path = None

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
                    if name.endswith('.flexipage'):
                        flexipage_content = zf.read(name).decode('utf-8')
                        flexipage_path = name
                        save_path = os.path.join(SCRIPT_DIR, f'{page_name}.xml')
                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(flexipage_content)
                        print(f"  Saved to {page_name}.xml ({len(flexipage_content)} chars)")
        break
    elif '<done>false</done>' in check_resp.text:
        print("  Still retrieving...")

if not flexipage_content:
    print("ERROR: Could not retrieve FlexiPage")
    exit(1)

has_notes = 'AttachedContentNotes' in flexipage_content
print(f"\n  Already has Notes: {has_notes}")

if has_notes:
    print("  Notes already on this page!")
    exit(0)

# Step 2: Add Notes related list in the leftsidebar region
# The leftsidebar has itemInstances with related lists (Quotes, Opportunities, CampaignMembers)
# Insert Notes before the merge preview card (last item before </name>leftsidebar)
print("\nStep 2: Injecting Notes (AttachedContentNotes) into left sidebar...")

notes_item = """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Contact.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>AttachedContentNotes</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListComponentOverride</name>
                    <value>NONE</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>rowsToDisplay</name>
                    <value>10</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>showActionBar</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentName>force:relatedListSingleContainer</componentName>
                <identifier>force_relatedListSingleContainer_Notes</identifier>
            </componentInstance>
        </itemInstances>
"""

# Also add Opportunity_Contact__c related list while we're at it
opp_contacts_item = """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Contact.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>Opportunity_Contacts__r</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListComponentOverride</name>
                    <value>NONE</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>rowsToDisplay</name>
                    <value>10</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>showActionBar</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentName>force:relatedListSingleContainer</componentName>
                <identifier>force_relatedListSingleContainer_OppContacts</identifier>
            </componentInstance>
        </itemInstances>
"""

# Insert before the merge preview card in the leftsidebar
# Find: runtime_sales_merge:mergeCandidatesPreviewCard in the leftsidebar
merge_marker = '<componentName>runtime_sales_merge:mergeCandidatesPreviewCard</componentName>'
merge_pos = flexipage_content.find(merge_marker)

if merge_pos > 0:
    # Find the <itemInstances> that contains this merge component
    item_start = flexipage_content.rfind('<itemInstances>', 0, merge_pos)
    # Insert our components before this itemInstances block
    flexipage_content = flexipage_content[:item_start] + notes_item + opp_contacts_item + flexipage_content[item_start:]
    print("  Injected Notes + Opportunity Contacts in left sidebar (before merge card)")
else:
    # Fallback: insert before <name>leftsidebar</name>
    sidebar_marker = '<name>leftsidebar</name>'
    sidebar_pos = flexipage_content.find(sidebar_marker)
    if sidebar_pos > 0:
        # Find the closing </itemInstances> just before the name tag
        last_item_end = flexipage_content.rfind('</itemInstances>', 0, sidebar_pos)
        insert_pos = last_item_end + len('</itemInstances>')
        flexipage_content = flexipage_content[:insert_pos] + '\n' + notes_item + opp_contacts_item + flexipage_content[insert_pos:]
        print("  Injected Notes + Opportunity Contacts before sidebar name tag")
    else:
        print("  ERROR: Could not find leftsidebar region")
        exit(1)

# Step 3: Deploy
print("\nStep 3: Deploying updated Contact FlexiPage...")

deploy_name = flexipage_path.replace('unpackaged/', '')

deploy_package = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>{page_name}</members>
        <name>FlexiPage</name>
    </types>
    <version>59.0</version>
</Package>"""

deploy_buf = io.BytesIO()
with zipfile.ZipFile(deploy_buf, 'w', zipfile.ZIP_DEFLATED) as dzf:
    dzf.writestr('package.xml', deploy_package)
    dzf.writestr(deploy_name, flexipage_content)
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
                print("\n  Contact page updated!")
                print("  Added: Notes (AttachedContentNotes) + Opportunity Contacts in left sidebar")
            break
else:
    print(f"  Deploy error: {deploy_resp.text[:500]}")

print("\nDone!")
