from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Fix 1: Update Role picklist - use ContractContactRole value set name
# The standard value set for OpportunityContactRole.Role is "OpptyContactRole"
obj_xml = """<?xml version="1.0" encoding="UTF-8"?>
<StandardValueSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <sorted>false</sorted>
    <standardValue>
        <fullName>Property Manager</fullName>
        <default>false</default>
        <label>Property Manager</label>
    </standardValue>
    <standardValue>
        <fullName>Property Owner</fullName>
        <default>false</default>
        <label>Property Owner</label>
    </standardValue>
    <standardValue>
        <fullName>Leasing Contact</fullName>
        <default>false</default>
        <label>Leasing Contact</label>
    </standardValue>
    <standardValue>
        <fullName>HOA Contact</fullName>
        <default>false</default>
        <label>HOA Contact</label>
    </standardValue>
    <standardValue>
        <fullName>General Contractor</fullName>
        <default>false</default>
        <label>General Contractor</label>
    </standardValue>
    <standardValue>
        <fullName>Developer</fullName>
        <default>false</default>
        <label>Developer</label>
    </standardValue>
    <standardValue>
        <fullName>Legal Contact</fullName>
        <default>false</default>
        <label>Legal Contact</label>
    </standardValue>
    <standardValue>
        <fullName>Broker</fullName>
        <default>false</default>
        <label>Broker</label>
    </standardValue>
    <standardValue>
        <fullName>Other</fullName>
        <default>false</default>
        <label>Other</label>
    </standardValue>
</StandardValueSet>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>OpptyContactRole</members>
        <name>StandardValueSet</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('standardValueSets/OpptyContactRole.standardValueSet', obj_xml)
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
print(f'Step 1 - Role picklist: {resp.status_code}')
if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(10):
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

# Fix 2: Layout with correct field names (ContactId, Role instead of CONTACT.FULL_NAME)
print("\nStep 2 - Layout with Contact Roles...")
headers2 = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
resp = requests.get(f'{sf.base_url}tooling/sobjects/Layout/00hHs00000dMIY9IAO', headers=headers2)
layout_meta = resp.json().get('Metadata', {})

existing_rls = layout_meta.get('relatedLists') or []
existing_rls = [rl for rl in existing_rls if rl.get('relatedList') != 'RelatedContactRoleList']
existing_rls.insert(0, {
    'customButtons': [],
    'excludeButtons': [],
    'fields': ['ContactId', 'Role', 'IsPrimary'],
    'quickActions': [],
    'relatedList': 'RelatedContactRoleList',
    'sortField': None,
    'sortOrder': None
})

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
    sections_xml.append(f"    <layoutSections>\n        <label>{label}</label>\n        <style>{style}</style>\n" + "\n".join(cols_xml) + "\n    </layoutSections>")

rl_xml_parts = []
for rl in existing_rls:
    fields_xml = "\n".join([f"        <fields>{f}</fields>" for f in rl.get('fields', [])])
    rl_xml_parts.append(f"    <relatedLists>\n        <relatedList>{rl['relatedList']}</relatedList>\n{fields_xml}\n    </relatedLists>")

full_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<Layout xmlns="http://soap.sforce.com/2006/04/metadata">\n' + "\n".join(sections_xml) + "\n" + "\n".join(rl_xml_parts) + "\n</Layout>"

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
    zf.writestr('layouts/Opportunity-Opportunity Layout.layout', full_xml)
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

resp2 = requests.post(
    deploy_url,
    headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    data=body_str2
)
print(f'Layout deploy: {resp2.status_code}')
if resp2.status_code == 201:
    deploy_id = resp2.json().get('id')
    for i in range(10):
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

# Verify picklist
print("\nVerifying role picklist...")
sf2 = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
desc = sf2.OpportunityContactRole.describe()
for f in desc['fields']:
    if f['name'] == 'Role':
        for pv in f['picklistValues']:
            print(f"  {pv['value']} (active: {pv['active']})")
