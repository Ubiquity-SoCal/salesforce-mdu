"""Merge Melissa's Dobson Ranch Condos dup (006WR000015Ifm7YAC) into the existing
Opp (006WR00000wkEcUYAU) and delete the dup.

Source Opp (DUP — Melissa created today, will be deleted):
  006WR000015Ifm7YAC  "Dobson Ranch Condos"  Owner: Melissa Baker

Target Opp (EXISTING — keep, augment):
  006WR00000wkEcUYAU  "Dobson Ranch Condos"  3 Agreements + 25 Notes + 1 SiteTracker

What moves over (per Koa's call):
  - 3 Opportunity_Contact__c junctions: Susan Thompson (HOA), Patsy Fawcett (Other),
    Shelly Loomer (HOA). Note: OC is master-detail on Opp (see
    sf-master-detail-no-reparent.md), so we CLONE rather than re-parent.
  - 4 field updates on target Opp:
      Incumbent_Provider__c            "Cox" -> "FiberFirst"
      Incumbent_Agreement_Type__c       (null) -> "EMA"
      Incumbent_Agreement_Expiration__c (null) -> 2035-02-17
      Projected_Close_Date__c           (null) -> 2026-07-31

What does NOT move:
  - Stage (existing MB Complete is correct: 3 completed agreements + Sept 2025 notes)
  - Site Name (existing Mesa_MDU_... matches convention)
  - ISP/Property Classification (existing has values, dup blanks)

Order of operations:
  1. Snapshot target Opp field values (for rollback)
  2. Update target Opp with the 4 field migrations
  3. Create 3 new OC junctions under target
  4. Delete the dup Opp (cascade-deletes its 3 OCs)
  5. Write audit CSV
"""
import os, sys, io, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime, timezone
from pathlib import Path
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

DUP_ID    = '006WR000015Ifm7YAC'   # Melissa's new Opp -- will be deleted
TARGET_ID = '006WR00000wkEcUYAU'   # Existing Opp -- gets the migrated data

FIELD_UPDATES = {
    'Incumbent_Provider__c':            'FiberFirst',
    'Incumbent_Agreement_Type__c':      'EMA',
    'Incumbent_Agreement_Expiration__c': '2035-02-17',
    'Projected_Close_Date__c':          '2026-07-31',
}

SCRIPT = '2026-05-19-dobson-ranch-dup-cleanup.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
audit = []
def log(sf_id, name, field, before, after, action, note=''):
    audit.append({'SF_Id': sf_id, 'Name': name, 'Field': field,
                  'Before': before, 'After': after, 'Source': SCRIPT,
                  'Timestamp': TS, 'Action': action, 'Note': note})

# 1. Pre-update snapshot
print('[1/5] Snapshotting target Opp field values...')
tgt = sf.Opportunity.get(TARGET_ID)
before_vals = {k: tgt.get(k) for k in FIELD_UPDATES}
print(f"     Target target Opp '{tgt.get('Name')}'")
for k, v in before_vals.items():
    print(f'       {k}: {v!r}')

# Pull dup OC junctions (the contacts to migrate)
print('\n[2/5] Pulling dup OC junctions...')
oc_q = (f"SELECT Id, Name, Contact__c, Contact__r.Name, Role__c "
        f"FROM Opportunity_Contact__c WHERE Opportunity__c = '{DUP_ID}'")
ocs = sf.query_all(oc_q)['records']
print(f'     Found {len(ocs)} OC junctions to clone:')
for oc in ocs:
    print(f"       {oc['Name']}  Contact={oc['Contact__r']['Name']}  Role={oc.get('Role__c')}")

# 3. Apply field updates to target Opp
print('\n[3/5] Updating target Opp fields...')
sf.Opportunity.update(TARGET_ID, FIELD_UPDATES)
for k, new in FIELD_UPDATES.items():
    log(TARGET_ID, tgt.get('Name'), k, before_vals.get(k), new, 'UPDATE',
        note=f'Migrated from dup {DUP_ID}')

# 4. Clone OC junctions under target Opp
print('\n[4/5] Cloning OC junctions under target Opp...')
new_oc_ids = []
for oc in ocs:
    payload = {
        'Opportunity__c': TARGET_ID,
        'Contact__c':     oc['Contact__c'],
        'Role__c':        oc.get('Role__c'),
    }
    res = sf.Opportunity_Contact__c.create(payload)
    new_oc_ids.append(res['id'])
    log(res['id'], f"clone of {oc['Name']}", '(created)', '',
        f"Opp={TARGET_ID}, Contact={oc['Contact__r']['Name']}, Role={oc.get('Role__c')}",
        'CREATE', note=f'Cloned from dup OC {oc["Id"]}')
    print(f"       Created OC {res['id']} for {oc['Contact__r']['Name']}")

# 5. Delete the dup Opp (cascade-deletes its 3 OC junctions automatically)
print('\n[5/5] Deleting dup Opp...')
dup = sf.Opportunity.get(DUP_ID)
sf.Opportunity.delete(DUP_ID)
log(DUP_ID, dup.get('Name'), '(deleted)', 'present', 'deleted', 'DELETE',
    note=f'Dup of {TARGET_ID}; 3 OCs cascade-deleted: {[o["Id"] for o in ocs]}')
for oc in ocs:
    log(oc['Id'], oc['Name'], '(deleted)', 'present', 'deleted', 'DELETE_CASCADE',
        note=f'Cascade-deleted with parent Opp {DUP_ID}')
print(f"       Deleted dup Opp {DUP_ID}")

# Audit log
audit_path = AUDIT_DIR / f'2026-05-19-dobson-ranch-dup-cleanup.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before', 'After',
                                       'Source', 'Timestamp', 'Action', 'Note'])
    w.writeheader()
    w.writerows(audit)
print(f'\nAudit log: {audit_path} ({len(audit)} rows)')
