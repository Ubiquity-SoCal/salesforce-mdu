"""
Item 1 (one-time backfill): copy expiration dates that already live on the linked
IronClad__c record down onto Agreement__c.Expiration_Date__c, so the Agreements
related list on the Opportunity can show each agreement's expiration.

Source: Agreement__c.IronClad_Record__r.Expiration_Date__c (set by import_ironclad_data.py).
Target: Agreement__c.Expiration_Date__c.
Rule:   IronClad is authoritative. Set where IC has a date and the Agreement differs.
        Never clear (a blank IC value leaves the Agreement value alone).

Snapshots before/after to the audit log (rollback) BEFORE writing. Preview, then --apply.
Go-forward is handled separately by patching the recurring IronClad refresh sync.

Run: python 2026-06-15-backfill-agreement-expiration-from-ironclad.py [--apply]
"""
import sys
import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]

LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
SOURCE = "2026-06-15-backfill-agreement-expiration-from-ironclad.py"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

recs = sf.query_all("""
    SELECT Id, Name, Agreement_Type__c, Status__c, Expiration_Date__c,
           IronClad_Record__r.Expiration_Date__c
    FROM Agreement__c
    WHERE IronClad_Record__r.Expiration_Date__c != null
""")["records"]
print(f"Agreements with an IronClad expiration available: {len(recs)}")

diffs = []
for r in recs:
    ic = (r.get("IronClad_Record__r") or {}).get("Expiration_Date__c")
    cur = r.get("Expiration_Date__c")
    if ic and cur != ic:
        diffs.append({"id": r["Id"], "name": r["Name"], "type": r["Agreement_Type__c"],
                      "from": cur, "to": ic})

already = len(recs) - len(diffs)
print(f"Already aligned (no change):                      {already}")
print(f"To set / update Expiration_Date__c:               {len(diffs)}")

print("\nSample (first 15):")
for d in diffs[:15]:
    print(f"  {d['name']:<10} {str(d['type']):<6} {str(d['from']):<12} -> {d['to']}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"backfill_agreement_expiration_{ts}.csv"
action = "UPDATE" if APPLY else "PREVIEW"
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SF_Id", "Agreement_Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
    for d in diffs:
        w.writerow([d["id"], d["name"], "Expiration_Date__c", d["from"] or "", d["to"],
                    SOURCE, action, datetime.now().isoformat()])
print(f"\nAudit (rollback record): {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to write.")
    sys.exit(0)

ok = fail = 0
for d in diffs:
    try:
        sf.Agreement__c.update(d["id"], {"Expiration_Date__c": d["to"]})
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  ! {d['name']}: {e}")
print(f"\nUpdated: ok={ok} fail={fail}")

# Verify
n = sf.query("SELECT COUNT() FROM Agreement__c WHERE Expiration_Date__c != null")["totalSize"]
print(f"Agreement__c with Expiration_Date__c populated now: {n}")
