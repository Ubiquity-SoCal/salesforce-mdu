"""
Activate the clean (legacy-ref-free) flow version via FlowDefinition, then verify.
"""
import json, requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)
hdr = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}
base = sf.base_url
tq = lambda q: requests.get(f"{base}tooling/query/?q=" + requests.utils.quote(q), headers=hdr).json()

DEFN = "Agreement_Niraj_Notifications"
versions = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
              f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
# pick the highest-numbered version that has 0 legacy refs
clean = None
for v in versions:
    meta = tq(f"SELECT Metadata FROM Flow WHERE Id='{v['Id']}'")["records"][0]["Metadata"]
    if json.dumps(meta).count("Confirmed_ISP__c") == 0:
        clean = v
assert clean, "No clean version found!"
print(f"Activating clean v{clean['VersionNumber']} ({clean['Id']})")

defn = tq(f"SELECT Id FROM FlowDefinition WHERE DeveloperName='{DEFN}'")["records"][0]
act = requests.patch(f"{base}tooling/sobjects/FlowDefinition/{defn['Id']}", headers=hdr,
                     data=json.dumps({"Metadata": {"activeVersionNumber": clean["VersionNumber"]}}))
print(f"Activate: {act.status_code} {act.text[:200]}")

after = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
           f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
print("Versions now:")
for v in after:
    print(f"  v{v['VersionNumber']} {v['Status']} {v['Id']}")
