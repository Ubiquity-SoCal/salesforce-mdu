"""
Link Agreements that have IronClad_ID__c (string) populated but no IronClad_Record__c lookup
to their matching IronClad__c parent record (matched by IronClad_Id__c == Agreement.IronClad_ID__c).

PREVIEW only by default. Run with --apply to write.

Audit: SalesForce/audit_logs/orphan_ironclad_link_<TS>.csv
"""
import sys
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

orphans = sf.query_all("""
    SELECT Id, Name, Agreement_Type__c, Status__c, IronClad_ID__c,
           Opportunity__r.RecordType.DeveloperName, Opportunity__r.Name
    FROM Agreement__c
    WHERE IronClad_ID__c != null AND IronClad_Record__c = null
""")['records']
print(f"Orphan Agreements (IronClad_ID__c set, no Record link): {len(orphans)}")

ic_ids = {a.get('IronClad_ID__c') for a in orphans if a.get('IronClad_ID__c')}
ids_str = "','".join(ic_ids)
ic_records = sf.query_all(
    f"SELECT Id, IronClad_Id__c, Agreement__c FROM IronClad__c WHERE IronClad_Id__c IN ('{ids_str}')"
)['records']
ic_by_id = {r['IronClad_Id__c']: r for r in ic_records}
print(f"IronClad__c parents found: {len(ic_records)}")

to_link = []     # (agr, ic) pairs to link safely
already_linked_other = []  # IC parent linked to different Agreement
no_parent = []   # IC ID has no parent in SF
rt_counts = Counter()

for a in orphans:
    ic_id = a.get('IronClad_ID__c')
    rt = (a.get('Opportunity__r') or {}).get('RecordType', {}).get('DeveloperName', '?')
    if ic_id not in ic_by_id:
        no_parent.append(a)
        continue
    ic = ic_by_id[ic_id]
    if ic.get('Agreement__c') and ic['Agreement__c'] != a['Id']:
        already_linked_other.append((a, ic))
        continue
    to_link.append((a, ic))
    rt_counts[rt] += 1

print(f"\nWill link:                    {len(to_link)}  (by RT: {dict(rt_counts)})")
print(f"Conflict (parent linked elsewhere): {len(already_linked_other)}")
print(f"No IronClad__c parent in SF:  {len(no_parent)}  (IDs: {[a.get('IronClad_ID__c') for a in no_parent]})")

# Audit
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"orphan_ironclad_link_{ts}.csv"
with open(audit, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(["Action", "SF_Id", "Agreement_Name", "IronClad_ID", "IronClad_Record_Id", "Conflict_Agreement", "Source", "Timestamp"])
    action = "UPDATE" if APPLY else "PREVIEW"
    for a, ic in to_link:
        w.writerow([action, a['Id'], a['Name'], a['IronClad_ID__c'], ic['Id'], '', 'link_orphan_ironclad_agreements.py', datetime.now().isoformat()])
    for a, ic in already_linked_other:
        w.writerow(['CONFLICT', a['Id'], a['Name'], a['IronClad_ID__c'], ic['Id'], ic.get('Agreement__c'), 'link_orphan_ironclad_agreements.py', datetime.now().isoformat()])
    for a in no_parent:
        w.writerow(['NO_PARENT', a['Id'], a['Name'], a.get('IronClad_ID__c'), '', '', 'link_orphan_ironclad_agreements.py', datetime.now().isoformat()])
print(f"\nAudit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to write.")
    sys.exit(0)

# Apply via composite API
import requests

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
url = f'{sf.base_url}composite/sobjects'
records = [{'attributes': {'type': 'Agreement__c'}, 'Id': a['Id'], 'IronClad_Record__c': ic['Id']} for a, ic in to_link]
ok = fail = 0
for i in range(0, len(records), 200):
    chunk = records[i:i+200]
    r = requests.patch(url, headers=headers, json={'allOrNone': False, 'records': chunk}, timeout=120)
    if r.status_code == 200:
        for res in r.json():
            if res.get('success'):
                ok += 1
            else:
                fail += 1
                print(f"  ! {res.get('errors')}")
    else:
        fail += len(chunk)
        print(f"  ! HTTP {r.status_code}: {r.text[:200]}")
print(f"\nLinked: ok={ok} fail={fail}")
