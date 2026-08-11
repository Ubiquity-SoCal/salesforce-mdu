"""
Update MDU Opportunity Record Page (FlexiPage) with Taylor's field changes.
The FlexiPage has hardcoded field sections that override the page layout,
so we need to update the FlexiPage directly.
"""
from simple_salesforce import Salesforce
import requests, json, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)


def build_field(field_item, behavior="none", visibility_field=None, visibility_op=None, visibility_value=None):
    """Build a fieldInstance XML block with optional visibility rule."""
    uid = field_item.replace("Record.", "").replace(".", "").replace("__c", "").replace("__r", "")
    props = ""
    if behavior == "readonly":
        props = """
                    <fieldInstanceProperties>
                        <name>uiBehavior</name>
                        <value>readonly</value>
                    </fieldInstanceProperties>"""
    elif behavior == "required":
        props = """
                    <fieldInstanceProperties>
                        <name>uiBehavior</name>
                        <value>required</value>
                    </fieldInstanceProperties>"""

    vis = ""
    if visibility_field:
        vis = f"""
                    <visibilityRule>
                        <booleanFilter/>
                        <criteria>
                            <leftValue>{{!Record.{visibility_field}}}</leftValue>
                            <operator>{visibility_op}</operator>
                            <rightValue>{visibility_value}</rightValue>
                        </criteria>
                    </visibilityRule>"""

    return f"""
                <itemInstances>
                    <fieldInstance>{props}
                        <fieldItem>{field_item}</fieldItem>
                        <identifier>{uid}Field</identifier>{vis}
                    </fieldInstance>
                </itemInstances>"""


def build_column_region(name, fields_with_behavior):
    """Build a region containing field instances."""
    items = ""
    for field_tuple in fields_with_behavior:
        items += build_field(*field_tuple)
    if items:
        return f"""
        <flexiPageRegions>{items}
            <name>{name}</name>
            <type>Facet</type>
        </flexiPageRegions>"""
    else:
        return f"""
        <flexiPageRegions>
            <name>{name}</name>
            <type>Facet</type>
        </flexiPageRegions>"""


def build_columns_region(name, left_facet, right_facet):
    """Build a two-column container region."""
    return f"""
        <flexiPageRegions>
            <itemInstances>
                <componentInstance>
                    <componentInstanceProperties>
                        <name>body</name>
                        <value>{left_facet}</value>
                    </componentInstanceProperties>
                    <componentName>flexipage:column</componentName>
                    <identifier>{left_facet}_col</identifier>
                </componentInstance>
            </itemInstances>
            <itemInstances>
                <componentInstance>
                    <componentInstanceProperties>
                        <name>body</name>
                        <value>{right_facet}</value>
                    </componentInstanceProperties>
                    <componentName>flexipage:column</componentName>
                    <identifier>{right_facet}_col</identifier>
                </componentInstance>
            </itemInstances>
            <name>{name}</name>
            <type>Facet</type>
        </flexiPageRegions>"""


def build_section(identifier, label, columns_facet):
    """Build a fieldSection component instance."""
    return f"""
                <itemInstances>
                    <componentInstance>
                        <componentInstanceProperties>
                            <name>columns</name>
                            <value>{columns_facet}</value>
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
                        <identifier>{identifier}</identifier>
                    </componentInstance>
                </itemInstances>"""


# ── Define all sections with correct fields ──

# Section 1: Opportunity Information
s1_left = [
    ("Record.RecordTypeId", "readonly", None, None, None),
    ("Record.Name", "none", None, None, None),
    ("Record.AccountId", "none", None, None, None),
    ("Record.StageName", "none", None, None, None),
    ("Record.Agreement_Name__c", "none", None, None, None),
    ("Record.Sales_Status__c", "none", "StageName", "EQUAL", "Prospecting"),
    ("Record.Contact__c", "none", None, None, None),
    ("Record.Loss_Reason__c", "none", "StageName", "EQUAL", "Closed Lost"),
    ("Record.Notes_Count__c", "readonly", None, None, None),
]
s1_right = [
    ("Record.OwnerId", "none", None, None, None),
    ("Record.RE_Assigned__c", "none", None, None, None),
    ("Record.Hold_Reason__c", "none", "StageName", "EQUAL", "On Hold"),
    ("Record.Probability", "none", None, None, None),
    ("Record.Projected_Close_Date__c", "none", None, None, None),
    ("Record.CloseDate", "none", None, None, None),
]

# Section 2: Property Details
s2_left = [
    ("Record.Units__c", "required", None, None, None),
    ("Record.Property_Type__c", "required", None, None, None),
    ("Record.Property_Classification__c", "none", None, None, None),
    ("Record.Property_Category__c", "required", None, None, None),
    ("Record.Property_Address__c", "required", None, None, None),
]
s2_right = [
    ("Record.Build_Type__c", "none", None, None, None),
    ("Record.New_Construction__c", "none", None, None, None),
    ("Record.HOA__c", "none", None, None, None),
    ("Record.Property_City__c", "none", None, None, None),
    ("Record.Property_State__c", "none", None, None, None),
    ("Record.Property_Zip__c", "none", None, None, None),
]

# Section 3: ISP Information (new multipicklist fields + incumbent)
s3_left = [
    ("Record.Prospective_ISPs__c", "none", None, None, None),
    ("Record.Confirmed_ISPs__c", "none", None, None, None),
]
s3_right = [
    ("Record.Incumbent_Provider__c", "none", None, None, None),
    ("Record.Incumbent_Agreement_Type__c", "none", None, None, None),
    ("Record.Incumbent_Agreement_Expiration__c", "none", None, None, None),
]

# Section 4: Integration Links
s4_left = [
    ("Record.SiteTracker_Project_ID__c", "none", None, None, None),
    ("Record.SiteTracker_URL__c", "none", None, None, None),
]
s4_right = [
    ("Record.IronClad_URL__c", "none", None, None, None),
]

# Section 5: Migration Reference
s5_left = [
    ("Record.Monday_Item_ID__c", "none", None, None, None),
]

# Section 6: System Information
s6_left = [
    ("Record.CreatedById", "readonly", None, None, None),
]
s6_right = [
    ("Record.LastModifiedById", "readonly", None, None, None),
]


# ── Build FlexiPage XML ──

# Build field column regions
field_regions = ""
field_regions += build_column_region("Facet_s1_l", s1_left)
field_regions += build_column_region("Facet_s1_r", s1_right)
field_regions += build_columns_region("Facet_s1_c", "Facet_s1_l", "Facet_s1_r")
field_regions += build_column_region("Facet_s2_l", s2_left)
field_regions += build_column_region("Facet_s2_r", s2_right)
field_regions += build_columns_region("Facet_s2_c", "Facet_s2_l", "Facet_s2_r")
field_regions += build_column_region("Facet_s3_l", s3_left)
field_regions += build_column_region("Facet_s3_r", s3_right)
field_regions += build_columns_region("Facet_s3_c", "Facet_s3_l", "Facet_s3_r")
field_regions += build_column_region("Facet_s4_l", s4_left)
field_regions += build_column_region("Facet_s4_r", s4_right)
field_regions += build_columns_region("Facet_s4_c", "Facet_s4_l", "Facet_s4_r")
s5_right = []  # empty right column
field_regions += build_column_region("Facet_s5_l", s5_left)
field_regions += build_column_region("Facet_s5_r", s5_right)
field_regions += build_columns_region("Facet_s5_c", "Facet_s5_l", "Facet_s5_r")
field_regions += build_column_region("Facet_s6_l", s6_left)
field_regions += build_column_region("Facet_s6_r", s6_right)
field_regions += build_columns_region("Facet_s6_c", "Facet_s6_l", "Facet_s6_r")

# Build section items for the detail tab
section_items = ""
section_items += build_section("fs_s1", "Opportunity Information", "Facet_s1_c")
section_items += build_section("fs_s2", "Property Details", "Facet_s2_c")
section_items += build_section("fs_s3", "ISP Information", "Facet_s3_c")
section_items += build_section("fs_s4", "Integration Links", "Facet_s4_c")
section_items += build_section("fs_s5", "Migration Reference", "Facet_s5_c")
section_items += build_section("fs_s6", "System Information", "Facet_s6_c")

flexipage_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Opportunity.Id</value>
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
                <identifier>force_relatedListSingleContainer_oppContacts</identifier>
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
                    <value>Agreements__r</value>
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
                <identifier>force_relatedListSingleContainer</identifier>
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
                    <value>SiteTracker_Projects__r</value>
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
                    <value>false</value>
                </componentInstanceProperties>
                <componentName>force:relatedListSingleContainer</componentName>
                <identifier>force_relatedListSingleContainer_stProjects</identifier>
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
                <identifier>force_relatedListSingleContainer2</identifier>
            </componentInstance>
        </itemInstances>
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
        {section_items}
        <name>Facet-detailTab</name>
        <type>Facet</type>
    </flexiPageRegions>
    {field_regions}
    <masterLabel>MDU Opportunity Record Page</masterLabel>
    <sobjectType>Opportunity</sobjectType>
    <template>
        <name>flexipage:recordHomeThreeColTemplateDesktop</name>
    </template>
    <type>RecordPage</type>
</FlexiPage>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MDU_Opportunity_Record_Page</members>
        <name>FlexiPage</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('flexipages/MDU_Opportunity_Record_Page.flexipage', flexipage_xml)
buf.seek(0)
zip_bytes = buf.read()

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
body_parts = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
    f'{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
    f'Content-Type: application/zip\r\n\r\n'
).encode('utf-8')
body_end = f'\r\n--{boundary}--'.encode('utf-8')

resp = requests.post(
    deploy_url,
    headers={
        'Authorization': f'Bearer {sf.session_id}',
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    },
    data=body_parts + zip_bytes + body_end
)
print(f'Deploy: {resp.status_code}')
if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(30):
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
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            else:
                print("\nFlexiPage updated successfully!")
            break
else:
    print(resp.text[:500])
