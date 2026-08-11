"""
One-off remediation (2026-06-12): clear Signed_Date__c on 4 Cancelled ROE
agreements that the IronClad refresh backfilled a signed date onto today.

Per Koa: a ROE cancelled out of an unsigned stage (Sign/Review) was never
actually executed, so it should not carry a signed/completed date. The export's
"Agreement Date" (used as the signed-date source) is just the doc date, not proof
of execution, for these.

Snapshots current values to the audit log BEFORE clearing (rollback). Read the
preview, then re-run with --apply.

NOTE: the recurring refresh (refresh_agreements_from_ironclad_export_*.py) will
re-stamp these next run unless its signed-date logic is changed to only stamp
Completed (not Cancelled). This script only fixes the current state.

Run: python 2026-06-12-clear-signed-date-cancelled-roes.py [--apply]
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

TARGETS = ["AGR-1467", "AGR-1458", "AGR-1460", "AGR-1464"]

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

names = "','".join(TARGETS)
recs = sf.query_all(
    f"SELECT Id, Name, Status__c, Signed_Date__c FROM Agreement__c WHERE Name IN ('{names}')"
)["records"]
print(f"Targets found: {len(recs)}")

to_clear = []
for r in recs:
    print(f"  {r['Name']:<10} {str(r['Status__c']):<10} signed={r['Signed_Date__c']}")
    if r.get("Signed_Date__c"):
        to_clear.append(r)

print(f"\nWill clear Signed_Date__c on: {len(to_clear)}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"clear_signed_date_cancelled_roes_{ts}.csv"
action = "UPDATE" if APPLY else "PREVIEW"
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SF_Id", "Agreement_Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
    for r in to_clear:
        w.writerow([r["Id"], r["Name"], "Signed_Date__c", r["Signed_Date__c"], "",
                    "2026-06-12-clear-signed-date-cancelled-roes.py", action, datetime.now().isoformat()])
print(f"Audit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to clear.")
    sys.exit(0)

ok = fail = 0
for r in to_clear:
    try:
        sf.Agreement__c.update(r["Id"], {"Signed_Date__c": None})
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  ! {r['Name']}: {e}")
print(f"\nCleared: ok={ok} fail={fail}")

# Verify
recs2 = sf.query_all(
    f"SELECT Name, Status__c, Signed_Date__c FROM Agreement__c WHERE Name IN ('{names}')"
)["records"]
print("\nPost-clear state:")
for r in sorted(recs2, key=lambda x: x["Name"]):
    print(f"  {r['Name']:<10} {str(r['Status__c']):<10} signed={r['Signed_Date__c']}")
