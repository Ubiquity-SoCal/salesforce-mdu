"""
Fix the two issues from taylor_revisions.py:
1. Deploy new fields via Metadata API (Tooling API created them but they're not visible)
2. Fix MDU layout (add Probability field)
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)
print(f"Connected: {sf.sf_instance}")

def deploy_zip(zf_buffer, label="deploy"):
    zf_buffer.seek(0)
    zip_b64 = base64.b64encode(zf_buffer.read()).decode()
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
    print(f'{label}: {resp.status_code}')
    if resp.status_code == 201:
        deploy_id = resp.json().get('id')
        for i in range(20):
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
                return status
    else:
        print(resp.text[:500])
        return 'Error'


# ============================================================
# STEP 1: Deploy new fields via Metadata API
# ============================================================
print("\n=== STEP 1: Deploying new fields via Metadata API ===")

object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Prospective_ISP_List__c</fullName>
        <label>Prospective ISP</label>
        <type>MultiselectPicklist</type>
        <visibleLines>4</visibleLines>
        <valueSet>
            <valueSetDefinition>
                <sorted>true</sorted>
                <value><fullName>AT_T</fullName><default>false</default><label>AT&amp;T</label></value>
                <value><fullName>Atlas</fullName><default>false</default><label>Atlas</label></value>
                <value><fullName>FiberFirst</fullName><default>false</default><label>FiberFirst</label></value>
                <value><fullName>Lumen_Quantum_Fiber</fullName><default>false</default><label>Lumen / Quantum Fiber</label></value>
                <value><fullName>Ting</fullName><default>false</default><label>Ting</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
    <fields>
        <fullName>Confirmed_ISP_List__c</fullName>
        <label>Confirmed ISP</label>
        <type>MultiselectPicklist</type>
        <visibleLines>4</visibleLines>
        <valueSet>
            <valueSetDefinition>
                <sorted>true</sorted>
                <value><fullName>AT_T</fullName><default>false</default><label>AT&amp;T</label></value>
                <value><fullName>Atlas</fullName><default>false</default><label>Atlas</label></value>
                <value><fullName>FiberFirst</fullName><default>false</default><label>FiberFirst</label></value>
                <value><fullName>Lumen_Quantum_Fiber</fullName><default>false</default><label>Lumen / Quantum Fiber</label></value>
                <value><fullName>Ting</fullName><default>false</default><label>Ting</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
    <fields>
        <fullName>HOA__c</fullName>
        <label>HOA</label>
        <type>Checkbox</type>
        <defaultValue>false</defaultValue>
    </fields>
    <fields>
        <fullName>Brownfield_Greenfield__c</fullName>
        <label>Brownfield / Greenfield</label>
        <type>Picklist</type>
        <valueSet>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Brownfield</fullName><default>false</default><label>Brownfield</label></value>
                <value><fullName>Greenfield</fullName><default>false</default><label>Greenfield</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('objects/Opportunity.object', object_xml)
    zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

result = deploy_zip(buf, "New fields deploy")
if result != 'Succeeded':
    print("Field deploy failed, stopping.")
    exit(1)


# ============================================================
# STEP 2: Verify fields are visible
# ============================================================
print("\n=== STEP 2: Verifying fields ===")
# Reconnect to get fresh schema
sf2 = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)
desc = sf2.Opportunity.describe()
field_names = {f['name'] for f in desc['fields']}
for name in ['Prospective_ISP_List__c', 'Confirmed_ISP_List__c', 'HOA__c', 'Brownfield_Greenfield__c']:
    status = 'FOUND' if name in field_names else 'MISSING'
    print(f"  {name}: {status}")


# ============================================================
# STEP 3: Migrate ISP data
# ============================================================
print("\n=== STEP 3: Migrating ISP data ===")

isp_mapping = {
    'at&t': 'AT_T',
    'atlas': 'Atlas',
    'fiberfirst': 'FiberFirst',
    'fiber first': 'FiberFirst',
    'lumen': 'Lumen_Quantum_Fiber',
    'quantum fiber': 'Lumen_Quantum_Fiber',
    'ting': 'Ting',
}

rest_headers = {
    'Authorization': f'Bearer {sf2.session_id}',
    'Content-Type': 'application/json'
}
base_rest = f"https://{sf2.sf_instance}/services/data/v59.0/sobjects/Opportunity"

def match_isp(text):
    matched = set()
    lower = text.lower()
    for key, val in isp_mapping.items():
        if key in lower:
            matched.add(val)
    return matched

# Prospective ISP
opps = sf2.query_all("SELECT Id, Prospective_ISP__c FROM Opportunity WHERE Prospective_ISP__c != null")
migrated_p = 0
for opp in opps['records']:
    old_val = (opp.get('Prospective_ISP__c') or '').strip()
    if not old_val:
        continue
    matched = match_isp(old_val)
    if matched:
        resp = requests.patch(f"{base_rest}/{opp['Id']}", headers=rest_headers,
                              json={'Prospective_ISP_List__c': ';'.join(sorted(matched))})
        if resp.status_code == 204:
            migrated_p += 1
        elif migrated_p == 0:
            print(f"    First error: {resp.status_code}: {resp.text[:200]}")
print(f"  Migrated {migrated_p}/{opps['totalSize']} Prospective ISP records")

# Confirmed ISP
opps = sf2.query_all("SELECT Id, Confirmed_ISP__c FROM Opportunity WHERE Confirmed_ISP__c != null")
migrated_c = 0
for opp in opps['records']:
    old_val = (opp.get('Confirmed_ISP__c') or '').strip()
    if not old_val:
        continue
    matched = match_isp(old_val)
    if matched:
        resp = requests.patch(f"{base_rest}/{opp['Id']}", headers=rest_headers,
                              json={'Confirmed_ISP_List__c': ';'.join(sorted(matched))})
        if resp.status_code == 204:
            migrated_c += 1
        elif migrated_c == 0:
            print(f"    First error: {resp.status_code}: {resp.text[:200]}")
print(f"  Migrated {migrated_c}/{opps['totalSize']} Confirmed ISP records")


# ============================================================
# STEP 4: Deploy fixed MDU layout (with Probability)
# ============================================================
print("\n=== STEP 4: Deploying fixed MDU layout ===")

contacts_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Contact__c</fields>
        <fields>Role__c</fields>
        <relatedList>Opportunity_Contact__c.Opportunity__c</relatedList>
    </relatedLists>"""

agreements_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Agreement_Type__c</fields>
        <fields>Status__c</fields>
        <fields>Signed_Date__c</fields>
        <fields>IronClad_ID__c</fields>
        <relatedList>Agreement__c.Opportunity__c</relatedList>
    </relatedLists>"""

sitetracker_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Site_Name__c</fields>
        <fields>Build_Status__c</fields>
        <fields>Site_Status__c</fields>
        <fields>Activation_Forecast__c</fields>
        <relatedList>SiteTracker_Project__c.Opportunity__c</relatedList>
    </relatedLists>"""

notes_rl = """
    <relatedLists>
        <relatedList>RelatedNoteList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedContentNoteList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedFileList</relatedList>
    </relatedLists>"""

footer = """
    <showHighlightsPanel>false</showHighlightsPanel>
    <showRunAssignmentRulesCheckbox>false</showRunAssignmentRulesCheckbox>
    <showSubmitAndAttachButton>false</showSubmitAndAttachButton>
</Layout>"""

mdu_layout_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <layoutSections>
        <label>Opportunity Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Required</behavior><field>Name</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>AccountId</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Agreement_Name__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Contact__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Loss_Reason__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Hold_Reason__c</field></layoutItems>
            <layoutItems><behavior>Readonly</behavior><field>Agreement_Count__c</field></layoutItems>
            <layoutItems><behavior>Readonly</behavior><field>Notes_Count__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>OwnerId</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>StageName</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Sales_Status__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Probability</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Projected_Close_Date__c</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>CloseDate</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>RE_Assigned__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Property Details</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Units__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Classification__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Category__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>HOA__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Build_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Brownfield_Greenfield__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Address__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_City__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_State__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Zip__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>ISP Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Prospective_ISP_List__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Confirmed_ISP_List__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Incumbent_Provider__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Incumbent_Agreement_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Incumbent_Agreement_Expiration__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Integration Links</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>SiteTracker_Project_ID__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>SiteTracker_URL__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>IronClad_URL__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Migration Reference</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Monday_Item_ID__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns/>
    </layoutSections>
    <layoutSections>
        <customLabel>true</customLabel>
        <label>System Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>CreatedById</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>LastModifiedById</field></layoutItems>
        </layoutColumns>
    </layoutSections>""" + contacts_rl + agreements_rl + sitetracker_rl + notes_rl + footer

buf3 = io.BytesIO()
with zipfile.ZipFile(buf3, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('layouts/Opportunity-MDU Opportunity Layout.layout', mdu_layout_xml)
    zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity-MDU Opportunity Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>""")

result = deploy_zip(buf3, "MDU Layout deploy")

if result == 'Succeeded':
    print("\n=== ALL FIXES COMPLETE ===")
else:
    print(f"\nLayout deploy returned: {result}")
