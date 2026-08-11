"""
Create the missing SF Agreement for IC-1723 (4750 Lafayette Ave, Omaha).

Context: 2026-07-22 IronClad sync reverse-diff surfaced IC-1723 as a COMPLETED ROE
in IronClad with no backing Agreement__c, while its SF Opp ("4750 Lafayette Ave", MDU)
exists but sits at Prospects with zero agreements. This is a clean, no-judgment gap:
mirror the completed ROE into SF as an Agreement linked to the Opp + IronClad record.

Deliberately does NOT move the Opportunity stage -- MDU stage moves are Taylor's call.
The Opp will lag its completed ROE at Prospects; flag for a human to advance.

Idempotent: aborts if any Agreement already references IC-1723.
Preview by default; --apply to create. Audit: audit_logs/agr_create_ic1723_<ts>.csv
"""
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _c

_s = _c()
sf = Salesforce(username=_s["username"], password=_s["password"], security_token=_s["token"])
APPLY = "--apply" in sys.argv
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")

IC_ID = "IC-1723"
OPP_NAME = "4750 Lafayette Ave"

# --- Idempotency guard ---
existing = sf.query(
    f"SELECT Id, Name FROM Agreement__c "
    f"WHERE IronClad_ID__c='{IC_ID}' OR IronClad_Record__r.IronClad_Id__c='{IC_ID}'"
)["records"]
if existing:
    print(f"ABORT: {IC_ID} already has Agreement(s): {[e['Name'] for e in existing]}")
    sys.exit(0)

# --- Resolve Opp + IronClad record ---
opps = sf.query(
    f"SELECT Id, Name, StageName, RecordType.DeveloperName FROM Opportunity WHERE Name='{OPP_NAME}'"
)["records"]
if len(opps) != 1:
    print(f"ABORT: expected exactly 1 Opp named '{OPP_NAME}', found {len(opps)}")
    sys.exit(1)
opp = opps[0]

ic = sf.query(
    f"SELECT Id, IronClad_Id__c, Stage_IC__c, Contract_Status__c, Agreement_Date__c, "
    f"Effective_Date__c, Expiration_Date__c FROM IronClad__c WHERE IronClad_Id__c='{IC_ID}'"
)["records"][0]

# Signed date rule (matches refresh script): Completed -> Agreement Date, fallback Effective Date.
signed = ic.get("Agreement_Date__c") or ic.get("Effective_Date__c")

body = {
    "Opportunity__c": opp["Id"],
    "Agreement_Type__c": "ROE",
    "Status__c": "Completed",
    "Signed_Date__c": signed,
    "IronClad_ID__c": IC_ID,
    "IronClad_Record__c": ic["Id"],
    "IronClad_Stage__c": ic.get("Stage_IC__c"),
    "IronClad_Contract_Status__c": ic.get("Contract_Status__c"),
}
if ic.get("Expiration_Date__c"):
    body["Expiration_Date__c"] = ic["Expiration_Date__c"]

print(f"Opp:  {opp['Id']}  {opp['Name']}  [{(opp.get('RecordType') or {}).get('DeveloperName')}]  stage={opp['StageName']}")
print(f"IC:   {ic['Id']}  {IC_ID}  stage={ic.get('Stage_IC__c')}")
print("New Agreement body:")
for k, v in body.items():
    print(f"   {k}: {v}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"agr_create_ic1723_{ts}.csv"

if not APPLY:
    with open(audit, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Action", "New_Id", "Opportunity", "IronClad_ID", "Fields", "Timestamp"])
        w.writerow(["PREVIEW", "", opp["Id"], IC_ID, str(body), datetime.now().isoformat()])
    print(f"\nPREVIEW only. Audit: {audit}\nRe-run with --apply to create.")
    sys.exit(0)

res = sf.Agreement__c.create(body)
new_id = res.get("id")
print(f"\nCreated Agreement: {new_id}  (success={res.get('success')})")
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Action", "New_Id", "Opportunity", "IronClad_ID", "Fields", "Timestamp"])
    w.writerow(["CREATE", new_id, opp["Id"], IC_ID, str(body), datetime.now().isoformat()])
print(f"Audit (rollback = delete New_Id): {audit}")
