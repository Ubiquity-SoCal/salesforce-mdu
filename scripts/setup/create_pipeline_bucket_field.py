"""
Create Pipeline_Bucket__c picklist field on Opportunity.
Holds the raw CA MDU Agreement Status bucket values (distinct from Sales_Status__c
which is used for outreach state).
"""
import sys
from simple_salesforce import Salesforce

SF_USERNAME = "cass1@ubiquitygp.com"
SF_PASSWORD = "Hawaiian1984"
SF_TOKEN    = "IBSKT6CFUpSUJWxq1CMm0HkFC"

FIELD_API_NAME = "Pipeline_Bucket__c"
FIELD_LABEL    = "CA Pipeline Bucket"
VALUES = [
    "Prospects",
    "Proposal Sent",
    "On Net - Access Agreement Complete",
    "Near Net - Access Agreement Complete",
    "ON Air Serviceable",
]

def main():
    sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)

    # Check if already exists
    desc = sf.Opportunity.describe()
    existing = [f for f in desc["fields"] if f["name"] == FIELD_API_NAME]
    if existing:
        f = existing[0]
        print(f"[OK] {FIELD_API_NAME} already exists.")
        print(f"  Label: {f['label']}, Type: {f['type']}")
        if f.get("picklistValues"):
            active = [v["value"] for v in f["picklistValues"] if v.get("active")]
            print(f"  Current values: {active}")
            missing = [v for v in VALUES if v not in active]
            if missing:
                print(f"  [!] Missing picklist values: {missing}")
                print(f"      Extend manually via Setup > Object Manager > Opportunity > Fields > {FIELD_API_NAME}")
            else:
                print(f"  [OK] All required values present.")
        return

    # Create via Metadata API (Tooling API CustomField on StandardEntity)
    from simple_salesforce.exceptions import SalesforceMalformedRequest

    # Tooling API endpoint for CustomField creation on standard object
    # For standard objects we POST to /services/data/vXX.X/tooling/sobjects/CustomField
    picklist_metadata = {
        "FullName": f"Opportunity.{FIELD_API_NAME}",
        "Metadata": {
            "label": FIELD_LABEL,
            "type": "Picklist",
            "description": "Raw CA MDU Agreement Status bucket. Populated by ca_mdu_merge import. Separate from Sales_Status__c.",
            "inlineHelpText": "From CA MDU Agreement Status spreadsheet: Prospects / Proposal Sent / On Net AA Complete / Near Net AA Complete / ON Air Serviceable.",
            "valueSet": {
                "restricted": True,
                "valueSetDefinition": {
                    "sorted": False,
                    "value": [{"fullName": v, "default": False, "label": v} for v in VALUES],
                },
            },
        },
    }

    result = sf.toolingexecute("sobjects/CustomField", method="POST", data=picklist_metadata)
    print(f"[OK] Create response: {result}")

    if result.get("success"):
        print(f"\n[SUCCESS] {FIELD_API_NAME} created.")
        print(f"Values: {VALUES}")
        print(f"\nIMPORTANT: Field-Level Security not auto-set. Grant FLS for System Administrator + relevant profiles")
        print(f"  via Setup > Object Manager > Opportunity > Fields > {FIELD_API_NAME} > Set Field-Level Security.")
    else:
        print(f"[FAIL] {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
