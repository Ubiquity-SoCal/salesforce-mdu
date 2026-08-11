"""
Enforce the rule: a Signed_Date__c should exist ONLY for executed agreements.
Clear Signed_Date__c on IronClad-linked Agreement__c records that are NOT Completed
AND whose IronClad parent has NO Workflow Completed Date (i.e., never executed).

IronClad is authoritative (Koa, 2026-06-22). The wf_completed guard protects any
legitimately-executed-then-archived agreement (it would carry a Workflow Completed
Date) from being wrongly cleared. Generalizes the 2026-06-12 cancelled-only fix.

PREVIEW only by default. Run with --apply to write.
Audit: SalesForce/data/output/audit_logs/clear_signed_noncompleted_<TS>.csv
"""
import sys
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
SOURCE = "2026-06-22-clear-signed-date-noncompleted.py"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

recs = sf.query_all("""
    SELECT Id, Name, Status__c, Signed_Date__c,
           IronClad_Record__r.IronClad_Id__c,
           IronClad_Record__r.Workflow_Completed_Date__c,
           Opportunity__r.Name
    FROM Agreement__c
    WHERE IronClad_Record__c != null
      AND Signed_Date__c != null
      AND Status__c != 'Completed'
""")['records']

to_clear, skipped_executed = [], []
for r in recs:
    icr = r.get('IronClad_Record__r') or {}
    if icr.get('Workflow_Completed_Date__c'):
        skipped_executed.append(r)   # executed (likely archived) -> keep its signed date
    else:
        to_clear.append(r)

print(f"Non-Completed linked agreements with a signed date: {len(recs)}")
print(f"  -> WILL CLEAR (no Workflow Completed Date):  {len(to_clear)}")
print(f"  -> KEEP (has Workflow Completed Date):       {len(skipped_executed)}")
print(f"\nBy status (to clear): {dict(Counter(r.get('Status__c') for r in to_clear))}")
for r in to_clear:
    icr = r.get('IronClad_Record__r') or {}
    print(f"   {r['Name']:9} {str(r.get('Status__c')):10} signed={r.get('Signed_Date__c')} "
          f"IC={icr.get('IronClad_Id__c')}  {(r.get('Opportunity__r') or {}).get('Name','')[:32]}")
if skipped_executed:
    print("\nKept (executed but non-Completed status -- review separately):")
    for r in skipped_executed:
        icr = r.get('IronClad_Record__r') or {}
        print(f"   {r['Name']:9} {r.get('Status__c')} signed={r.get('Signed_Date__c')} "
              f"IC={icr.get('IronClad_Id__c')} wf_completed={icr.get('Workflow_Completed_Date__c')}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"clear_signed_noncompleted_{ts}.csv"
with open(audit, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(["Action", "SF_Id", "Name", "Field", "Before", "After", "Status", "Source", "Timestamp"])
    act = "UPDATE" if APPLY else "PREVIEW"
    for r in to_clear:
        w.writerow([act, r['Id'], r['Name'], "Signed_Date__c", r.get('Signed_Date__c'), "",
                    r.get('Status__c'), SOURCE, datetime.now().isoformat()])
print(f"\nAudit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to clear.")
    sys.exit(0)

import requests

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
url = f'{sf.base_url}composite/sobjects'
records = [{'attributes': {'type': 'Agreement__c'}, 'Id': r['Id'], 'Signed_Date__c': None} for r in to_clear]
ok = fail = 0
for i in range(0, len(records), 200):
    chunk = records[i:i+200]
    resp = requests.patch(url, headers=headers, json={'allOrNone': False, 'records': chunk}, timeout=120)
    if resp.status_code == 200:
        for res in resp.json():
            if res.get('success'):
                ok += 1
            else:
                fail += 1
                print(f"  ! {res.get('errors')}")
    else:
        fail += len(chunk)
        print(f"  ! HTTP {resp.status_code}: {resp.text[:300]}")
print(f"\nCleared Signed_Date__c: ok={ok} fail={fail}")
