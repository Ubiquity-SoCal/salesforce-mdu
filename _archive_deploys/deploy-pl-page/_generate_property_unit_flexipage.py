"""
Generate Property_Unit_Record_Page.flexipage-meta.xml
Same layout pattern as Property_Location:
  - 3-col template (recordHomeThreeColTemplateDesktop)
  - leftsidebar: Opportunities (with +New) + Property_Unit_File_Links
  - main: highlights panel + 4 tabs
  - rightsidebar: Quick Links + Contacts + Activity panel + Notes
"""

TAB1_MAIN_INFO = [
    ("Unit Identity", 2, [
        ["Name", "Property_Location__c", "Unit__c"],
        ["Circuit_ID__c", "State_from_Property_Location__c", "Territory_Zone__c"],
    ]),
    ("Activation", 2, [
        ["Activated__c", "Address_Activation_Date__c", "Activation_Status_Icon__c"],
        ["Available_for_Sales_Date_From_Location__c", "ValidForFF__c", "Coho__c"],
    ]),
    ("Deactivation", 2, [
        ["Address_Deactivated__c", "Address_De_activation_Date__c"],
        ["Last_Customer_Disconnect__c", "Latest_Disconnect_Reason__c"],
    ]),
]

TAB2_SALES = [
    ("Assignment", 2, [
        ["Sales_Assigned__c", "Sales_Status__c"],
        ["Combined_Sales_Status__c", "Unit_Sales_Status__c"],
    ]),
    ("Pipeline Dates", 2, [
        ["Initial_Contact__c", "Site_Walk_FC__c", "Site_Walk_AC__c"],
        ["Deal_Complete_FC__c", "Deal_Complete_AC__c", "Update_Last_Sales_Status_Change_Date__c"],
    ]),
    ("Closed", 2, [
        ["Closed_Date__c", "Closed_Bucket__c"],
        ["Closed_Notes__c"],
    ]),
    ("Flags", 2, [
        ["ROE__c", "CX_Complete__c", "Service_Agreement_Executed__c", "EOPC__c"],
        ["Research_Required__c", "Research_Required_Date__c", "Research_Required_Check__c", "Need_more_Info__c"],
    ]),
    ("Research / Info Notes", 1, [
        ["Research_Required_Notes__c", "Need_more_Info_Notes__c"],
    ]),
    ("Estimates", 2, [
        ["Sales_Estimate_Baseline__c"],
        [],
    ]),
]

TAB3_CUSTOMER = [
    ("Customer Contact", 2, [
        ["Customer_Name__c", "Customer_Phone__c"],
        ["Customer_Email__c", "AccountId__c"],
    ]),
    ("Service / Order", 2, [
        ["Order_Number__c", "Ordered_Product__c", "Latest_Service__c"],
        ["Latest_Price__c", "Latest_Install_Date__c", "Segment__c"],
    ]),
    ("Cancellation History", 2, [
        ["Last_Customer_Order_Cancel__c", "Latest_Cancelation_Reason__c"],
        [],
    ]),
]

TAB4_MISC = [
    ("IDs", 2, [
        ["Record_ID_Unit__c", "AreaId__c"],
        ["Map_Link__c", "Unit_Sort_Order__c"],
    ]),
    ("Import / System", 2, [
        ["Import_DateTime__c", "Import_Delete_Unit__c"],
        ["Import_Delete_Note__c"],
    ]),
]

TABS = [
    ("Main Information", TAB1_MAIN_INFO, "tab_main"),
    ("Customer", TAB3_CUSTOMER, "tab_customer"),
    ("Misc Links &amp; IDs", TAB4_MISC, "tab_misc"),
]


# ============================
# XML builders
# ============================

def field_instance(field_name, ui_behavior="none"):
    return f"""        <itemInstances>
            <fieldInstance>
                <fieldInstanceProperties>
                    <name>uiBehavior</name>
                    <value>{ui_behavior}</value>
                </fieldInstanceProperties>
                <fieldItem>Record.{field_name}</fieldItem>
                <identifier>Record{field_name.replace('__c','').replace('.','_')}Field</identifier>
            </fieldInstance>
        </itemInstances>
"""


def column_component(facet_id, identifier):
    return f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>body</name>
                    <value>{facet_id}</value>
                </componentInstanceProperties>
                <componentName>flexipage:column</componentName>
                <identifier>{identifier}</identifier>
            </componentInstance>
        </itemInstances>
"""


def field_section_component(label, columns_facet_id, identifier):
    return f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>columns</name>
                    <value>{columns_facet_id}</value>
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
        </itemInstances>
"""


def facet(name, body):
    return f"""    <flexiPageRegions>
{body}        <name>{name}</name>
        <type>Facet</type>
    </flexiPageRegions>
"""


def region(name, body):
    return f"""    <flexiPageRegions>
{body}        <name>{name}</name>
        <type>Region</type>
    </flexiPageRegions>
"""


# ============================
# Build the FlexiPage
# ============================

xml_parts = []
xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>\n<FlexiPage xmlns="http://soap.sforce.com/2006/04/metadata">\n')

# Highlights panel (goes in main region above tabset)
highlights_panel_xml = """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>actionNames</name>
                    <valueList>
                        <valueListItems><value>Edit</value></valueListItems>
                        <valueListItems><value>Delete</value></valueListItems>
                        <valueListItems><value>Clone</value></valueListItems>
                        <valueListItems><value>Share</value></valueListItems>
                        <valueListItems><value>PrintableView</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>collapsed</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>enableActionsConfiguration</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>numVisibleActions</name>
                    <value>3</value>
                </componentInstanceProperties>
                <componentName>force:highlightsPanel</componentName>
                <identifier>force_highlightsPanel</identifier>
            </componentInstance>
        </itemInstances>
"""

# ---- LEFT SIDEBAR: Opportunities + Unit File Links ----
left_body = """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>actionNames</name>
                    <valueList>
                        <valueListItems><value>New</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>maxRecordsToDisplay</name>
                    <value>10</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Property_Unit__c.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>Opportunities__r</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListDisplayType</name>
                    <value>ADVGRID</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListFieldAliases</name>
                    <valueList>
                        <valueListItems><value>OPPORTUNITY.NAME</value></valueListItems>
                        <valueListItems><value>OPPORTUNITY.STAGE_NAME</value></valueListItems>
                        <valueListItems><value>OPPORTUNITY.CLOSE_DATE</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListLabel</name>
                    <value>Opportunities</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>showActionBar</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>sortFieldAlias</name>
                    <value>__DEFAULT__</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>sortFieldOrder</name>
                    <value>Default</value>
                </componentInstanceProperties>
                <componentName>lst:dynamicRelatedList</componentName>
                <identifier>left_opps_related_list</identifier>
            </componentInstance>
        </itemInstances>
"""
xml_parts.append(region("leftsidebar", left_body))

# ---- MAIN region: highlights panel + tabset ----
main_body = highlights_panel_xml + """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>tabs</name>
                    <value>Facet-tabsetTabs</value>
                </componentInstanceProperties>
                <componentName>flexipage:tabset</componentName>
                <identifier>main_tabset</identifier>
            </componentInstance>
        </itemInstances>
"""
xml_parts.append(region("main", main_body))

# ---- TABSET FACET ----
tabset_facet_body = ""
for i, (title, _, tab_id) in enumerate(TABS):
    active = "true" if i == 0 else "false"
    tabset_facet_body += f"""        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>active</name>
                    <value>{active}</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>body</name>
                    <value>Facet-{tab_id}-body</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>title</name>
                    <value>{title}</value>
                </componentInstanceProperties>
                <componentName>flexipage:tab</componentName>
                <identifier>{tab_id}</identifier>
            </componentInstance>
        </itemInstances>
"""
xml_parts.append(facet("Facet-tabsetTabs", tabset_facet_body))

# ---- TAB BODY FACETS ----
all_subfacets = []
for title, sections, tab_id in TABS:
    tab_body = ""
    for s_idx, (sec_label, n_cols, cols_data) in enumerate(sections):
        section_id = f"{tab_id}_s{s_idx}"
        cols_facet = f"Facet-{section_id}-cols"
        tab_body += field_section_component(sec_label, cols_facet, f"fs_{section_id}")
        cols_facet_body = ""
        for c_idx in range(n_cols):
            content_facet = f"Facet-{section_id}-c{c_idx}"
            cols_facet_body += column_component(content_facet, f"col_{section_id}_{c_idx}")
            content_body = ""
            if c_idx < len(cols_data):
                for fname in cols_data[c_idx]:
                    content_body += field_instance(fname)
            all_subfacets.append((content_facet, content_body))
        all_subfacets.append((cols_facet, cols_facet_body))
    all_subfacets.append((f"Facet-{tab_id}-body", tab_body))

for name, body in all_subfacets:
    xml_parts.append(facet(name, body))

# ---- RIGHT SIDEBAR ----
right_body = ""

# Related List Quick Links
right_body += """        <itemInstances>
            <componentInstance>
                <componentName>force:relatedListQuickLinksContainer</componentName>
                <identifier>related_list_quick_links</identifier>
            </componentInstance>
        </itemInstances>
"""

# Contacts related list
right_body += """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>actionNames</name>
                    <valueList>
                        <valueListItems><value>NewContact</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>maxRecordsToDisplay</name>
                    <value>10</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Property_Unit__c.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>Contacts__r</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListDisplayType</name>
                    <value>ADVGRID</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListFieldAliases</name>
                    <valueList>
                        <valueListItems><value>FULL_NAME</value></valueListItems>
                        <valueListItems><value>CONTACT.TITLE</value></valueListItems>
                        <valueListItems><value>CONTACT.PHONE1</value></valueListItems>
                        <valueListItems><value>CONTACT.EMAIL</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListLabel</name>
                    <value>Contacts</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>showActionBar</name>
                    <value>true</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>sortFieldAlias</name>
                    <value>__DEFAULT__</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>sortFieldOrder</name>
                    <value>Default</value>
                </componentInstanceProperties>
                <componentName>lst:dynamicRelatedList</componentName>
                <identifier>contacts_related_list</identifier>
            </componentInstance>
        </itemInstances>
"""

# Activity panel directly
right_body += """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>showLegacyActivityComposer</name>
                    <value>false</value>
                </componentInstanceProperties>
                <componentName>runtime_sales_activities:activityPanel</componentName>
                <identifier>activity_panel_direct</identifier>
            </componentInstance>
        </itemInstances>
"""

# Notes
right_body += """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Property_Unit__c.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>AttachedContentNotes</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListComponentOverride</name>
                    <value>ADVGRID</value>
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
                <identifier>notes_related_list</identifier>
            </componentInstance>
        </itemInstances>
"""

xml_parts.append(region("rightsidebar", right_body))

xml_parts.append("""    <masterLabel>Property Unit Record Page1</masterLabel>
    <sobjectType>Property_Unit__c</sobjectType>
    <template>
        <name>flexipage:recordHomeThreeColTemplateDesktop</name>
    </template>
    <type>RecordPage</type>
</FlexiPage>
""")

output = "".join(xml_parts)
out_path = r"C:/Users/cass/Work_Projects/SalesForce/deploy-pl-page/force-app/main/default/flexipages/Property_Unit_Record_Page1.flexipage-meta.xml"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(output)
print(f"Wrote {len(output)} bytes / {output.count(chr(10))} lines to {out_path}")
