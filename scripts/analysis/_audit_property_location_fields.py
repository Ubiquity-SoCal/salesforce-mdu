"""
Audit every field on Property_Location__c:
- describe metadata (label, type, custom?, formula?)
- fill rate (% of records with non-null value)
- categorize: core / RE / AM-AVR / sales / legacy-redundant / unused

Output: a sortable table to help decide what to keep/hide/delete on the new page.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Total records (as denominator)
total = sf.query("SELECT COUNT() FROM Property_Location__c")['totalSize']
print(f'Total Property_Location__c records: {total}\n')

# Describe
desc = sf.Property_Location__c.describe()
fields = [f for f in desc['fields'] if f['custom'] and f['name'] not in ('Id', 'OwnerId', 'IsDeleted', 'CreatedDate', 'CreatedById', 'LastModifiedDate', 'LastModifiedById', 'SystemModstamp', 'LastActivityDate', 'LastViewedDate', 'LastReferencedDate')]

# Add the standard Name field too since it's the primary
std_to_check = [{'name': 'Name', 'label': 'Property Location ID', 'type': 'string', 'custom': False, 'calculatedFormula': None}]
fields = std_to_check + fields

# Categorize manually based on naming patterns
def categorize(field):
    n = field['name'].lower()
    if n in ('name', 'property_location_name__c', 'property_type__c', 'type_of_property__c', 'building_floor_type__c', 'city__c', 'state__c', 'business_base_address__c', 'serving_area__c'):
        return 'CORE-Identity'
    if n in ('property_status__c', 'hold__c', 'priority__c', 'market__c'):
        return 'CORE-Status'
    if n in ('property_unit_count__c', 'active_unit_count__c', 'deactive_unit_count__c', 'all_units_active_icon__c', 'available_for_sales__c', 'available_for_sales_count__c', 'property_customer_bucket__c', 'location_count__c', 'number_of_buildings__c', 'number_of_parcels__c', 'number_of_owners__c', 'number_of_tenants__c'):
        return 'CORE-Counts'
    if n in ('fdh_name__c', 'fdh_activated_date__c', 'year_month_fdh_activation__c', 'circuit_id__c', 'parcel__c'):
        return 'CORE-Network'
    if n in ('user__c', 'sales_assigned__c', 'bulk_deal__c', 'access_agreement_required__c', 're_notes__c', 'sales_notes__c', 'potential_issues__c', 'sales_estimate_baseline__c'):
        return 'RE-Sales'
    if n.startswith('roe_') or n in ('site_walk_fc__c', 'site_walk_ac__c'):
        return 'RE-Legacy-Status'
    if n in ('categorize_as_mtu__c', 'related_mtu_addresses__c', 'mtu_group_name__c', 'mtu_notes__c', 'mtu_address_reviewed__c'):
        return 'AM-MTU'
    if n.startswith('am_') or n.startswith('gis_') or n in ('avr_project_id__c', 're_reviewer_am__c', 're_review_date_am__c', 're_review_notes_am__c', 're_reviewed__c', 'address_review_required__c', 'additional_units_found__c'):
        return 'AM-AVR'
    if n.startswith('unit_count_') or n == 'units_in_progress__c':
        return 'Sales-Pipeline-Manual'
    if n in ('record_id_property__c', 'assignment_reference__c', 'business_building_id__c', 'import_delete_property__c', 'import_delete_note__c'):
        return 'IDs-Sync'
    if n in ('ff_sales_project__c', 'ff_sales_assigned_date__c'):
        return 'Misc-FF'
    if n == 'build_effort__c':
        return 'CORE-Network'
    if n == 'number_of_roes__c':
        return 'RE-Legacy-Status'
    if n == 'sales_assigned__c':
        return 'RE-Sales'
    return '???-Other'


# Query fill rate per field
print('Computing fill rate for each field (this may take ~90s)...\n')
rows = []
for f in fields:
    name = f['name']
    label = f.get('label', '')
    ftype = f['type']
    formula = f.get('calculatedFormula') or ''
    is_formula = bool(formula)
    cat = categorize(f)
    try:
        if ftype in ('boolean',):
            # boolean: count where = true
            n_true = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {name} = true")['totalSize']
            fill = n_true
            note = f'true={n_true}'
        elif ftype in ('multipicklist',):
            n = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {name} != null")['totalSize']
            fill = n
            note = ''
        else:
            n = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {name} != null")['totalSize']
            fill = n
            note = ''
    except Exception as e:
        fill = -1
        note = f'err: {str(e)[:60]}'
    pct = round(100 * fill / total, 1) if fill >= 0 else 'err'
    rows.append({'name': name, 'label': label, 'type': ftype, 'formula': is_formula, 'cat': cat, 'fill': fill, 'pct': pct, 'note': note})
    print(f'  {name:45} {ftype:12} cat={cat:25} fill={fill}/{total} ({pct}%) {note}')

# Sort by category then fill rate
print('\n' + '=' * 130)
print('AUDIT SUMMARY — sorted by category, then fill rate desc')
print('=' * 130)
print(f"{'NAME':45} {'TYPE':12} {'CATEGORY':24} {'FILL':>10} {'PCT':>7}  FORMULA")
print('-' * 130)
for r in sorted(rows, key=lambda x: (x['cat'], -x['fill'] if isinstance(x['fill'], int) else 0)):
    flag = ' ⚠ low' if isinstance(r['pct'], (int, float)) and r['pct'] < 5 else ''
    fml = ' [F]' if r['formula'] else ''
    print(f"  {r['name']:45} {r['type']:12} {r['cat']:24} {r['fill']:>10} {str(r['pct']):>6}%{fml}{flag}")
