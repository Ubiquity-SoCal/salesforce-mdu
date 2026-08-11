"""Remove Property_Address/City/State/Zip from Business_Opportunity_Record_Page.

Business Opps use Property_Location__c/Property_Unit__c. These 4 fields are
always blank on Business records and shouldn't show on the page.
"""
import sys
import json
import requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


DRY = "--dry-run" in sys.argv

FLEX_ID = "0M0WR0000004IKv0AM"  # Business_Opportunity_Record_Page
TARGETS = {"Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"}


def main():
    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )
    base = sf.base_url.rstrip('/').replace('/data/v59.0', '/data/v59.0/tooling')
    h = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}

    r = requests.get(f"{base}/sobjects/FlexiPage/{FLEX_ID}", headers=h).json()
    fmeta = r["Metadata"]

    removed = []
    for region in fmeta.get("flexiPageRegions") or []:
        before = region.get("itemInstances") or []
        kept = []
        for item in before:
            fi = item.get("fieldInstance")
            if fi:
                api = (fi.get("fieldItem") or "").split(".", 1)[-1]
                if api in TARGETS:
                    removed.append((region.get("name"), api))
                    continue
            kept.append(item)
        region["itemInstances"] = kept

    print(f"Fields to remove from Business FlexiPage: {len(removed)}")
    for region_name, api in removed:
        print(f"  {region_name}: {api}")

    if not removed:
        print("[SKIP] nothing to remove")
        return

    if DRY:
        print("[DRY] would PATCH FlexiPage")
        return

    resp = requests.patch(f"{base}/sobjects/FlexiPage/{FLEX_ID}",
                           headers=h, data=json.dumps({"Metadata": fmeta}))
    if resp.status_code not in (200, 204):
        print(f"[FAIL] {resp.status_code} {resp.text}")
        sys.exit(1)
    print(f"[OK] removed {len(removed)} fields from Business FlexiPage")


if __name__ == "__main__":
    main()
