"""
Stage 2 of ISP text-field retire: repoint Agreement_Niraj_Notifications flow from
the legacy text field Confirmed_ISP__c to the multipicklist Confirmed_ISPs__c.

Creates a NEW flow version (Draft) with the swap, then activates it via FlowDefinition.
Leaves old versions in place (deleted in a later, verified step).
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
base = sf.base_url  # .../services/data/vXX.0/
tq = lambda q: requests.get(f"{base}tooling/query/?q=" + requests.utils.quote(q), headers=hdr).json()

DEFN = "Agreement_Niraj_Notifications"

# current versions
versions = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
              f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
print("Existing versions:")
for v in versions:
    print(f"  v{v['VersionNumber']} {v['Status']} {v['Id']}")
active = [v for v in versions if v["Status"] == "Active"][0]
next_ver = max(v["VersionNumber"] for v in versions) + 1

# active version metadata
meta = tq(f"SELECT Metadata FROM Flow WHERE Id='{active['Id']}'")["records"][0]["Metadata"]

# swap legacy -> picklist (Confirmed_ISP__c is NOT a substring of Confirmed_ISPs__c, safe)
raw = json.dumps(meta)
n = raw.count("Confirmed_ISP__c")
raw = raw.replace("Confirmed_ISP__c", "Confirmed_ISPs__c")
meta2 = json.loads(raw)
print(f"\nReplaced {n} occurrences of Confirmed_ISP__c -> Confirmed_ISPs__c")

# dedupe queriedFields (the swap can duplicate Confirmed_ISPs__c)
for rl in (meta2.get("recordLookups") or []):
    qf = rl.get("queriedFields")
    if qf:
        seen, deduped = set(), []
        for f in qf:
            if f not in seen:
                seen.add(f); deduped.append(f)
        rl["queriedFields"] = deduped
        if rl.get("name") == "get_opportunity":
            print(f"  get_opportunity queriedFields now: {deduped}")

meta2["status"] = "Draft"  # create inactive, activate via FlowDefinition

# create new version
resp = requests.post(f"{base}tooling/sobjects/Flow", headers=hdr,
                     data=json.dumps({"FullName": DEFN, "Metadata": meta2}))
print(f"\nCreate v{next_ver}: {resp.status_code} {resp.text[:300]}")
if resp.status_code not in (200, 201):
    raise SystemExit("Flow version create failed.")

# activate via FlowDefinition
defn = tq(f"SELECT Id FROM FlowDefinition WHERE DeveloperName='{DEFN}'")["records"][0]
act = requests.patch(f"{base}tooling/sobjects/FlowDefinition/{defn['Id']}", headers=hdr,
                     data=json.dumps({"Metadata": {"activeVersionNumber": next_ver}}))
print(f"Activate v{next_ver}: {act.status_code} {act.text[:200]}")

# verify
after = tq(f"SELECT Id, VersionNumber, Status FROM Flow "
           f"WHERE Definition.DeveloperName='{DEFN}' ORDER BY VersionNumber")["records"]
print("\nVersions after:")
for v in after:
    print(f"  v{v['VersionNumber']} {v['Status']} {v['Id']}")
new_active = [v for v in after if v["Status"] == "Active"]
if new_active:
    chk = tq(f"SELECT Metadata FROM Flow WHERE Id='{new_active[0]['Id']}'")["records"][0]["Metadata"]
    blob = json.dumps(chk)
    print(f"\nActive v{new_active[0]['VersionNumber']}: "
          f"Confirmed_ISP__c={blob.count('Confirmed_ISP__c')}  "
          f"Confirmed_ISPs__c={blob.count('Confirmed_ISPs__c')}")
