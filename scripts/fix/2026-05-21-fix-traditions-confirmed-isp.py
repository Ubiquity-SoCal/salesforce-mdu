"""
Stage 1 of ISP text-field retire: backfill the one Opp whose Confirmed_ISP text
value never made it into the multipicklist, so deleting the text field loses nothing.

The Traditions Apartments (006WR00000wkEbvYAE): Confirmed_ISP__c='Lumen', Confirmed_ISPs__c=null
-> set Confirmed_ISPs__c = 'Lumen / Quantum Fiber'
"""
import csv, datetime
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)
OPP_ID = "006WR00000wkEbvYAE"
TARGET = "Lumen / Quantum Fiber"

rec = sf.Opportunity.get(OPP_ID)
before = rec.get("Confirmed_ISPs__c")
text_val = rec.get("Confirmed_ISP__c")
print(f"{rec['Name']}: text={text_val!r}  picklist before={before!r}")

if before:
    print("Picklist already populated; aborting to avoid stomp.")
    raise SystemExit(0)

sf.Opportunity.update(OPP_ID, {"Confirmed_ISPs__c": TARGET})
after = sf.Opportunity.get(OPP_ID).get("Confirmed_ISPs__c")
print(f"picklist after={after!r}")
assert after == TARGET, "Update did not stick!"

# audit log
ts = datetime.datetime.now().isoformat()
log = "data/output/audit_logs/2026-05-21-isp-retire-data-fix.csv"
with open(log, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
    w.writerow([OPP_ID, rec["Name"], "Confirmed_ISPs__c", before, after,
                "ISP text-field retire (Confirmed_ISP__c=Lumen)", ts, "update"])
print(f"Logged -> {log}")
