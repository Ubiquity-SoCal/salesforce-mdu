"""
Retroactively build audit CSVs for today's (2026-04-24) batch updates.

Each CSV captures: SF_Id, Name, Field, Before, After, Source, Timestamp, Action
Files land in SalesForce/audit_logs/ for later review.
"""
import sys, io, json, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce
from datetime import datetime
from pathlib import Path

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
TS = datetime.now().isoformat(timespec='seconds')

def write_csv(filename, rows):
    path = OUT / filename
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id','Name','Field','Before','After','Source','Timestamp','Action'])
        for r in rows:
            w.writerow(r)
    print(f"  {filename}: {len(rows)} rows")

def fetch_names(ids):
    if not ids: return {}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i+200]
        ids_sql = ",".join(f"'{x}'" for x in chunk)
        try:
            r = sf.query(f"SELECT Id, Name FROM Opportunity WHERE Id IN ({ids_sql})")
            for o in r['records']: out[o['Id']] = o.get('Name')
        except Exception:
            pass
    return out

# ── 1. Monday orphan imports (21 Opps created) ──────────────────────────────
with open(r'C:\Users\cass\Work_Projects\Monday.com\orphan_import_results_2026-04-24.json') as f:
    orp = json.load(f)
rows = []
for e in orp.get('created', []):
    rows.append([e['sf_id'], e['name'], 'Opportunity.Created', '(null)', 'new record',
                 'Monday.com/scripts/apply_orphan_imports_2026-04-24.py', TS, 'create'])
for lk in orp.get('linked', []):
    rows.append([lk['sf_id'], 'Beacons Beach Village', 'Monday_Item_ID__c', '(null)', lk['monday_id'],
                 'orphan_import_preview_2026-04-24.json', TS, 'update'])
for fl in orp.get('flipped', []):
    rows.append([fl['sf_id'], fl['name'], 'StageName', '(prior)', fl['new_stage'],
                 'apply_orphan_imports_2026-04-24.py', TS, 'update'])
write_csv('monday_orphan_imports_2026-04-24.csv', rows)

# ── 2. IronClad 12 easement linkages + stage promotions ─────────────────────
with open(r'C:\Users\cass\Work_Projects\IronClad\link_results_2026-04-24.json') as f:
    lr = json.load(f)
rows = []
for c in lr.get('created', []):
    rows.append([c['sf_id'], c['counterparty'] + ' -> ' + c['opp'], 'Agreement__c.Created',
                 '(none)', f"new Agreement_Type=ROE, IronClad_Record__c linked",
                 'link_ironclad_easements_2026-04-24.py', TS, 'create'])
for p in lr.get('promoted', []):
    rows.append(['(opp)', p['opp'], 'StageName', p['from'], p['to'],
                 'link_ironclad_easements_2026-04-24.py', TS, 'update'])
write_csv('ironclad_easement_linkages_2026-04-24.csv', rows)

# ── 3. IronClad bulk upsert (1,143 records) ──────────────────────────────────
rows = [['(IronClad__c)', '1,143 records upserted', 'IronClad__c.*',
         'prior state', '88 new + 1,055 updates',
         'SalesForce/scripts/import/import_ironclad_data.py + ironclad_export_2026-04-24_162341_all_export.xlsx',
         TS, 'bulk upsert']]
write_csv('ironclad_bulk_upsert_2026-04-24.csv', rows)

# ── 4. Franchise_Type field deploy + FLS + backfill ─────────────────────────
rows = [
    ['(schema)', 'Opportunity.Franchise_Type__c', 'CustomField.Created', '(no field)',
     "picklist: 'In-Franchise','National'",
     'deploy-franchise-type/force-app via sf project deploy start', TS, 'deploy'],
    ['(schema)', 'Opportunity.MDU record type', 'RecordType.picklistValues', '(no Franchise_Type)',
     'added Franchise_Type picklist values', 'deploy-franchise-type', TS, 'deploy'],
    ['(schema)', 'Opportunity.Business record type', 'RecordType.picklistValues', '(no Franchise_Type)',
     'added Franchise_Type picklist values', 'deploy-franchise-type', TS, 'deploy'],
    ['(FLS)', 'Profile: System Administrator', 'FieldPermissions on Opportunity.Franchise_Type__c',
     '(no access)', 'Read+Edit granted', 'simple_salesforce FieldPermissions.create', TS, 'grant'],
    ['(FLS)', 'Profile: Standard User', 'FieldPermissions on Opportunity.Franchise_Type__c',
     '(no access)', 'Read+Edit granted', 'simple_salesforce FieldPermissions.create', TS, 'grant'],
    ['(FLS)', 'Profile: B2B Vendor', 'FieldPermissions on Opportunity.Franchise_Type__c',
     '(no access)', 'Read+Edit granted', 'simple_salesforce FieldPermissions.create', TS, 'grant'],
]
write_csv('franchise_type_schema_changes_2026-04-24.csv', rows)

# Franchise_Type backfill — list the 3,228 updated ids
print("  Querying Franchise_Type__c set on Opps...")
r = sf.query_all("SELECT Id, Name, Franchise_Type__c, Monday_Item_ID__c FROM Opportunity WHERE Franchise_Type__c != null")
rows = []
for o in r['records']:
    rows.append([o['Id'], o.get('Name'), 'Franchise_Type__c', '(null)', o.get('Franchise_Type__c'),
                 'franchise_mapping.json (Monday-derived)', TS, 'backfill'])
write_csv('franchise_type_backfill_2026-04-24.csv', rows)

# ── 5. CA MDU Property_Category backfill (85 writes) ─────────────────────────
# We don't have a structured log; rely on the Pipeline_Bucket__c set that correlates
print("  Querying Pipeline_Bucket__c-populated Opps (CA MDU merge subset)...")
r = sf.query_all("SELECT Id, Name, Property_Category__c, Pipeline_Bucket__c FROM Opportunity WHERE Pipeline_Bucket__c != null")
rows = []
for o in r['records']:
    rows.append([o['Id'], o.get('Name'), 'Property_Category__c', '(prior, mostly null)',
                 o.get('Property_Category__c') or '(null)',
                 'CA MDU Agreement Status 04172026.xlsx (On Net? Yes/No)', TS, 'backfill'])
write_csv('ca_property_category_backfill_2026-04-24.csv', rows)

# ── 6. Vetro classifier v1 (applied, later reverted in v2) ──────────────────
with open(r'C:\Users\cass\Work_Projects\SalesForce\vetro_classifier_preview.json') as f:
    v1 = json.load(f)
with open(r'C:\Users\cass\Work_Projects\SalesForce\vetro_classifier_preview_v2.json') as f:
    v2 = json.load(f)

all_ids = set(v1['cat1_ids']) | set(v1['cat2_ids']) | set(v2['cat1_ids']) | set(v2['cat2_ids'])
names = fetch_names(all_ids)

rows = []
for i in v1['cat1_ids']:
    rows.append([i, names.get(i,'?'), 'Property_Category__c', '(null/Cat 3)', 'Cat 1',
                 'vetro_category_classifier.py v1 (loose rule)', TS, 'backfill (later corrected)'])
for i in v1['cat2_ids']:
    rows.append([i, names.get(i,'?'), 'Property_Category__c', '(null/Cat 3)', 'Cat 2',
                 'vetro_category_classifier.py v1', TS, 'backfill (later corrected)'])
write_csv('vetro_classifier_v1_applied_2026-04-24.csv', rows)

# ── 7. Vetro classifier v2 correction ───────────────────────────────────────
rows = []
for i in v2.get('revert_cat1', []) + v2.get('revert_cat2', []):
    rows.append([i, names.get(i,'?'), 'Property_Category__c', '(v1 Cat 1 or Cat 2)', '(null)',
                 'vetro_tightened.py v2', TS, 'revert'])
for i in v2.get('flip_c1_to_c2', []):
    rows.append([i, names.get(i,'?'), 'Property_Category__c', 'Cat 1', 'Cat 2',
                 'vetro_tightened.py v2', TS, 'flip'])
# v2 NEW cat1 additions = v2_cat1 - v1_cat1
new_c1 = set(v2['cat1_ids']) - set(v1['cat1_ids'])
new_c2 = set(v2['cat2_ids']) - set(v1['cat2_ids']) - set(v2.get('flip_c1_to_c2') or [])
for i in new_c1:
    rows.append([i, names.get(i,'?'), 'Property_Category__c', '(null/Cat 3)', 'Cat 1',
                 'vetro_tightened.py v2 (strict: SA+FDH activated + serviceable)', TS, 'backfill'])
for i in new_c2:
    rows.append([i, names.get(i,'?'), 'Property_Category__c', '(null/Cat 3)', 'Cat 2',
                 'vetro_tightened.py v2', TS, 'backfill'])
write_csv('vetro_classifier_v2_correction_2026-04-24.csv', rows)

print(f"\nAll audit logs written to {OUT}")
