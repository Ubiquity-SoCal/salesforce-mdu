"""
Stage 2b: after the repointed flow version is active, delete the obsolete flow
versions that still reference Confirmed_ISP__c (they block field deletion).
Only deletes inactive versions that still reference the legacy field.
"""
import json, requests
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)
hdr = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}
base = sf.base_url
tq = lambda q: requests.get(f"{base}tooling/query/?q=" + requests.utils.quote(q), headers=hdr).json()

DEFN = "Agreement_Niraj_Notifications"
versions = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
              f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
print("Versions:")
for v in versions:
    meta = tq(f"SELECT Metadata FROM Flow WHERE Id='{v['Id']}'")["records"][0]["Metadata"]
    refs = json.dumps(meta).count("Confirmed_ISP__c")
    print(f"  v{v['VersionNumber']} {v['Status']:<9} {v['Id']}  legacy_refs={refs}")
    v["_refs"] = refs

active = [v for v in versions if v["Status"] == "Active"]
assert active and active[0]["_refs"] == 0, "Active version must exist and be clean before deleting old ones!"
print(f"\nActive v{active[0]['VersionNumber']} is clean (0 legacy refs). Safe to delete old versions.")

for v in versions:
    if v["Status"] != "Active" and v["_refs"] > 0:
        d = requests.delete(f"{base}tooling/sobjects/Flow/{v['Id']}", headers=hdr)
        print(f"  delete v{v['VersionNumber']} ({v['Id']}): {d.status_code}")

# confirm
after = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
           f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
print("\nRemaining versions:")
for v in after:
    print(f"  v{v['VersionNumber']} {v['Status']} {v['Id']}")
