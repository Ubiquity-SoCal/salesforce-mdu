"""
Deploy updated Property Unit FlexiPage via Tooling API PATCH.
Uses the Tooling API to update the existing FlexiPage metadata directly,
which avoids the template/region mode issues with Metadata API deploys.
"""
from simple_salesforce import Salesforce
import requests, json, copy

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)
headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

# Load the backup
with open(r'C:/Users/cass/Work_Projects/SalesForce/property_unit_flexipage_backup.json') as f:
    meta = json.load(f)

# Fields to REMOVE from the page
remove_fields = {
    # From Address Info (was col1)
    'Record.Record_ID_Unit__c',
    'Record.Unit_Sales_Status__c',
    'Record.Update_Last_Sales_Status_Change_Date__c',
    'Record.Ordered_Product__c',
    'Record.Combined_Sales_Status__c',
    # From Address Info (was col2)
    'Record.AreaId__c',
    'Record.Import_Delete_Unit__c',
    # From Address Status
    'Record.EOPC__c',
    'Record.Service_Agreement_Executed__c',
    'Record.ROE__c',
    'Record.CX_Complete__c',
    'Record.ValidForFF__c',
}

# Sections to REMOVE entirely
remove_sections = {'RE Team', 'Sales'}

# Sidebar related lists to REMOVE
remove_sidebar_lists = {'Property_Unit_File_Links__r', 'File_Links__r'}


def get_fields_in_facet(facet_name, regions):
    """Get all field names in a facet region."""
    for r in regions:
        if r['name'] == facet_name:
            return [
                item['fieldInstance']['fieldItem']
                for item in r.get('itemInstances', [])
                if item.get('fieldInstance')
            ]
    return []


def remove_fields_from_facet(facet_name, regions, fields_to_remove):
    """Remove specific fields from a facet region."""
    for r in regions:
        if r['name'] == facet_name:
            r['itemInstances'] = [
                item for item in r['itemInstances']
                if not (item.get('fieldInstance') and
                       item['fieldInstance']['fieldItem'] in fields_to_remove)
            ]


def remove_region(name, regions):
    """Remove a region by name."""
    return [r for r in regions if r['name'] != name]


# Work on a copy
new_meta = copy.deepcopy(meta)
regions = new_meta['flexiPageRegions']

# Step 1: Find section labels and their facet mappings
main_region = None
for r in regions:
    if r['name'] == 'main':
        main_region = r
        break

section_facets = {}  # label -> facet names used by columns
sections_to_remove_facets = set()

if main_region:
    new_items = []
    for item in main_region['itemInstances']:
        comp = item.get('componentInstance')
        if comp and comp.get('componentName') == 'flexipage:fieldSection':
            label = None
            col_facet = None
            for p in comp.get('componentInstanceProperties', []):
                if p['name'] == 'label':
                    label = p.get('value', '')
                if p['name'] == 'columns':
                    col_facet = p.get('value', '')

            if label in remove_sections:
                # Mark all facets used by this section for removal
                sections_to_remove_facets.add(col_facet)
                print(f'Removing section: {label} (facet: {col_facet})')
                continue

            section_facets[label] = col_facet
        new_items.append(item)
    main_region['itemInstances'] = new_items

# Step 2: Find all facets referenced by removed sections and trace their children
facets_to_remove = set()
def trace_facets(facet_name):
    """Recursively find all child facets of a given facet."""
    facets_to_remove.add(facet_name)
    for r in regions:
        if r['name'] == facet_name:
            for item in r.get('itemInstances', []):
                comp = item.get('componentInstance')
                if comp:
                    for p in comp.get('componentInstanceProperties', []):
                        if p['name'] == 'body' and p.get('value'):
                            trace_facets(p['value'])

for f in sections_to_remove_facets:
    trace_facets(f)

print(f'Facets to remove: {facets_to_remove}')

# Step 3: Remove those facet regions
new_meta['flexiPageRegions'] = [
    r for r in new_meta['flexiPageRegions']
    if r['name'] not in facets_to_remove
]
regions = new_meta['flexiPageRegions']

# Step 4: Remove individual fields from remaining facets
for r in regions:
    if r['name'].startswith('Facet-'):
        original_count = len(r.get('itemInstances', []))
        r['itemInstances'] = [
            item for item in r.get('itemInstances', [])
            if not (item.get('fieldInstance') and
                   item['fieldInstance']['fieldItem'] in remove_fields)
        ]
        removed = original_count - len(r['itemInstances'])
        if removed > 0:
            print(f'Removed {removed} fields from {r["name"]}')

# Step 5: Clean up sidebar - remove unwanted related lists
for r in regions:
    if r['name'] == 'sidebar':
        new_items = []
        for item in r.get('itemInstances', []):
            comp = item.get('componentInstance')
            if comp:
                props = {p['name']: p.get('value') for p in comp.get('componentInstanceProperties', [])}
                api_name = props.get('relatedListApiName', '')
                if api_name in remove_sidebar_lists:
                    print(f'Removing sidebar list: {api_name}')
                    continue
            new_items.append(item)
        r['itemInstances'] = new_items

# Step 6: Rename "Address Info" section to "Unit Details"
for r in regions:
    if r['name'] == 'main':
        for item in r.get('itemInstances', []):
            comp = item.get('componentInstance')
            if comp:
                for p in comp.get('componentInstanceProperties', []):
                    if p['name'] == 'label' and p.get('value') == 'Address Info':
                        p['value'] = 'Unit Details'
                        print('Renamed "Address Info" to "Unit Details"')
                    if p['name'] == 'label' and p.get('value') == 'CHR Data':
                        p['value'] = 'Customer & Service Data'
                        print('Renamed "CHR Data" to "Customer & Service Data"')

# Step 7: Deploy via Tooling API PATCH
page_id = '0M0WR0000002DHJ0A2'
url = f'{sf.base_url}tooling/sobjects/FlexiPage/{page_id}'
payload = {'Metadata': new_meta}

print(f'\nDeploying to {url}...')
resp = requests.patch(url, headers=headers, json=payload)
print(f'Status: {resp.status_code}')
if resp.status_code == 204:
    print('SUCCESS - FlexiPage updated!')
else:
    print(f'Response: {resp.text[:2000]}')
