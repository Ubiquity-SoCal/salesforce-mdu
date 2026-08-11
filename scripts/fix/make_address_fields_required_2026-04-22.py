"""Make Property_Address/City/State/Zip required on MDU Opportunity only.

Steps:
  1. Fill Quail Gardens blank city/zip (the 1 remaining blank City on MDU).
  2. Tighten validation rule Require_City_State_Zip_On_New_MDU to also fire when
     any of City/State/Zip is cleared on an existing MDU record.
  3. Set fieldInstance uiBehavior = 'Required' on the 4 fields in MDU FlexiPage
     (MDU_Opportunity_Record_Page). Business page untouched, CustomField.required
     stays false so Business Opps (which use Property_Location__c and leave these
     blank by design) are unaffected.

Flags:
  --dry-run   preview only
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

FLEX_ID = "0M0WR0000004IKw0AM"  # MDU_Opportunity_Record_Page
QUAIL_GARDENS_ID = "006WR00000ywTThYAM"
TARGETS = {"Property_Address__c", "Property_City__c", "Property_State__c", "Property_Zip__c"}

NEW_FORMULA = (
    "AND("
    "RecordType.DeveloperName = 'MDU',"
    "OR("
    "AND(ISNEW(), OR(ISBLANK(Property_City__c), ISBLANK(Property_State__c), ISBLANK(Property_Zip__c))),"
    "AND(ISCHANGED(Property_City__c),  ISBLANK(Property_City__c)),"
    "AND(ISCHANGED(Property_State__c), ISBLANK(Property_State__c)),"
    "AND(ISCHANGED(Property_Zip__c),   ISBLANK(Property_Zip__c))"
    ")"
    ")"
)


def main():
    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )
    base = sf.base_url.rstrip('/').replace('/data/v59.0', '/data/v59.0/tooling')
    h = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}

    # --- Step 1 ---
    print("=" * 60)
    print("Step 1: Backfill Quail Gardens (Encinitas, CA 92024)")
    print("=" * 60)
    if DRY:
        print("  [DRY] would set city=Encinitas, zip=92024")
    else:
        sf.Opportunity.update(QUAIL_GARDENS_ID,
                              {"Property_City__c": "Encinitas", "Property_Zip__c": "92024"})
        print("  [OK] Quail Gardens filled")

    # --- Step 2 ---
    print("\n" + "=" * 60)
    print("Step 2: Update validation rule Require_City_State_Zip_On_New_MDU")
    print("=" * 60)
    r = requests.get(
        f"{base}/query/?q=" + requests.utils.quote(
            "SELECT Id, Metadata FROM ValidationRule "
            "WHERE EntityDefinition.QualifiedApiName='Opportunity' "
            "AND ValidationName='Require_City_State_Zip_On_New_MDU'"
        ),
        headers=h,
    ).json()
    if not r.get("records"):
        print("  [FAIL] rule not found")
        sys.exit(1)
    vr_id = r["records"][0]["Id"]
    meta = r["records"][0]["Metadata"]
    print(f"  Old formula: {meta.get('errorConditionFormula')}")
    print(f"  New formula: {NEW_FORMULA}")
    meta["errorConditionFormula"] = NEW_FORMULA
    meta["errorMessage"] = ("City, State, and Zip are required for MDU opportunities. "
                             "These fields cannot be left blank or cleared once set.")
    if DRY:
        print("  [DRY] would PATCH validation rule")
    else:
        resp = requests.patch(f"{base}/sobjects/ValidationRule/{vr_id}",
                               headers=h, data=json.dumps({"Metadata": meta}))
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] {resp.status_code} {resp.text}")
            sys.exit(1)
        print("  [OK] validation rule updated")

    # --- Step 3 ---
    print("\n" + "=" * 60)
    print("Step 3: uiBehavior=Required on 4 fields in MDU FlexiPage")
    print("=" * 60)
    r = requests.get(f"{base}/sobjects/FlexiPage/{FLEX_ID}", headers=h).json()
    fmeta = r["Metadata"]

    changes = []
    for region in fmeta.get("flexiPageRegions") or []:
        for item in region.get("itemInstances") or []:
            fi = item.get("fieldInstance")
            if not fi:
                continue
            ref = fi.get("fieldItem") or ""
            api = ref.split(".", 1)[-1] if "." in ref else ref
            if api not in TARGETS:
                continue
            props = fi.setdefault("fieldInstanceProperties", []) or []
            ui = next((p for p in props if p.get("name") == "uiBehavior"), None)
            if ui:
                prev = ui.get("value")
                if (prev or "").lower() == "required":
                    print(f"  [SKIP] {api}: already required")
                    continue
                ui["value"] = "required"
                changes.append((api, prev))
            else:
                props.append({"name": "uiBehavior", "value": "required"})
                fi["fieldInstanceProperties"] = props
                changes.append((api, None))

    for api, prev in changes:
        print(f"  {api}: {prev!r} -> 'Required'")
    print(f"  Total changes: {len(changes)}")

    if not changes:
        print("  [SKIP] nothing to patch")
    elif DRY:
        print("  [DRY] would PATCH FlexiPage")
    else:
        resp = requests.patch(f"{base}/sobjects/FlexiPage/{FLEX_ID}",
                               headers=h, data=json.dumps({"Metadata": fmeta}))
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] {resp.status_code} {resp.text}")
            sys.exit(1)
        print("  [OK] FlexiPage updated")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
