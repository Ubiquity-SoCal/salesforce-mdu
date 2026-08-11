"""
Taylor Mauney's 2026-04-21 Salesforce revision requests.

Tasks handled here (metadata changes via Tooling API):
  1. Add inlineHelpText to RE_Assigned__c
  2. Add 8 missing values to Property_Type__c on MDU record type
  3a. Add inlineHelpText to Property_Address__c
  3b. Validation rule for City/State/Zip required on create (MDU RT)
  4. Add EMA + NEMA to Incumbent_Agreement_Type__c on MDU record type
  6. Add 5 values to Account.Type StandardValueSet

Task 5 (FlexiPage move) handled separately — requires sf CLI retrieve/deploy.
"""

import sys
import json
import requests
from simple_salesforce import Salesforce
import os as _os

# Salesforce config -- read from the gitignored SalesForce/api/ creds file.
# Never hardcode the password here: this file is tracked in git.
def _sf_creds():
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       "..", "..", "api", "Salesforce_Credentials.txt")
    _c = {}
    with open(_p) as _f:
        for _line in _f:
            if ":" in _line:
                _k, _v = _line.split(":", 1)
                _c[_k.strip()] = _v.strip()
    return _c


_SF = _sf_creds()
SF_USERNAME = _SF["Username"]
SF_PASSWORD = _SF["Password"]
SF_TOKEN = _SF["Security Token"]

DRY_RUN = "--dry-run" in sys.argv

MDU_RT_ID     = "012WR00000Ra0mkYAB"
BUSINESS_RT_ID = "012WR00000Ra0mjYAB"

RE_ASSIGNED_HELP = (
    "Only used for External Affairs team assignments (Tanya, Justin, or Rose). "
    "Do NOT put your own name here — leave blank unless an EA team member is working the property."
)

PROPERTY_ADDRESS_HELP = (
    "Type the full street address here AND also fill in the City, State, and Zip Code in their "
    "separate fields below. All four address fields are required for new properties."
)

# Full desired value list for Property_Type__c on MDU/Business RT
# (RecordType currently has no explicit picklistValues entry, so we need to define it fully
# — partial entries make SF drop the missing ones)
PROPERTY_TYPE_FULL = [
    "Apartments", "Condos", "Townhomes",
    "Private SFU Neighborhood", "Single Family Rental Homes",
    "Mixed Use", "Manufactured Homes / Mobile Homes",
    "Senior Living / Assisted Living",
    "Commercial / Business",
]

# Full desired value list for Incumbent_Agreement_Type__c
INCUMBENT_AT_FULL = ["Bulk", "EMA", "NEMA"]

ACCOUNT_TYPE_ADD = [
    "Management Company", "Law Firm", "Consulting Group", "Portfolio", "REIT",
]


def get_sf():
    return Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)


def tooling_base(sf):
    base = sf.base_url.rstrip('/').replace('/data/v59.0', '/data/v59.0/tooling')
    return base, {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}


def get_custom_field_id(sf, entity, field_dev_name):
    base, h = tooling_base(sf)
    r = requests.get(
        f"{base}/query/?q=SELECT+Id+FROM+CustomField+WHERE+TableEnumOrId%3D%27{entity}%27+AND+DeveloperName%3D%27{field_dev_name}%27",
        headers=h,
    )
    recs = r.json().get("records", [])
    return recs[0]["Id"] if recs else None


def patch_field_help_text(sf, entity, field_dev_name, help_text):
    """Update inlineHelpText on a custom field."""
    base, h = tooling_base(sf)
    field_id = get_custom_field_id(sf, entity, field_dev_name)
    if not field_id:
        print(f"  [FAIL] {entity}.{field_dev_name}__c not found")
        return False

    # Get current metadata
    r = requests.get(f"{base}/sobjects/CustomField/{field_id}", headers=h)
    current = r.json()
    meta = current["Metadata"]
    print(f"  {entity}.{field_dev_name}__c current help: {meta.get('inlineHelpText') or '(none)'}")

    meta["inlineHelpText"] = help_text

    if DRY_RUN:
        print(f"  [DRY] would set inlineHelpText to: {help_text[:80]}...")
        return True

    r = requests.patch(
        f"{base}/sobjects/CustomField/{field_id}",
        headers=h,
        data=json.dumps({"Metadata": meta}),
    )
    if r.status_code in (200, 204):
        print(f"  [OK] inlineHelpText set")
        return True
    else:
        print(f"  [FAIL] {r.status_code}: {r.text}")
        return False


def patch_record_type_picklist(sf, rt_id, rt_label, picklist_api_name, full_values):
    """Set the full picklist value list for a record type (replaces any existing)."""
    base, h = tooling_base(sf)

    r = requests.get(f"{base}/sobjects/RecordType/{rt_id}", headers=h)
    rt = r.json()
    meta = rt["Metadata"]

    # Find or create the picklist entry
    target = None
    for p in meta.get("picklistValues", []):
        if p["picklist"] == picklist_api_name:
            target = p
            break

    if not target:
        target = {"picklist": picklist_api_name, "values": []}
        meta.setdefault("picklistValues", []).append(target)

    existing_names = {v["valueName"] for v in target.get("values", [])}
    desired = set(full_values)
    print(f"  {rt_label} RT {picklist_api_name}: had {len(existing_names)} values, setting {len(desired)}")

    if existing_names == desired:
        print(f"  [SKIP] already aligned")
        return True

    target["values"] = [{"valueName": v, "default": False} for v in full_values]

    if DRY_RUN:
        print(f"  [DRY] would set values to: {full_values}")
        return True

    r = requests.patch(
        f"{base}/sobjects/RecordType/{rt_id}",
        headers=h,
        data=json.dumps({"Metadata": meta}),
    )
    if r.status_code in (200, 204):
        print(f"  [OK] values set")
        return True
    else:
        print(f"  [FAIL] {r.status_code}: {r.text}")
        return False


def patch_standard_value_set(sf, value_set_master_label, values_to_add):
    """Add values to a StandardValueSet (e.g. AccountType)."""
    base, h = tooling_base(sf)

    r = requests.get(
        f"{base}/query/?q=SELECT+Id,Metadata+FROM+StandardValueSet+WHERE+MasterLabel%3D%27{value_set_master_label}%27",
        headers=h,
    )
    recs = r.json().get("records", [])
    if not recs:
        print(f"  [FAIL] StandardValueSet {value_set_master_label} not found")
        return False

    rec = recs[0]
    svs_id = rec["Id"]
    meta = rec["Metadata"]
    existing = {v["valueName"] for v in meta.get("standardValue", [])}
    missing = [v for v in values_to_add if v not in existing]

    print(f"  {value_set_master_label}: has {len(existing)} values, missing: {missing}")
    if not missing:
        return True

    for v in missing:
        meta["standardValue"].append({"valueName": v, "label": v, "default": False, "isActive": True})

    if DRY_RUN:
        print(f"  [DRY] would add {len(missing)} values to {value_set_master_label}")
        return True

    r = requests.patch(
        f"{base}/sobjects/StandardValueSet/{svs_id}",
        headers=h,
        data=json.dumps({"Metadata": meta}),
    )
    if r.status_code in (200, 204):
        print(f"  [OK] added {len(missing)} values to {value_set_master_label}")
        return True
    else:
        print(f"  [FAIL] {r.status_code}: {r.text}")
        return False


def create_validation_rule(sf, entity, rule_dev_name, active, error_msg, error_field, condition):
    """Create a ValidationRule via Tooling API."""
    base, h = tooling_base(sf)

    # Check if exists
    r = requests.get(
        f"{base}/query/?q=SELECT+Id+FROM+ValidationRule+WHERE+EntityDefinition.QualifiedApiName%3D%27{entity}%27+AND+ValidationName%3D%27{rule_dev_name}%27",
        headers=h,
    )
    recs = r.json().get("records", [])
    if recs:
        print(f"  [SKIP] Validation rule {rule_dev_name} already exists: {recs[0]['Id']}")
        return True

    # Create
    payload = {
        "FullName": f"{entity}.{rule_dev_name}",
        "Metadata": {
            "active": active,
            "description": "Require Property City, State, Zip on new MDU Opportunity creation (Taylor request 2026-04-21).",
            "errorConditionFormula": condition,
            "errorMessage": error_msg,
            "errorDisplayField": error_field,
        },
    }
    if DRY_RUN:
        print(f"  [DRY] would create validation rule {rule_dev_name}")
        print(f"        formula: {condition}")
        return True

    r = requests.post(
        f"{base}/sobjects/ValidationRule",
        headers=h,
        data=json.dumps(payload),
    )
    if r.status_code in (200, 201):
        print(f"  [OK] created validation rule: {r.json().get('id')}")
        return True
    else:
        print(f"  [FAIL] {r.status_code}: {r.text}")
        return False


def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print(f"=== Taylor Revisions 2026-04-21 [{mode}] ===\n")

    sf = get_sf()

    print("Task 1 — RE_Assigned__c inlineHelpText")
    patch_field_help_text(sf, "Opportunity", "RE_Assigned", RE_ASSIGNED_HELP)
    print()

    print("Task 2 — Property_Type__c picklist values on MDU + Business RT")
    patch_record_type_picklist(sf, MDU_RT_ID, "MDU", "Property_Type__c", PROPERTY_TYPE_FULL)
    patch_record_type_picklist(sf, BUSINESS_RT_ID, "Business", "Property_Type__c", PROPERTY_TYPE_FULL)
    print()

    print("Task 3a — Property_Address__c inlineHelpText")
    patch_field_help_text(sf, "Opportunity", "Property_Address", PROPERTY_ADDRESS_HELP)
    print()

    print("Task 3b — Validation rule: City/State/Zip required on new MDU Opp")
    create_validation_rule(
        sf, "Opportunity",
        "Require_City_State_Zip_On_New_MDU",
        active=True,
        error_msg="City, State, and Zip Code are required for new MDU opportunities. Please fill in all three address fields.",
        error_field="Property_City__c",
        condition=(
            "AND("
            "RecordType.DeveloperName = 'MDU',"
            "OR(ISNEW(), ISCHANGED(Property_Address__c)),"
            "OR(ISBLANK(Property_City__c), ISBLANK(Property_State__c), ISBLANK(Property_Zip__c))"
            ")"
        ),
    )
    print()

    print("Task 4 — Incumbent_Agreement_Type__c — set full list on MDU + Business RT")
    patch_record_type_picklist(sf, MDU_RT_ID, "MDU", "Incumbent_Agreement_Type__c", INCUMBENT_AT_FULL)
    patch_record_type_picklist(sf, BUSINESS_RT_ID, "Business", "Incumbent_Agreement_Type__c", INCUMBENT_AT_FULL)
    print()

    print("Task 6 — Account.Type StandardValueSet (add 5 values)")
    patch_standard_value_set(sf, "AccountType", ACCOUNT_TYPE_ADD)
    print()

    print(f"\n=== Done [{mode}] ===")


if __name__ == "__main__":
    main()
