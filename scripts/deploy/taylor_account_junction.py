"""
Taylor Revisions follow-up (4/17): Opportunity -> Multi-Account junction + misc.

Builds:
  A) Custom object Opportunity_Account__c with fields
       Opportunity__c (Master-Detail, required)
       Account__c     (Lookup)
       Is_Primary__c  (Checkbox)
       Role__c        (Picklist, optional: Owner / Management Company / Portfolio / Other)
  B) Record-triggered Flow on Opportunity_Account__c:
       - When Is_Primary__c = true: unset other primaries on same Opp, sync to Opp.AccountId
  C) Add related list to MDU Opportunity Layout
  D) Backfill junction records from existing AccountId / Management_Company__c / Portfolio__c
  E) Clear Units__c inlineHelpText (label "Living Units")
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time, sys

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)
print(f"Connected: {sf.sf_instance}\n")

# ---------------------------------------------------------------
# Metadata deploy helper
# ---------------------------------------------------------------
def deploy_zip(zf_buffer, label="deploy"):
    zf_buffer.seek(0)
    zip_b64 = base64.b64encode(zf_buffer.read()).decode()
    deploy_url = f'{sf.base_url}metadata/deployRequest'
    deploy_body = {'deployOptions': {
        'checkOnly': False, 'ignoreWarnings': True,
        'rollbackOnError': True, 'singlePackage': True
    }}
    boundary = '----DeployBoundary'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="json"\r\nContent-Type: application/json\r\n\r\n'
        f'{json.dumps(deploy_body)}\r\n--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
        f'Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n'
        f'{zip_b64}\r\n--{boundary}--'
    )
    headers = {'Authorization': f'Bearer {sf.session_id}',
               'Content-Type': f'multipart/form-data; boundary={boundary}'}
    resp = requests.post(deploy_url, headers=headers, data=body)
    print(f'{label}: HTTP {resp.status_code}')
    if resp.status_code != 201:
        print(resp.text[:500])
        return 'Error'
    deploy_id = resp.json().get('id')
    for _ in range(30):
        time.sleep(3)
        check = requests.get(f'{deploy_url}/{deploy_id}?includeDetails=true',
                             headers={'Authorization': f'Bearer {sf.session_id}'})
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  status: {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict):
                    failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} :: {f.get("problem")}')
            return status
    return 'Timeout'


PHASE = sys.argv[1] if len(sys.argv) > 1 else 'all'
def run_phase(p): return PHASE == 'all' or PHASE == p


# ==============================================================
# PHASE A  Custom object + fields
# ==============================================================
if run_phase('A'):
    print("=== PHASE A: Create Opportunity_Account__c ===")

    object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Opportunity Account</label>
    <pluralLabel>Opportunity Accounts</pluralLabel>
    <nameField>
        <displayFormat>OA-{00000}</displayFormat>
        <label>Opportunity Account Name</label>
        <type>AutoNumber</type>
    </nameField>
    <deploymentStatus>Deployed</deploymentStatus>
    <sharingModel>ControlledByParent</sharingModel>
    <enableActivities>false</enableActivities>
    <enableHistory>true</enableHistory>
    <enableReports>true</enableReports>
    <enableSearch>true</enableSearch>
    <fields>
        <fullName>Opportunity__c</fullName>
        <label>Opportunity</label>
        <type>MasterDetail</type>
        <referenceTo>Opportunity</referenceTo>
        <relationshipName>Opportunity_Accounts</relationshipName>
        <relationshipLabel>Accounts</relationshipLabel>
        <writeRequiresMasterRead>false</writeRequiresMasterRead>
        <reparentableMasterDetail>false</reparentableMasterDetail>
    </fields>
    <fields>
        <fullName>Account__c</fullName>
        <label>Account</label>
        <type>Lookup</type>
        <referenceTo>Account</referenceTo>
        <relationshipName>Opportunity_Accounts</relationshipName>
        <relationshipLabel>Opportunity Accounts</relationshipLabel>
        <deleteConstraint>Restrict</deleteConstraint>
        <required>true</required>
    </fields>
    <fields>
        <fullName>Is_Primary__c</fullName>
        <label>Is Primary</label>
        <type>Checkbox</type>
        <defaultValue>false</defaultValue>
        <inlineHelpText>When checked, this Account becomes the Opportunity's primary Account. Only one primary per Opportunity.</inlineHelpText>
    </fields>
    <fields>
        <fullName>Role__c</fullName>
        <label>Role</label>
        <type>Picklist</type>
        <required>false</required>
        <inlineHelpText>Optional. Leave blank if unsure - the goal is that any tagged Account is discoverable in search regardless of role.</inlineHelpText>
        <valueSet>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>Owner</fullName><default>false</default><label>Owner</label></value>
                <value><fullName>Management Company</fullName><default>false</default><label>Management Company</label></value>
                <value><fullName>Portfolio</fullName><default>false</default><label>Portfolio</label></value>
                <value><fullName>Other</fullName><default>false</default><label>Other</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('objects/Opportunity_Account__c.object', object_xml)
        zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity_Account__c</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

    if deploy_zip(buf, "Phase A: junction object") != 'Succeeded':
        print("Phase A failed, stopping.")
        sys.exit(1)
    print("Phase A: OK\n")


# ==============================================================
# PHASE E  Clear Units__c help text
# ==============================================================
if run_phase('E'):
    print("=== PHASE E: Clear Units__c help text ===")

    # Metadata API requires re-sending the whole field definition
    units_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Units__c</fullName>
        <label>Living Units</label>
        <type>Number</type>
        <precision>18</precision>
        <scale>0</scale>
    </fields>
</CustomObject>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('objects/Opportunity.object', units_xml)
        zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

    if deploy_zip(buf, "Phase E: Units help text") != 'Succeeded':
        print("Phase E failed.")
        sys.exit(1)
    print("Phase E: OK\n")

# ==============================================================
# PHASE B  Flow: primary sync + single-primary enforcement
# ==============================================================
if run_phase('B'):
    print("=== PHASE B: Deploy sync flow ===")

    flow_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <description>When an Opportunity_Account__c is marked Is_Primary=true, (a) unset Is_Primary on sibling junctions for same Opp, (b) sync Opportunity.AccountId.</description>
    <interviewLabel>Sync Primary Opportunity Account {!$Flow.CurrentDateTime}</interviewLabel>
    <label>Sync Primary Opportunity Account</label>
    <processType>AutoLaunchedFlow</processType>
    <runInMode>SystemModeWithoutSharing</runInMode>
    <status>Active</status>
    <environments>Default</environments>

    <start>
        <locationX>50</locationX>
        <locationY>50</locationY>
        <object>Opportunity_Account__c</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Is_Primary__c</field>
            <operator>EqualTo</operator>
            <value><booleanValue>true</booleanValue></value>
        </filters>
        <connector><targetReference>UnsetSiblings</targetReference></connector>
    </start>

    <recordUpdates>
        <name>UnsetSiblings</name>
        <label>Unset Is_Primary on sibling junctions</label>
        <locationX>50</locationX><locationY>200</locationY>
        <object>Opportunity_Account__c</object>
        <filterLogic>1 AND 2 AND 3</filterLogic>
        <filters>
            <field>Opportunity__c</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </filters>
        <filters>
            <field>Id</field>
            <operator>NotEqualTo</operator>
            <value><elementReference>$Record.Id</elementReference></value>
        </filters>
        <filters>
            <field>Is_Primary__c</field>
            <operator>EqualTo</operator>
            <value><booleanValue>true</booleanValue></value>
        </filters>
        <inputAssignments>
            <field>Is_Primary__c</field>
            <value><booleanValue>false</booleanValue></value>
        </inputAssignments>
        <connector><targetReference>UpdateOpp</targetReference></connector>
    </recordUpdates>

    <recordUpdates>
        <name>UpdateOpp</name>
        <label>Sync AccountId on Opportunity if different</label>
        <locationX>50</locationX><locationY>300</locationY>
        <object>Opportunity</object>
        <filterLogic>1 AND 2</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </filters>
        <filters>
            <field>AccountId</field>
            <operator>NotEqualTo</operator>
            <value><elementReference>$Record.Account__c</elementReference></value>
        </filters>
        <inputAssignments>
            <field>AccountId</field>
            <value><elementReference>$Record.Account__c</elementReference></value>
        </inputAssignments>
    </recordUpdates>
</Flow>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('flows/Sync_Primary_Opportunity_Account.flow', flow_xml)
        zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Sync_Primary_Opportunity_Account</members><name>Flow</name></types>
    <version>59.0</version>
</Package>""")

    if deploy_zip(buf, "Phase B: flow") != 'Succeeded':
        print("Phase B failed, stopping.")
        sys.exit(1)
    print("Phase B: OK\n")


# ==============================================================
# PHASE D  Backfill junction from existing AccountId / Mgmt / Portfolio
# ==============================================================
if run_phase('D'):
    print("=== PHASE D: Backfill junction records ===")

    opps = sf.query_all(
        "SELECT Id, AccountId, Management_Company__c, Portfolio__c "
        "FROM Opportunity "
        "WHERE AccountId != null OR Management_Company__c != null OR Portfolio__c != null"
    )['records']
    print(f"  Found {len(opps)} opps with Account/Mgmt/Portfolio populated")

    created = 0
    skipped = 0
    errors = []

    for opp in opps:
        seen = set()
        plan = []
        # priority for primary: AccountId -> Management_Company -> Portfolio
        if opp.get('AccountId'):
            plan.append(('Owner', opp['AccountId']))
            seen.add(opp['AccountId'])
        if opp.get('Management_Company__c') and opp['Management_Company__c'] not in seen:
            plan.append(('Management Company', opp['Management_Company__c']))
            seen.add(opp['Management_Company__c'])
        if opp.get('Portfolio__c') and opp['Portfolio__c'] not in seen:
            plan.append(('Portfolio', opp['Portfolio__c']))
            seen.add(opp['Portfolio__c'])

        for i, (role, acct_id) in enumerate(plan):
            try:
                sf.Opportunity_Account__c.create({
                    'Opportunity__c': opp['Id'],
                    'Account__c': acct_id,
                    'Role__c': role,
                    'Is_Primary__c': i == 0,
                })
                created += 1
            except Exception as e:
                errors.append((opp['Id'], role, acct_id, str(e)[:200]))

    print(f"  Created: {created}")
    print(f"  Errors: {len(errors)}")
    for e in errors[:10]:
        print(f"    {e}")


# ==============================================================
# PHASE C  Add related list to MDU Opportunity Layout
# ==============================================================
if run_phase('C'):
    print("\n=== PHASE C: Add related list to MDU layout ===")
    # Retrieve existing layout, splice in the related list, redeploy
    retrieve_body = {'unpackaged': {
        'types': [{'members': ['Opportunity-MDU Opportunity Layout'], 'name': 'Layout'}],
        'version': '59.0'
    }}
    resp = requests.post(f'{sf.base_url}metadata/retrieveRequest',
        headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'},
        json=retrieve_body)
    rid = resp.json().get('id')
    layout_xml_raw = None
    for _ in range(20):
        time.sleep(2)
        r = requests.get(f'{sf.base_url}metadata/retrieveRequest/{rid}',
                         headers={'Authorization': f'Bearer {sf.session_id}'})
        d = r.json()
        if d.get('status') in ('Succeeded', 'Failed'):
            if d.get('zipFile'):
                zb = base64.b64decode(d['zipFile'])
                zf = zipfile.ZipFile(io.BytesIO(zb))
                for n in zf.namelist():
                    if n.endswith('.layout'):
                        layout_xml_raw = zf.read(n).decode('utf-8')
            break

    if not layout_xml_raw:
        print("  Could not retrieve layout, skipping")
    else:
        # Insert related list before the closing </Layout>
        rl_block = """    <relatedLists>
        <fields>NAME</fields>
        <fields>Account__c</fields>
        <fields>Role__c</fields>
        <fields>Is_Primary__c</fields>
        <relatedList>Opportunity_Account__c.Opportunity__c</relatedList>
    </relatedLists>
"""
        if 'Opportunity_Account__c.Opportunity__c' in layout_xml_raw:
            print("  Related list already present, skipping")
        else:
            layout_xml_new = layout_xml_raw.replace('</Layout>', rl_block + '</Layout>')
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('layouts/Opportunity-MDU Opportunity Layout.layout', layout_xml_new)
                zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Opportunity-MDU Opportunity Layout</members><name>Layout</name></types>
    <version>59.0</version>
</Package>""")
            if deploy_zip(buf, "Phase C: layout") != 'Succeeded':
                print("Phase C failed.")
                sys.exit(1)
            print("  Phase C: OK")


print("\nDone.")
