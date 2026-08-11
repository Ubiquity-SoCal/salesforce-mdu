"""Add the two new handoff columns to the LIVE 'MDU Agreements Milestone Tracker'
report (00OWR00000KwMEL2A3) via the Analytics API (read-modify-write of detailColumns).

Why not redeploy the build script: the live report has been customized well beyond
2026-06-17 (Cat 1 filter, stage filter, Sub_Bucket exclusion, MDU/SFU record type).
A Metadata redeploy would clobber those. We only touch detailColumns, preserving
all filters/groupings/format.

Inserts, chronologically just before Design Phase Complete:
  Opportunity.ST_Design_Inputs_Received__c   (Design Inputs Received (A))
  Opportunity.ST_Ready_for_Engineering__c    (Ready for Engineering)
Idempotent: skips columns already present.
"""
import json
import requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])
RID = "00OWR00000KwMEL2A3"
hdr = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}
url = f"{sf.base_url}analytics/reports/{RID}"

NEW = ["Opportunity.ST_Design_Inputs_Received__c", "Opportunity.ST_Ready_for_Engineering__c"]
ANCHOR = "Opportunity.ST_Design_Phase_Complete__c"  # insert before this

rm = requests.get(f"{url}/describe", headers=hdr).json()["reportMetadata"]
cols = list(rm["detailColumns"])
print("before:", len(cols), "columns")

if all(c in cols for c in NEW):
    print("Both columns already present; nothing to do.")
    raise SystemExit(0)

# Remove any partial pre-existing, then insert as a block before the anchor.
cols = [c for c in cols if c not in NEW]
idx = cols.index(ANCHOR) if ANCHOR in cols else len(cols)
cols[idx:idx] = NEW
rm["detailColumns"] = cols
print("after: ", len(cols), "columns; inserted at index", idx)

r = requests.patch(url, headers=hdr, data=json.dumps({"reportMetadata": rm}))
print("PATCH ->", r.status_code)
if r.status_code not in (200, 201):
    print(r.text[:400])
    raise SystemExit("report PATCH failed")

# verify
rm2 = requests.get(f"{url}/describe", headers=hdr).json()["reportMetadata"]
cols2 = rm2["detailColumns"]
print("verify: total columns =", len(cols2))
for c in NEW:
    print(f"  {c}: {'present' if c in cols2 else 'MISSING'}")
print("filters preserved:", rm2.get("reportBooleanFilter"))
assert all(c in cols2 for c in NEW), "new columns missing after PATCH"
assert rm2.get("reportBooleanFilter") == rm.get("reportBooleanFilter"), "filter changed!"
print("OK: columns added, filters intact.")
