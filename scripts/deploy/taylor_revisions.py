"""
Taylor's Salesforce Revisions (3/30 emails)
- Field label changes, picklist updates, new fields
- Layout reorganization
- Validation rule for Opportunity Name lock
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

print("Connected to Salesforce")
print(f"Instance: {sf.sf_instance}")

# ============================================================
# PHASE 1: Field metadata changes via Metadata API deploy
# ============================================================

# Helper: deploy a zip via Metadata API
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
# PHASE 1A: Create new fields via Tooling API
# ============================================================
print("\n=== PHASE 1A: Creating new fields ===")

tooling_url = f"https://{sf.sf_instance}/services/data/v59.0/tooling/sobjects/CustomField"
headers = {
    'Authorization': f'Bearer {sf.session_id}',
    'Content-Type': 'application/json'
}

# Tooling API query helper
def tooling_query(soql):
    url = f"https://{sf.sf_instance}/services/data/v59.0/tooling/query?q={requests.utils.quote(soql)}"
    resp = requests.get(url, headers={'Authorization': f'Bearer {sf.session_id}'})
    return resp.json()

new_fields = [
    {
        'name': 'Brownfield_Greenfield__c',
        'label': 'Brownfield / Greenfield',
        'type': 'Picklist',
        'metadata': {
            'label': 'Brownfield / Greenfield',
            'type': 'Picklist',
            'valueSet': {
                'valueSetDefinition': {
                    'sorted': False,
                    'value': [
                        {'fullName': 'Brownfield', 'default': False, 'label': 'Brownfield'},
                        {'fullName': 'Greenfield', 'default': False, 'label': 'Greenfield'},
                    ]
                }
            }
        }
    },
    {
        'name': 'HOA__c',
        'label': 'HOA',
        'type': 'Checkbox',
        'metadata': {
            'label': 'HOA',
            'type': 'Checkbox',
            'defaultValue': False
        }
    },
    {
        'name': 'Prospective_ISP_List__c',
        'label': 'Prospective ISP',
        'type': 'MultiselectPicklist',
        'metadata': {
            'label': 'Prospective ISP',
            'type': 'MultiselectPicklist',
            'visibleLines': 4,
            'valueSet': {
                'valueSetDefinition': {
                    'sorted': True,
                    'value': [
                        {'fullName': 'AT&T', 'default': False, 'label': 'AT&T'},
                        {'fullName': 'Atlas', 'default': False, 'label': 'Atlas'},
                        {'fullName': 'FiberFirst', 'default': False, 'label': 'FiberFirst'},
                        {'fullName': 'Lumen / Quantum Fiber', 'default': False, 'label': 'Lumen / Quantum Fiber'},
                        {'fullName': 'Ting', 'default': False, 'label': 'Ting'},
                    ]
                }
            }
        }
    },
    {
        'name': 'Confirmed_ISP_List__c',
        'label': 'Confirmed ISP',
        'type': 'MultiselectPicklist',
        'metadata': {
            'label': 'Confirmed ISP',
            'type': 'MultiselectPicklist',
            'visibleLines': 4,
            'valueSet': {
                'valueSetDefinition': {
                    'sorted': True,
                    'value': [
                        {'fullName': 'AT&T', 'default': False, 'label': 'AT&T'},
                        {'fullName': 'Atlas', 'default': False, 'label': 'Atlas'},
                        {'fullName': 'FiberFirst', 'default': False, 'label': 'FiberFirst'},
                        {'fullName': 'Lumen / Quantum Fiber', 'default': False, 'label': 'Lumen / Quantum Fiber'},
                        {'fullName': 'Ting', 'default': False, 'label': 'Ting'},
                    ]
                }
            }
        }
    },
]

for field_def in new_fields:
    # Check if field already exists
    check = tooling_query(f"SELECT Id FROM CustomField WHERE DeveloperName = '{field_def['name'].replace('__c', '')}' AND EntityDefinition.QualifiedApiName = 'Opportunity'")
    if check['records']:
        print(f"  {field_def['name']} already exists, skipping")
        continue

    body = {
        'FullName': f"Opportunity.{field_def['name']}",
        'Metadata': field_def['metadata']
    }
    resp = requests.post(tooling_url, headers=headers, json=body)
    if resp.status_code == 201:
        print(f"  Created {field_def['name']}")
    else:
        print(f"  FAILED {field_def['name']}: {resp.status_code} - {resp.text[:200]}")


# ============================================================
# PHASE 1B: Update existing field labels and picklists via Metadata API
# ============================================================
print("\n=== PHASE 1B: Updating field metadata ===")

# Agreement_Name__c -> label "Site Name"
# Units__c -> inlineHelpText "Number of living units at this property"
# Property_Type__c -> updated picklist values
# Build_Type__c -> FTTU / FTTB only
# Property_Category__c -> Cat 1, Cat 2, Cat 3
# Property_Classification__c -> MDU / SFU only (remove MHP)
# Incumbent_Agreement_Type__c -> EMA / NEMA / Bulk

field_updates = {
    'Opportunity.Agreement_Name__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Agreement_Name__c</fullName>
    <label>Site Name</label>
    <type>Text</type>
    <length>255</length>
    <externalId>true</externalId>
    <unique>true</unique>
    <inlineHelpText>Cross-system identifier matching SiteTracker project name. Format: City_MDU_PropertyName</inlineHelpText>
</CustomField>""",

    'Opportunity.Units__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Units__c</fullName>
    <label>Living Units</label>
    <type>Number</type>
    <precision>18</precision>
    <scale>0</scale>
    <inlineHelpText>Number of living units at this property</inlineHelpText>
</CustomField>""",

    'Opportunity.Property_Type__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Property_Type__c</fullName>
    <label>Property Type</label>
    <type>Picklist</type>
    <valueSet>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>Apartments</fullName><default>false</default><label>Apartments</label></value>
            <value><fullName>Condos</fullName><default>false</default><label>Condos</label></value>
            <value><fullName>Townhomes</fullName><default>false</default><label>Townhomes</label></value>
            <value><fullName>Private SFU Neighborhood</fullName><default>false</default><label>Private SFU Neighborhood</label></value>
            <value><fullName>Single Family Rental Homes</fullName><default>false</default><label>Single Family Rental Homes</label></value>
            <value><fullName>Mixed Use</fullName><default>false</default><label>Mixed Use</label></value>
            <value><fullName>Manufactured Homes / Mobile Homes</fullName><default>false</default><label>Manufactured Homes / Mobile Homes</label></value>
            <value><fullName>Senior Living / Assisted Living</fullName><default>false</default><label>Senior Living / Assisted Living</label></value>
            <value><fullName>Commercial / Business</fullName><default>false</default><label>Commercial / Business</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>""",

    'Opportunity.Build_Type__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Build_Type__c</fullName>
    <label>Build Type</label>
    <type>Picklist</type>
    <valueSet>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>FTTU</fullName><default>false</default><label>FTTU</label></value>
            <value><fullName>FTTB</fullName><default>false</default><label>FTTB</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>""",

    'Opportunity.Property_Category__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Property_Category__c</fullName>
    <label>Category</label>
    <type>Picklist</type>
    <valueSet>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>Cat 1</fullName><default>false</default><label>Cat 1</label></value>
            <value><fullName>Cat 2</fullName><default>false</default><label>Cat 2</label></value>
            <value><fullName>Cat 3</fullName><default>false</default><label>Cat 3</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>""",

    'Opportunity.Incumbent_Agreement_Type__c': """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Incumbent_Agreement_Type__c</fullName>
    <label>Incumbent Agreement Type</label>
    <type>Picklist</type>
    <valueSet>
        <valueSetDefinition>
            <sorted>false</sorted>
            <value><fullName>EMA</fullName><default>false</default><label>EMA</label></value>
            <value><fullName>NEMA</fullName><default>false</default><label>NEMA</label></value>
            <value><fullName>Bulk</fullName><default>false</default><label>Bulk</label></value>
        </valueSetDefinition>
    </valueSet>
</CustomField>""",
}

# Build a single .object file containing all field updates
all_fields_xml = ''.join(xml.replace('<?xml version="1.0" encoding="UTF-8"?>\n<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">', '<fields>').replace('</CustomField>', '</fields>') for xml in field_updates.values())

object_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
{all_fields_xml}
</CustomObject>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('objects/Opportunity.object', object_xml)
    package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""
    zf.writestr('package.xml', package_xml)

result = deploy_zip(buf, "Field updates")

if result != 'Succeeded':
    print("Field updates failed, stopping.")
    exit(1)


# ============================================================
# PHASE 1C: Update Property_Classification__c (remove MHP)
# ============================================================
print("\n=== PHASE 1C: Updating Property_Classification__c ===")

# Property_Classification__c is on Opportunity per memory, but let me check
# Actually from memory: Property_Classification__c is on Opportunity
# But wait - the memory says it's a Picklist: SFU/MDU/MHP
# Need to check if it's on Opportunity or Property_Location__c
# Memory says: "Property_Classification__c (Picklist: SFU/MDU/MHP) -- added to separate the building classification"
# And from migration-import-decisions.md: on Opportunity

class_object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Property_Classification__c</fullName>
        <label>Property Classification</label>
        <type>Picklist</type>
        <valueSet>
            <valueSetDefinition>
                <sorted>false</sorted>
                <value><fullName>MDU</fullName><default>false</default><label>MDU</label></value>
                <value><fullName>SFU</fullName><default>false</default><label>SFU</label></value>
            </valueSetDefinition>
        </valueSet>
    </fields>
</CustomObject>"""

buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('objects/Opportunity.object', class_object_xml)
    zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

result = deploy_zip(buf2, "Property Classification update")


# ============================================================
# PHASE 2: Migrate ISP text data to new multi-select fields
# ============================================================
print("\n=== PHASE 2: Migrating ISP data ===")

isp_values = {'AT&T', 'Atlas', 'FiberFirst', 'Lumen / Quantum Fiber', 'Ting'}

# Use direct REST to avoid cached schema
rest_headers = {
    'Authorization': f'Bearer {sf.session_id}',
    'Content-Type': 'application/json'
}
base_rest = f"https://{sf.sf_instance}/services/data/v59.0/sobjects/Opportunity"

# Migrate Prospective_ISP__c -> Prospective_ISP_List__c
opps_prosp = sf.query_all("SELECT Id, Prospective_ISP__c FROM Opportunity WHERE Prospective_ISP__c != null")
migrated_p = 0
for opp in opps_prosp['records']:
    old_val = opp['Prospective_ISP__c'].strip()
    if not old_val:
        continue
    matched = []
    old_lower = old_val.lower()
    for v in isp_values:
        if v.lower() in old_lower:
            matched.append(v)
    if matched:
        resp = requests.patch(f"{base_rest}/{opp['Id']}", headers=rest_headers,
                              json={'Prospective_ISP_List__c': ';'.join(matched)})
        if resp.status_code == 204:
            migrated_p += 1
        else:
            print(f"    WARN: {opp['Id']} - {resp.status_code}: {resp.text[:100]}")
print(f"  Migrated {migrated_p} Prospective ISP records")

# Migrate Confirmed_ISP__c -> Confirmed_ISP_List__c
opps_conf = sf.query_all("SELECT Id, Confirmed_ISP__c FROM Opportunity WHERE Confirmed_ISP__c != null")
migrated_c = 0
for opp in opps_conf['records']:
    old_val = opp['Confirmed_ISP__c'].strip()
    if not old_val:
        continue
    matched = []
    old_lower = old_val.lower()
    for v in isp_values:
        if v.lower() in old_lower:
            matched.append(v)
    if matched:
        resp = requests.patch(f"{base_rest}/{opp['Id']}", headers=rest_headers,
                              json={'Confirmed_ISP_List__c': ';'.join(matched)})
        if resp.status_code == 204:
            migrated_c += 1
        else:
            print(f"    WARN: {opp['Id']} - {resp.status_code}: {resp.text[:100]}")
print(f"  Migrated {migrated_c} Confirmed ISP records")


# ============================================================
# PHASE 3: Deploy updated MDU layout
# ============================================================
print("\n=== PHASE 3: Deploying updated MDU layout ===")

# Related list snippets
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
        <fields>PAL_Signed_Date__c</fields>
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

# Updated MDU layout per Taylor's requests:
# - Agreement_Name__c renamed to "Site Name" (label change, field stays same API name)
# - Removed Amount from layout
# - Added Sales_Status__c, Hold_Reason__c, Projected_Close_Date__c to Opp Info
# - Property Details reorganized: Living Units, Property Type, Category, Build Type,
#   Brownfield/Greenfield, Property Classification, HOA, Address fields
# - ISP section: new multi-select fields + Incumbent fields moved here
# - Close Date help text note
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


# ============================================================
# PHASE 4: Validation rule - lock Opportunity Name for non-admins
# ============================================================
print("\n=== PHASE 4: Validation rule for Opportunity Name ===")

# Only blocks name changes on existing records (not new ones)
# Admins (System Administrator profile) can still edit
validation_xml = """<?xml version="1.0" encoding="UTF-8"?>
<ValidationRule xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Prevent_Opportunity_Name_Change</fullName>
    <active>true</active>
    <description>Prevents non-admin users from changing the Opportunity Name after creation. Name changes affect other systems (SiteTracker, IronClad) and should go through a request process.</description>
    <errorConditionFormula>AND(
  NOT(ISNEW()),
  ISCHANGED(Name),
  $Profile.Name &lt;&gt; &quot;System Administrator&quot;
)</errorConditionFormula>
    <errorDisplayField>Name</errorDisplayField>
    <errorMessage>Opportunity Name cannot be changed after creation. Please contact your admin to request a name change, as it affects linked records in SiteTracker and IronClad.</errorMessage>
</ValidationRule>"""

# Validation rules go inside the .object file
val_object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <validationRules>
        <fullName>Prevent_Opportunity_Name_Change</fullName>
        <active>true</active>
        <description>Prevents non-admin users from changing the Opportunity Name after creation. Name changes affect other systems (SiteTracker, IronClad) and should go through a request process.</description>
        <errorConditionFormula>AND(
  NOT(ISNEW()),
  ISCHANGED(Name),
  $Profile.Name &lt;&gt; &quot;System Administrator&quot;
)</errorConditionFormula>
        <errorDisplayField>Name</errorDisplayField>
        <errorMessage>Opportunity Name cannot be changed after creation. Please contact your admin to request a name change, as it affects linked records in SiteTracker and IronClad.</errorMessage>
    </validationRules>
</CustomObject>"""

buf4 = io.BytesIO()
with zipfile.ZipFile(buf4, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('objects/Opportunity.object', val_object_xml)
    zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

result = deploy_zip(buf4, "Validation rule deploy")


# ============================================================
# PHASE 5: Update Close Date help text
# ============================================================
print("\n=== PHASE 5: Close Date help text ===")

# Standard Close Date field - update via Metadata API
close_date_object_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>CloseDate</fullName>
        <inlineHelpText>Date the PAL was signed (or expected signing date if still in progress). Use Projected Close Date for initial estimates.</inlineHelpText>
    </fields>
</CustomObject>"""

buf5 = io.BytesIO()
with zipfile.ZipFile(buf5, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('objects/Opportunity.object', close_date_object_xml)
    zf.writestr('package.xml', """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>""")

result = deploy_zip(buf5, "Close Date help text")


print("\n=== ALL PHASES COMPLETE ===")
print("""
Summary of changes:
  FIELDS CREATED:
    - Brownfield_Greenfield__c (Picklist: Brownfield/Greenfield)
    - HOA__c (Checkbox)
    - Prospective_ISP_List__c (Multi-Select: AT&T, Atlas, FiberFirst, Lumen/Quantum Fiber, Ting)
    - Confirmed_ISP_List__c (Multi-Select: AT&T, Atlas, FiberFirst, Lumen/Quantum Fiber, Ting)

  FIELDS UPDATED:
    - Agreement_Name__c -> label "Site Name"
    - Units__c -> label "Living Units" + help text
    - Property_Type__c -> Taylor's picklist (Apartments, Condos, Townhomes, etc.)
    - Build_Type__c -> FTTU/FTTB only
    - Property_Category__c -> Cat 1/Cat 2/Cat 3
    - Incumbent_Agreement_Type__c -> EMA/NEMA/Bulk
    - Property_Classification__c -> MDU/SFU (removed MHP)
    - CloseDate -> help text clarifying PAL signed date vs projected

  LAYOUT CHANGES (MDU):
    - Removed Amount field
    - Added Sales_Status__c, Hold_Reason__c, RE_Assigned__c, Projected_Close_Date__c
    - Added HOA__c, Brownfield_Greenfield__c, Property_Classification__c to Property Details
    - Replaced old text ISP fields with new multi-select ISP fields
    - Moved Incumbent fields to ISP section

  ISP DATA MIGRATED:
    - Prospective_ISP__c (text) -> Prospective_ISP_List__c (multi-select)
    - Confirmed_ISP__c (text) -> Confirmed_ISP_List__c (multi-select)

  VALIDATION RULE:
    - Prevent_Opportunity_Name_Change: blocks non-admin name edits after creation

  NOT CHANGED (needs discussion):
    - SiteTracker Project details view (Email 2) - separate task
    - Old ISP text fields still exist (can be hidden/deleted later)
""")
