"""
Generate Property_Location_Record_Page.flexipage-meta.xml
3-column tabbed layout:
  - header: highlights panel
  - leftsidebar: Property Units related list
  - main: 4-tab tabset (Main Info / Real Estate / Address Mgmt / Misc Links & IDs)
  - rightsidebar: Quick Links + Agreements + Opportunities + ST Projects + Contacts + Activity + Notes
"""

# ============================
# Field & section configuration
# ============================

# Each tab is a list of (section_label, columns, field_list)
# columns = 1 or 2; field_list is list of field API names

TAB1_MAIN_INFO = [
    ("Property Identity", 2, [
        ["Name", "Property_Type__c", "Building_Floor_Type__c"],
        ["Property_Customer_Bucket__c", "All_Units_Active_Icon__c"],
    ]),
    ("Address", 2, [
        ["Business_Base_Address__c", "City__c", "State__c"],
        ["Market__c", "Serving_Area__c"],
    ]),
    ("Status", 2, [
        ["Property_Status__c", "Hold__c"],
        ["Priority__c"],
    ]),
    ("Counts", 2, [
        ["Property_Unit_Count__c", "Active_Unit_Count__c", "Deactive_Unit_Count__c", "Available_for_Sales_Count__c"],
        ["number_of_buildings__c", "number_of_parcels__c", "number_of_owners__c"],
    ]),
]

TAB2_REAL_ESTATE = [
    ("Assignment", 2, [
        ["User__c"],
        ["Build_Effort__c", "SMB_RE_In_Scope__c"],
    ]),
    ("MTU", 2, [
        ["Categorize_as_MTU__c", "MTU_Group_Name__c", "MTU_Address_Reviewed__c"],
        ["Related_MTU_Addresses__c", "MTU_Notes__c"],
    ]),
    ("Notes", 1, [
        ["RE_Notes__c", "Potential_Issues__c"],
    ]),
]

TAB3_ADDRESS_MGMT = [
    ("AM Status", 2, [
        ["AM_Status__c", "AM_Review_Status__c", "AM_Flag_RE_to_Review__c", "AM_Suite_Numbers__c"],
        ["Additional_Units_found__c", "AVR_Project_ID__c", "Address_Review_Required__c", "RE_Reviewed__c"],
    ]),
    ("AM Review", 2, [
        ["RE_Reviewer_AM__c", "RE_Review_Date_AM__c"],
        ["RE_Review_Notes_AM__c"],
    ]),
    ("GIS", 2, [
        ["GIS_API_Match__c", "GIS_Reviewer__c", "GIS_Review_Date__c"],
        ["GIS_Review_Quarter__c", "GIS_Notes__c"],
    ]),
    ("Sync Flags", 2, [
        ["Import_Delete_Property__c"],
        ["Import_Delete_Note__c"],
    ]),
]

TAB4_MISC = [
    ("IDs", 2, [
        ["Record_ID_Property__c", "Business_Building_Id__c"],
        ["Assignment_Reference__c", "Parcel__c"],
    ]),
    ("Network", 2, [
        ["FDH_Name__c", "Circuit_ID__c"],
        ["FDH_Activated_Date__c", "Year_Month_FDH_Activation__c"],
    ]),
    ("Import / System", 1, [
        ["Import_DateTime__c"],
    ]),
]

TABS = [
    ("Main Information", TAB1_MAIN_INFO, "tab_main"),
    ("Real Estate", TAB2_REAL_ESTATE, "tab_re"),
    ("Address Management", TAB3_ADDRESS_MGMT, "tab_am"),
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

# (Highlights panel moved into the main region above the tabset
#  to match the Opportunity page template — no separate header region)
highlights_panel_xml = """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>actionNames</name>
                    <valueList>
                        <valueListItems><value>Edit</value></valueListItems>
                        <valueListItems><value>Delete</value></valueListItems>
                        <valueListItems><value>Clone</value></valueListItems>
                        <valueListItems><value>Share</value></valueListItems>
                        <valueListItems><value>ChangeOwnerOne</value></valueListItems>
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

# ---- LEFT SIDEBAR: Opportunities (pursuit anchor) + Property Units ----
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
                    <value>Property_Location__c.Id</value>
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
                        <valueListItems><value>Sales_Status__c</value></valueListItems>
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
        <itemInstances>
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
                    <value>Property_Location__c.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>Property_Units__r</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListDisplayType</name>
                    <value>ADVGRID</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListFieldAliases</name>
                    <valueList>
                        <valueListItems><value>NAME</value></valueListItems>
                        <valueListItems><value>Unit__c</value></valueListItems>
                        <valueListItems><value>Activation_Status_Icon__c</value></valueListItems>
                        <valueListItems><value>Sales_Status__c</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListLabel</name>
                    <value>Property Units</value>
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
                <identifier>pl_units_related_list</identifier>
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

# ---- TABSET FACET (lists 4 tabs) ----
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

# ---- TAB BODY FACETS (one per tab) ----
all_subfacets = []  # collect (name, body) for sub-facets used by sections

for title, sections, tab_id in TABS:
    tab_body = ""
    for s_idx, (sec_label, n_cols, cols_data) in enumerate(sections):
        section_id = f"{tab_id}_s{s_idx}"
        cols_facet = f"Facet-{section_id}-cols"
        # Build the section component referencing cols_facet
        tab_body += field_section_component(sec_label, cols_facet, f"fs_{section_id}")
        # Build cols facet (contains 1 or 2 column components)
        cols_facet_body = ""
        for c_idx in range(n_cols):
            content_facet = f"Facet-{section_id}-c{c_idx}"
            cols_facet_body += column_component(content_facet, f"col_{section_id}_{c_idx}")
            # Build content facet (fields)
            content_body = ""
            if c_idx < len(cols_data):
                for fname in cols_data[c_idx]:
                    content_body += field_instance(fname)
            all_subfacets.append((content_facet, content_body))
        all_subfacets.append((cols_facet, cols_facet_body))
    # Tab body facet
    all_subfacets.append((f"Facet-{tab_id}-body", tab_body))

# Append all sub-facets
for name, body in all_subfacets:
    xml_parts.append(facet(name, body))

# ---- RIGHT SIDEBAR: Related lists + Activity tab ----
right_body = ""

# Related List Quick Links (icon row)
right_body += """        <itemInstances>
            <componentInstance>
                <componentName>force:relatedListQuickLinksContainer</componentName>
                <identifier>related_list_quick_links</identifier>
            </componentInstance>
        </itemInstances>
"""

# (Agreements moved to left sidebar above Property Units)

# (Opportunities moved to left sidebar above Property Units, no longer in right col)

# SiteTracker_Projects related list
right_body += """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>maxRecordsToDisplay</name>
                    <value>10</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Property_Location__c.Id</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListApiName</name>
                    <value>SiteTracker_Projects__r</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListDisplayType</name>
                    <value>ADVGRID</value>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListFieldAliases</name>
                    <valueList>
                        <valueListItems><value>NAME</value></valueListItems>
                        <valueListItems><value>Site_Name__c</value></valueListItems>
                        <valueListItems><value>Build_Status__c</value></valueListItems>
                        <valueListItems><value>Site_Status__c</value></valueListItems>
                    </valueList>
                </componentInstanceProperties>
                <componentInstanceProperties>
                    <name>relatedListLabel</name>
                    <value>SiteTracker Projects</value>
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
                <identifier>st_projects_related_list</identifier>
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
                    <value>Property_Location__c.Id</value>
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

# Activity panel directly (skip the tabset wrapper)
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

# Notes related list
right_body += """        <itemInstances>
            <componentInstance>
                <componentInstanceProperties>
                    <name>parentFieldApiName</name>
                    <value>Property_Location__c.Id</value>
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

# (Activity tabset removed — using activity panel directly in right sidebar)

# ---- Closing ----
xml_parts.append("""    <masterLabel>Property Location Record Page</masterLabel>
    <sobjectType>Property_Location__c</sobjectType>
    <template>
        <name>flexipage:recordHomeThreeColTemplateDesktop</name>
    </template>
    <type>RecordPage</type>
</FlexiPage>
""")

# Write file
output = "".join(xml_parts)
out_path = r"C:/Users/cass/Work_Projects/SalesForce/deploy-pl-page/force-app/main/default/flexipages/Property_Location_Record_Page.flexipage-meta.xml"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(output)
print(f"Wrote {len(output)} bytes to {out_path}")
print(f"Lines: {output.count(chr(10))}")
