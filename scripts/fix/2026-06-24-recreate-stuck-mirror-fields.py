"""Remediate two SiteTracker_Project__c fields that the Metadata API created in a
half-baked state today (2026-06-24 15:34 UTC): the CustomField metadata rows exist
(Tooling shows them, name is reserved) but they never became queryable — describe
+ SOQL return "No such column" at v59 and v63. The matching Opportunity fields from
the same deploy propagated fine; only the custom-object fields stuck.

Fix: delete the stuck CustomField rows via Tooling, recreate cleanly via Tooling
(concrete per-field success), verify queryable. Fields are brand-new + empty, so
delete is safe (no data loss).
"""
import time
import requests
from simple_salesforce import Salesforce

sf = Salesforce(username="cass1@ubiquitygp.com", password="Hawaiian1984",
                security_token="IBSKT6CFUpSUJWxq1CMm0HkFC")
inst = f"https://{sf.sf_instance}"
hdr = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}
tool = f"{inst}/services/data/v59.0/tooling/sobjects/CustomField"

DEFS = [
    ("SiteTracker_Project__c.Desktop_Design_Inputs_A__c",
     {"label": "Desktop Design Inputs and Floor Plan (A)", "type": "Date"}),
    ("SiteTracker_Project__c.Ready_for_Engineering__c",
     {"label": "Ready for Engineering?", "type": "Checkbox", "defaultValue": False}),
]
DEVNAMES = ["Desktop_Design_Inputs_A", "Ready_for_Engineering"]


def stuck_ids():
    q = ("SELECT Id, DeveloperName FROM CustomField WHERE DeveloperName IN ('%s')"
         % "','".join(DEVNAMES))
    return {r["DeveloperName"]: r["Id"]
            for r in sf.restful("tooling/query", params={"q": q})["records"]}


# 1. delete stuck rows
ids = stuck_ids()
print("Stuck CustomField rows:", ids)
for dev, cid in ids.items():
    r = requests.delete(f"{tool}/{cid}", headers=hdr)
    print(f"  DELETE {dev} ({cid}) -> {r.status_code} {r.text[:120]}")

# wait for delete to settle
for _ in range(6):
    time.sleep(5)
    if not stuck_ids():
        break
print("Remaining stuck rows after delete:", stuck_ids())

# 2. recreate cleanly
for full, meta in DEFS:
    r = requests.post(tool, headers=hdr, json={"FullName": full, "Metadata": meta})
    print(f"  CREATE {full.split('.')[1]:32} -> {r.status_code} {r.text[:160]}")

# 3. verify queryable (retry for propagation)
ok = False
for attempt in range(12):
    time.sleep(10)
    try:
        sf.query("SELECT Id, Desktop_Design_Inputs_A__c, Ready_for_Engineering__c "
                 "FROM SiteTracker_Project__c LIMIT 1")
        ok = True
        print(f"  queryable after ~{(attempt + 1) * 10}s")
        break
    except Exception as e:
        print(f"  attempt {attempt + 1}: not yet ({str(e)[:60]})")
print("RESULT:", "OK — both mirror fields queryable" if ok else "STILL STUCK — escalate")
