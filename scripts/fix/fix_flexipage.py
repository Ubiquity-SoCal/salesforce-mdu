from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')

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

# Define sections
sections = [
    ("Opportunity Information", "s1",
     ["Name", "AccountId", "Contact__c", "Agreement_Name__c"],
     ["none", "none", "none", "none"],
     ["OwnerId", "CloseDate", "StageName", "Probability", "Amount"],
     ["none", "none", "none", "none", "none"]),
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
    <masterLabel>Opportunity Record Page - Three Column</masterLabel>
    <sobjectType>Opportunity</sobjectType>
    <template>
        <name>flexipage:recordHomeThreeColTemplateDesktop</name>
    </template>
    <type>RecordPage</type>
</FlexiPage>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity_Record_Page_Three_Column</members>
        <name>FlexiPage</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('flexipages/Opportunity_Record_Page_Three_Column.flexipage', flexipage_xml)
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
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
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
            break
else:
    print(resp.text[:500])
