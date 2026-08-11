"""
Deploy record-type-specific Opportunity FlexiPages:
  - MDU_Opportunity_Record_Page — for MDU and SFU record types
  - Business_Opportunity_Record_Page — for Business record type

Both share the same structure/feel. Differences:
  MDU: No Property_Unit__c, No Market_Sales_Lead__c
  Business: All fields

This script is the CANONICAL SOURCE OF TRUTH for both Opp record pages.
Do NOT edit pages through Lightning App Builder — changes will be overwritten.

After deploying pages, assigns them per record type via Metadata API.
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# ============================================================================
# SHARED BUILDING BLOCKS
# ============================================================================

def field_item_xml(api_name, behavior="none"):
    safe_id = api_name.replace('__c','_c').replace('__r','_r')
    return f"""        <itemInstances>
            <fieldInstance>
                <fieldInstanceProperties>
                    <name>uiBehavior</name>
                    <value>{behavior}</value>
                </fieldInstanceProperties>
                <fieldItem>Record.{api_name}</fieldItem>
                <identifier>Record{safe_id}Field</identifier>
            </fieldInstance>
        </itemInstances>"""

def column_facet_xml(name, fields, behaviors=None):
    if behaviors is None:
        behaviors = ["none"] * len(fields)
    items = "\n".join([field_item_xml(f, b) for f, b in zip(fields, behaviors)])
    return f"""    <flexiPageRegions>
{items}
        <name>{name}</name>
        <type>Facet</type>
    </flexiPageRegions>"""

def section_columns_facet_xml(name, col_facet_names):
    cols = ""
    for i, cf in enumerate(col_facet_names):
        cols += f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>body</name>
                    <value>{cf}</value>
                </componentInstanceProperties>
                <componentName>flexipage:column</componentName>
                <identifier>col_{name}_{i}</identifier>
            </componentInstance>
        </itemInstances>
"""
    return f"""    <flexiPageRegions>
{cols}        <name>{name}</name>
        <type>Facet</type>
    </flexiPageRegions>"""

def related_list_xml(api_name, identifier, show_action_bar="true"):
    return f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Opportunity.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>{api_name}</value>
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
                    <value>{show_action_bar}</value>
                </componentInstanceProperties>
                <componentName>force:relatedListSingleContainer</componentName>
                <identifier>{identifier}</identifier>
            </componentInstance>
        </itemInstances>"""

def build_flexipage_xml(sections, master_label, sidebar_lists=None):
    """Build a complete FlexiPage XML from section definitions."""
    all_facets = []
    section_items_xml = []

    for label, sid, lfields, lbehaviors, rfields, rbehaviors in sections:
        lf = f"Facet_{sid}_l"
        rf = f"Facet_{sid}_r"
        cf = f"Facet_{sid}_c"

        all_facets.append(column_facet_xml(lf, lfields, lbehaviors))
        if rfields:
            all_facets.append(column_facet_xml(rf, rfields, rbehaviors))
            all_facets.append(section_columns_facet_xml(cf, [lf, rf]))
        else:
            all_facets.append(section_columns_facet_xml(cf, [lf]))

        section_items_xml.append(f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>columns</name>
                    <value>{cf}</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>horizontalAlignment</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>label</name>
                    <value>{label}</value>
                </componentInstanceProperties>
                <componentName>flexipage:fieldSection</componentName>
                <identifier>fs_{sid}</identifier>
            </componentInstance>
        </itemInstances>""")

    detail_items = "\n".join(section_items_xml)
    facets_block = "\n".join(all_facets)

    # Related lists in left sidebar — configurable per page
    if sidebar_lists is None:
        sidebar_lists = [
            ("Opportunity_Contacts__r", "force_relatedListSingleContainer_oppContacts", "true"),
            ("Agreements__r", "force_relatedListSingleContainer", "true"),
            ("SiteTracker_Projects__r", "force_relatedListSingleContainer_stProjects", "false"),
            ("AttachedContentNotes", "force_relatedListSingleContainer2", "true"),
        ]
    left_sidebar_lists = "\n".join([
        related_list_xml(api, ident, action) for api, ident, action in sidebar_lists
    ])

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FlexiPage xmlns="http://soap.sforce.com/2006/04/metadata">
    <flexiPageRegions>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>collapsed</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>enableActionsConfiguration</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>enableActionsInNative</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>hideChatterActions</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>numVisibleActions</name>
                    <value>5</value>
                </componentInstanceProperties>
                <componentName>force:highlightsPanel</componentName>
                <identifier>force_highlightsPanel</identifier>
            </componentInstance>
        </itemInstances>
{left_sidebar_lists}
        <name>leftsidebar</name>
        <type>Region</type>
    </flexiPageRegions>
    <flexiPageRegions>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>hideUpdateButton</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>variant</name>
                    <value>linear</value>
                </componentInstanceProperties>
                <componentName>runtime_sales_pathassistant:pathAssistant</componentName>
                <identifier>runtime_sales_pathassistant_pathAssistant</identifier>
            </componentInstance>
        </itemInstances>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>tabs</name>
                    <value>Facet-tabsetTabs</value>
                </componentInstanceProperties>
                <componentName>flexipage:tabset</componentName>
                <identifier>flexipage_tabset</identifier>
            </componentInstance>
        </itemInstances>
        <name>main</name>
        <type>Region</type>
    </flexiPageRegions>
    <flexiPageRegions>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>body</name>
                    <value>Facet-detailTab</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>title</name>
                    <value>Standard.Tab.detail</value>
                </componentInstanceProperties>
                <componentName>flexipage:tab</componentName>
                <identifier>flexipage_tab2</identifier>
            </componentInstance>
        </itemInstances>
        <name>Facet-tabsetTabs</name>
        <type>Facet</type>
    </flexiPageRegions>
    <flexiPageRegions>
{detail_items}
        <name>Facet-detailTab</name>
        <type>Facet</type>
    </flexiPageRegions>
{facets_block}
    <flexiPageRegions>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>hideHeader</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentName>force:relatedListQuickLinksContainer</componentName>
                <identifier>force_relatedListQuickLinksContainer</identifier>
            </componentInstance>
        </itemInstances>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>showLegacyActivityComposer</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentName>runtime_sales_activities:activityPanel</componentName>
                <identifier>runtime_sales_activities_activityPanel</identifier>
            </componentInstance>
        </itemInstances>
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Opportunity.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>AttachedContentDocuments</value>
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
                <identifier>force_relatedListSingleContainer4</identifier>
            </componentInstance>
        </itemInstances>
        <name>rightsidebar</name>
        <type>Region</type>
    </flexiPageRegions>
    <masterLabel>{master_label}</masterLabel>
    <sobjectType>Opportunity</sobjectType>
    <template>
        <name>flexipage:recordHomeThreeColTemplateDesktop</name>
    </template>
    <type>RecordPage</type>
</FlexiPage>"""

# ============================================================================
# SECTION DEFINITIONS — Edit here to change fields on either page
# ============================================================================

# BUSINESS — all fields
business_sections = [
    ("Opportunity Information", "s1",
     ["RecordTypeId", "Name", "AccountId", "Portfolio__c", "Management_Company__c", "Contact__c", "Agreement_Name__c"],
     ["readonly", "required", "none", "none", "none", "none", "none"],
     ["OwnerId", "Market_Sales_Lead__c", "RE_Assigned__c", "CloseDate", "StageName", "Probability", "Amount"],
     ["readonly", "none", "none", "required", "required", "none", "none"]),
    ("Property Details", "s2",
     ["Property_Unit__c", "Units__c", "Property_Type__c", "Property_Category__c", "Build_Type__c"],
     ["none"] * 5,
     ["Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"],
     ["none"] * 4),
    ("ISP Information", "s3",
     ["Prospective_ISP__c"], ["none"],
     ["Confirmed_ISP__c"], ["none"]),
    ("Additional Information", "s4",
     ["NextStep", "Description"], ["none", "none"],
     ["LeadSource"], ["none"]),
    ("Integration Links", "s5",
     ["SiteTracker_Project_ID__c", "SiteTracker_URL__c"], ["none", "none"],
     ["IronClad_URL__c"], ["none"]),
    ("Migration Reference", "s6",
     ["Monday_Item_ID__c"], ["none"],
     [], []),
    ("System Information", "s7",
     ["CreatedById"], ["readonly"],
     ["LastModifiedById"], ["readonly"]),
]

# MDU — same structure, minus Property_Unit__c and Market_Sales_Lead__c
mdu_sections = [
    ("Opportunity Information", "s1",
     ["RecordTypeId", "Name", "AccountId", "Portfolio__c", "Management_Company__c", "Contact__c", "Agreement_Name__c"],
     ["readonly", "required", "none", "none", "none", "none", "none"],
     ["OwnerId", "RE_Assigned__c", "CloseDate", "StageName", "Probability", "Amount"],
     ["readonly", "none", "required", "required", "none", "none"]),
    ("Property Details", "s2",
     ["Units__c", "Property_Type__c", "Property_Category__c", "Build_Type__c"],
     ["none"] * 4,
     ["Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"],
     ["none"] * 4),
    ("ISP Information", "s3",
     ["Prospective_ISP__c"], ["none"],
     ["Confirmed_ISP__c"], ["none"]),
    ("Additional Information", "s4",
     ["NextStep", "Description"], ["none", "none"],
     ["LeadSource"], ["none"]),
    ("Integration Links", "s5",
     ["SiteTracker_Project_ID__c", "SiteTracker_URL__c"], ["none", "none"],
     ["IronClad_URL__c"], ["none"]),
    ("Migration Reference", "s6",
     ["Monday_Item_ID__c"], ["none"],
     [], []),
    ("System Information", "s7",
     ["CreatedById"], ["readonly"],
     ["LastModifiedById"], ["readonly"]),
]

# ============================================================================
# BUILD AND DEPLOY
# ============================================================================

# ============================================================================
# SIDEBAR RELATED LISTS — Edit here to change sidebar per page
# Format: (relatedListApiName, identifier, showActionBar)
# ============================================================================

# Business sidebar: Contacts, Agreements, Property Units, Notes (no SiteTracker)
business_sidebar = [
    ("Opportunity_Contacts__r", "force_relatedListSingleContainer_oppContacts", "true"),
    ("Agreements__r", "force_relatedListSingleContainer", "true"),
    ("Property_Units__r", "force_relatedListSingleContainer_propUnits", "true"),
    ("AttachedContentNotes", "force_relatedListSingleContainer2", "true"),
]

# MDU sidebar: Contacts, Agreements, SiteTracker, Notes
mdu_sidebar = [
    ("Opportunity_Contacts__r", "force_relatedListSingleContainer_oppContacts", "true"),
    ("Agreements__r", "force_relatedListSingleContainer", "true"),
    ("SiteTracker_Projects__r", "force_relatedListSingleContainer_stProjects", "false"),
    ("AttachedContentNotes", "force_relatedListSingleContainer2", "true"),
]

business_xml = build_flexipage_xml(business_sections, "Business Opportunity Record Page", business_sidebar)
mdu_xml = build_flexipage_xml(mdu_sections, "MDU Opportunity Record Page", mdu_sidebar)

# The old shared page (Opportunity_Record_Page_Three_Column) has an org-wide default
# assignment that can't be removed via API. So we overwrite it with Business content.
# This effectively makes it the Business page under the old name.
old_page_xml = build_flexipage_xml(business_sections, "Opportunity Record Page - Three Column", business_sidebar)

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Business_Opportunity_Record_Page</members>
        <members>MDU_Opportunity_Record_Page</members>
        <members>Opportunity_Record_Page_Three_Column</members>
        <name>FlexiPage</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('flexipages/Business_Opportunity_Record_Page.flexipage', business_xml)
    zf.writestr('flexipages/MDU_Opportunity_Record_Page.flexipage', mdu_xml)
    zf.writestr('flexipages/Opportunity_Record_Page_Three_Column.flexipage', old_page_xml)
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

print("Step 1: Deploying Business + MDU FlexiPages...")
resp = requests.post(
    deploy_url,
    headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    data=body_str
)
print(f'Deploy: {resp.status_code}')

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
        print(f'  Poll {i+1}: {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict):
                    failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            elif status == 'Succeeded':
                print('\nFlexiPages deployed successfully!')
            break
else:
    print(resp.text[:500])

# ============================================================================
# STEP 2: Assign pages per record type
# ============================================================================
print("\nStep 2: Assigning pages per record type...")

# Record type IDs
# Business: 012WR00000Ra0mjYAB
# MDU: 012WR00000Ra0mkYAB
# SFU: 012WR00000S2ne1YAB

# Get the new FlexiPage IDs
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
tooling_url = f'{sf.base_url}tooling/query/'

resp = requests.get(tooling_url, headers=headers, params={
    'q': "SELECT Id, DeveloperName FROM FlexiPage WHERE DeveloperName IN ('Business_Opportunity_Record_Page', 'MDU_Opportunity_Record_Page')"
})
pages = {r['DeveloperName']: r['Id'] for r in resp.json()['records']}
print(f'  Business page ID: {pages.get("Business_Opportunity_Record_Page")}')
print(f'  MDU page ID: {pages.get("MDU_Opportunity_Record_Page")}')

# Assign via Tooling API — FlexiPageRegionAssignment doesn't exist as queryable
# We need to use the Metadata API to deploy a CustomObject with flexipageAssignment
# Actually, in Lightning, page assignments need to be done via the
# flexipageAssignment metadata on FlexiPage. The trick is to set the
# 'pageOrSobjectType' and activate per record type.

# The standard way: deploy FlexiPage with activation settings using Metadata API
# We can use the REST Composite endpoint to set page assignments

# Actually the cleanest way is to use the /connect/communities or
# the FlexiPage activation endpoint. But since that's not well-documented,
# let's use the Tooling API to update the FlexiPage assignment records.

# In practice, FlexiPage assignments are stored internally and the most reliable
# programmatic approach is to use the Metadata API with a full package that
# includes the assignment. Let me use the Salesforce CLI approach via REST.

# Use the compact approach: PATCH the existing org default to use the new pages
# by creating AppFlexiPageAssignment records

# Actually, the most reliable way is via the Metadata API CustomObject deploy
# with recordTypeFlexiPageAssignments. But that's complex.

# Let's try the simplest approach: use the Lightning Page Assignment API
assign_url = f'{sf.base_url}connect/lightning-page-assignments'

# Assign Business page to Business record type (org default for that RT)
for rt_id, page_dev_name, rt_name in [
    ('012WR00000Ra0mjYAB', 'Business_Opportunity_Record_Page', 'Business'),
    ('012WR00000Ra0mkYAB', 'MDU_Opportunity_Record_Page', 'MDU'),
    ('012WR00000S2ne1YAB', 'MDU_Opportunity_Record_Page', 'SFU'),
]:
    page_id = pages.get(page_dev_name)
    if page_id:
        payload = {
            "flexiPageId": page_id,
            "type": "RecordType",
            "recordTypeId": rt_id
        }
        resp = requests.post(assign_url, headers=headers, json=payload)
        print(f'  Assign {page_dev_name} to {rt_name}: {resp.status_code}')
        if resp.status_code not in (200, 201, 204):
            print(f'    Response: {resp.text[:300]}')
