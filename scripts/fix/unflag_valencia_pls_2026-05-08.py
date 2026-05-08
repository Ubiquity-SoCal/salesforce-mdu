"""One-shot remediation for the 3 Valencia DR PLs that hit DUPLICATE_VALUE during
the 2026-05-08 sync. The script's case-sensitive BBA index missed mixed-case
Vetro -> SF matches, causing these to:
  (1) be flagged Import_Delete=True (in step E) -- wrong, they're real records
  (2) be re-attempted as new (step A) -- failed with DUPLICATE_VALUE

Fix:
  - Clear Import_Delete_Property__c flag and note
  - Uppercase Business_Base_Address__c + Name so future syncs match
  - Also populate Address_Type__c = 'Business' (this got skipped for these 3)
"""
import sys, io, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984',
                security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
TS = datetime.now().isoformat(timespec='seconds')
SCRIPT = 'unflag_valencia_pls_2026-05-08.py'
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

ids = ['a01WR00000UGWxTYAX', 'a01WR00000UGWvcYAH', 'a01WR00000UGWvaYAH']
quoted = "','".join(ids)

print("Before state:")
res = sf.query_all(
    f"SELECT Id, Name, Business_Base_Address__c, Address_Type__c, "
    f"Import_Delete_Property__c, Import_Delete_Note__c, State__c "
    f"FROM Property_Location__c WHERE Id IN ('{quoted}')"
)
before = {r['Id']: r for r in res['records']}
for r in res['records']:
    print(f"  {r['Id']}  bba={r['Business_Base_Address__c']!r}  type={r.get('Address_Type__c')}  stale={r['Import_Delete_Property__c']}")

# Build update payload: uppercase BBA/Name, clear stale flag, set type
updates = []
for r in res['records']:
    bba_upper = (r['Business_Base_Address__c'] or '').strip().upper()
    updates.append({
        'Id': r['Id'],
        'Business_Base_Address__c': bba_upper,
        'Name': bba_upper[:80],
        'Address_Type__c': 'Business',
        'Import_Delete_Property__c': False,
        'Import_Delete_Note__c': None,
    })

print(f"\nApplying {len(updates)} updates...")
result = sf.bulk.Property_Location__c.update(updates)
audit_rows = []
for r, u in zip(result, updates):
    if r.get('success'):
        b = before[u['Id']]
        for fld, after in u.items():
            if fld == 'Id': continue
            old = b.get(fld)
            audit_rows.append({
                'SF_Id': u['Id'], 'Name': u['Name'], 'Field': fld,
                'Before': old, 'After': after,
                'Source': SCRIPT, 'Timestamp': TS, 'Action': 'FIX_CASING_REMEDIATION',
                'Note': 'Remediating 2026-05-08 sync casing bug'
            })
        print(f"  OK: {u['Id']} -> {u['Business_Base_Address__c']}")
    else:
        print(f"  FAIL: {u['Id']} - {r.get('errors', r)}")

audit_path = AUDIT_DIR / f"unflag_valencia_{TS.replace(':', '-')}.csv"
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before', 'After',
                                       'Source', 'Timestamp', 'Action', 'Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\nAudit log: {audit_path}")
