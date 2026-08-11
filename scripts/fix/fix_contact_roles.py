from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# 1. Replace Contact Role picklist values via Metadata API
# 2. Add Contact Roles back to FlexiPage left sidebar

# Step 1: Update the Role picklist on OpportunityContactRole
obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Role</fullName>
        <type>Picklist</type>
        <picklist>
            <picklistValues><fullName>Property Manager</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Property Owner</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Leasing Contact</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>HOA Contact</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>General Contractor</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Developer</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Legal Contact</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Broker</fullName><default>false</default></picklistValues>
            <picklistValues><fullName>Other</fullName><default>false</default></picklistValues>
            <sorted>false</sorted>
        </picklist>
    </fields>
</CustomObject>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpportunityContactRole</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('objects/OpportunityContactRole.object', obj_xml)
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

resp = requests.post(
    deploy_url,
    headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    data=body_str
)
print(f'Step 1 - Role picklist deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(10):
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

# Step 2: Add Contact Roles back to FlexiPage left sidebar
print("\nStep 2 - Adding Contact Roles to FlexiPage sidebar...")
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

resp = requests.get(f'{sf.base_url}tooling/sobjects/FlexiPage/0M0Hs000001HrilKAC', headers=headers)
metadata = resp.json().get('Metadata', {})

for region in metadata.get('flexiPageRegions', []):
    if region.get('name') != 'leftsidebar':
        continue

    # Find where Agreements is, insert Contact Roles after it
    items = region['itemInstances']
    insert_idx = 1  # after highlights panel by default
    for i, item in enumerate(items):
        ci = item.get('componentInstance')
        if ci:
            props = {p['name']: p.get('value') for p in ci.get('componentInstanceProperties', [])}
            if props.get('relatedListApiName') == 'Agreements__r':
                insert_idx = i  # before Agreements
                break

    contact_roles_component = {
        "componentInstance": {
            "componentInstanceProperties": [
                {"name": "parentFieldApiName", "type": None, "value": "Opportunity.Id", "valueList": None},
                {"name": "relatedListApiName", "type": None, "value": "OpportunityContactRoles", "valueList": None},
                {"name": "relatedListComponentOverride", "type": None, "value": "NONE", "valueList": None},
                {"name": "rowsToDisplay", "type": None, "value": "10", "valueList": None},
                {"name": "showActionBar", "type": None, "value": "true", "valueList": None}
            ],
            "componentName": "force:relatedListSingleContainer",
            "componentType": None,
            "flexipageDataSources": None,
            "identifier": "force_relatedListSingleContainer3",
            "visibilityRule": None
        },
        "fieldInstance": None
    }

    items.insert(insert_idx, contact_roles_component)
    print(f"Inserted Contact Roles at position {insert_idx}")

    for i, item in enumerate(items):
        ci = item.get('componentInstance')
        if ci:
            props = {p['name']: p.get('value') for p in ci.get('componentInstanceProperties', [])}
            print(f"  [{i}] {props.get('relatedListApiName', ci.get('componentName'))}")

update_body = {
    'Metadata': metadata,
    'FullName': 'Opportunity_Record_Page_Three_Column'
}
resp = requests.patch(
    f'{sf.base_url}tooling/sobjects/FlexiPage/0M0Hs000001HrilKAC',
    headers=headers,
    json=update_body
)
print(f'FlexiPage update: {resp.status_code}')
print(resp.text[:300] if resp.text else 'OK')

# Step 3: Also add OpportunityContactRoles to the page layout related lists
print("\nStep 3 - Adding Contact Roles to page layout related lists...")
resp = requests.get(f'{sf.base_url}tooling/sobjects/Layout/00hHs00000dMIY9IAO', headers=headers)
layout_meta = resp.json().get('Metadata', {})

existing_rls = layout_meta.get('relatedLists') or []
has_contact_roles = any(rl.get('relatedList') == 'RelatedContactRoleList' for rl in existing_rls)
if not has_contact_roles:
    existing_rls.insert(0, {
        'customButtons': [],
        'excludeButtons': [],
        'fields': ['CONTACT.FULL_NAME', 'CONTACT.TITLE', 'CONTACT.EMAIL', 'CONTACT.PHONE1', 'ROLE'],
        'quickActions': [],
        'relatedList': 'RelatedContactRoleList',
        'sortField': None,
        'sortOrder': None
    })
    layout_meta['relatedLists'] = existing_rls
    print("Added RelatedContactRoleList to page layout")
else:
    print("Contact Roles already in page layout")

# Can't update layout via Tooling API easily, use Metadata deploy
layout_xml_parts = []
for rl in existing_rls:
    fields_xml = "\n".join([f"        <fields>{f}</fields>" for f in rl.get('fields', [])])
    layout_xml_parts.append(f"""    <relatedLists>
        <relatedList>{rl['relatedList']}</relatedList>
{fields_xml}
    </relatedLists>""")

# Get sections from current layout
sections_xml = []
for section in layout_meta.get('layoutSections', []):
    label = section.get('label', '')
    style = section.get('style', 'TwoColumnsTopToBottom')
    cols_xml = []
    for col in (section.get('layoutColumns') or []):
        if col is None:
            cols_xml.append("        <layoutColumns/>")
            continue
        items_xml = []
        for item in (col.get('layoutItems') or []):
            field = item.get('field')
            behavior = item.get('behavior', 'Edit')
            if field:
                items_xml.append(f"            <layoutItems><behavior>{behavior}</behavior><field>{field}</field></layoutItems>")
        if items_xml:
            cols_xml.append("        <layoutColumns>\n" + "\n".join(items_xml) + "\n        </layoutColumns>")
        else:
            cols_xml.append("        <layoutColumns/>")

    sections_xml.append(f"""    <layoutSections>
        <label>{label}</label>
        <style>{style}</style>
{chr(10).join(cols_xml)}
    </layoutSections>""")

full_layout_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n' + "\n".join(sections_xml) + "\n" + "\n".join(layout_xml_parts) + "\n</Layout>"

layout_package = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity-Opportunity Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""

buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', layout_package)
    zf.writestr('layouts/Opportunity-Opportunity Layout.layout', full_layout_xml)
buf2.seek(0)
zip_b64_2 = base64.b64encode(buf2.read()).decode()

body_str2 = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
    f'{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
    f'Content-Type: application/zip\r\n'
    f'Content-Transfer-Encoding: base64\r\n\r\n'
    f'{zip_b64_2}\r\n'
    f'--{boundary}--'
)

resp3 = requests.post(
    deploy_url,
    headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    data=body_str2
)
print(f'Layout deploy: {resp3.status_code}')
if resp3.status_code == 201:
    deploy_id = resp3.json().get('id')
    for i in range(10):
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
