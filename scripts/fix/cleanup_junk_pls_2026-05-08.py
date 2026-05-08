"""Cleanup of junk records produced by the 2026-05-08 Vetro sync:
  - 2 SFU PLs with junk Name/AgreeName ('0' and 'SFU') - HARD DELETE (incl child Units)
  - 11 Bus PLs with junk Agreement_Name__c values ('PA01','PA05','PA07') - clear field
"""
import sys, io, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984',
                security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
TS = datetime.now().isoformat(timespec='seconds')
SCRIPT = 'cleanup_junk_pls_2026-05-08.py'
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

audit_rows = []
def log(sf_id, name, field, before, after, action, note=''):
    audit_rows.append({'SF_Id': sf_id, 'Name': name, 'Field': field,
                       'Before': before, 'After': after, 'Source': SCRIPT,
                       'Timestamp': TS, 'Action': action, 'Note': note})

# ─── 1. Hard-delete 2 junk SFU PLs (Name='0' and Name='SFU') ───
print('[1/2] Hard-deleting junk SFU PLs (Name="0" and Name="SFU")...')
res = sf.query_all(
    "SELECT Id, Name, Agreement_Name__c FROM Property_Location__c "
    "WHERE Address_Type__c = 'SFU' AND Name IN ('0', 'SFU')"
)
junk_ids = [r['Id'] for r in res['records']]
print(f'  Found {len(junk_ids)} PLs')

# First delete child Units (cascade isn't on for non-master-detail FK; do it manually to be safe)
if junk_ids:
    quoted = "','".join(junk_ids)
    units = sf.query_all(f"SELECT Id, Circuit_ID__c FROM Property_Unit__c WHERE Property_Location__c IN ('{quoted}')")
    print(f'  Deleting {len(units["records"])} child Units first')
    if units['records']:
        del_payload = [{'Id': u['Id']} for u in units['records']]
        for i in range(0, len(del_payload), 200):
            batch = del_payload[i:i+200]
            unit_meta = units['records'][i:i+200]
            results = sf.bulk.Property_Unit__c.delete(batch)
            for r, u in zip(results, unit_meta):
                if r.get('success'):
                    log(u['Id'], u.get('Circuit_ID__c'), '(deleted)', '', 'Unit deleted', 'DELETE',
                        note='child of junk SFU PL "0"/"SFU"')
                else:
                    print(f"   FAIL Unit {u['Id']} - {r.get('errors', r)}")

    # Then delete the PLs
    print(f'  Deleting {len(junk_ids)} PLs')
    pl_payload = [{'Id': i} for i in junk_ids]
    results = sf.bulk.Property_Location__c.delete(pl_payload)
    for r, p in zip(results, res['records']):
        if r.get('success'):
            log(p['Id'], p['Name'], '(deleted)', '', 'PL deleted', 'DELETE',
                note=f'junk SFU PL with agreename={p["Agreement_Name__c"]!r}')
            print(f"  OK: deleted {p['Id']}  Name={p['Name']!r}")
        else:
            print(f"   FAIL PL {p['Id']} - {r.get('errors', r)}")

# ─── 2. Clear bogus AgreeName on 11 Bus PLs ───
print('\n[2/2] Clearing bogus Agreement_Name__c on bus PLs (PA01/PA05/PA07)...')
res = sf.query_all(
    "SELECT Id, Name, Agreement_Name__c FROM Property_Location__c "
    "WHERE Agreement_Name__c IN ('PA01', 'PA05', 'PA07')"
)
print(f'  Found {len(res["records"])} PLs')
if res['records']:
    payload = [{'Id': r['Id'], 'Agreement_Name__c': None} for r in res['records']]
    results = sf.bulk.Property_Location__c.update(payload)
    for r, p in zip(results, res['records']):
        if r.get('success'):
            log(p['Id'], p['Name'], 'Agreement_Name__c', p['Agreement_Name__c'], None,
                'CLEAR', note='bogus project-area code, not a real agreement')
            print(f"  OK: cleared {p['Name'][:50]:<50}  was {p['Agreement_Name__c']}")
        else:
            print(f"   FAIL {p['Id']} - {r.get('errors', r)}")

audit_path = AUDIT_DIR / f"cleanup_junk_pls_{TS.replace(':', '-')}.csv"
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before', 'After',
                                       'Source', 'Timestamp', 'Action', 'Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f'\nAudit log: {audit_path}  ({len(audit_rows)} rows)')
