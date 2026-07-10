"""
Create the ONE ROW PER PROPERTY version of Niraj's report.

Uses report type MDU_Opportunities_Primary_Contact (base Opportunity, no join), so there is
no contact fan-out. Shows the single highest-priority contact plus Contact Count.

Verifies: row count must equal the Opportunity count for the same filter (1,067), not the
1,345 rows the fan-out report returns.

Usage: python 2026-07-09-create-niraj-one-line-report.py --create
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

FOLDER_ID = "00lWR000005rBnFYAU"  # MDU Sales Reports
DEV_NAME = "NE_TX_Opportunity_Primary_Contact"
LABEL = "NE TX Opportunities Primary Contact"  # Salesforce caps report names at 40 chars

COLUMNS = [
    "Opportunity.Name",
    "Opportunity.Property_Address__c",
    "Opportunity.Property_City__c",
    "Opportunity.Property_State__c",
    "Opportunity.StageName",
    "Opportunity.Loss_Reason__c",
    "Opportunity.Units__c",
    "Opportunity.Property_Category__c",
    "Opportunity.MDU_Categorization__c",
    "Opportunity.Owner.Name",
    "Opportunity.Originator__c.Name",
    "Opportunity.RE_Assigned__c.Name",
    "Opportunity.Contact_Count__c",
    "Opportunity.Primary_Contact__c.Name",
    "Opportunity.Primary_Contact_Role__c",
    "Opportunity.Primary_Contact__c.Account.Name",
    "Opportunity.Primary_Contact__c.Title",
    "Opportunity.Primary_Contact__c.Phone",
    "Opportunity.Primary_Contact__c.Email",
]

FILTERS = [
    {"column": "Opportunity.Property_State__c", "operator": "equals",
     "value": "NE,TX", "isRunPageEditable": True},
    {"column": "Opportunity.Property_Category__c", "operator": "notEqual",
     "value": "Cat 2,Cat 3", "isRunPageEditable": True},
]

payload = {
    "reportMetadata": {
        "name": LABEL,
        "developerName": DEV_NAME,
        "reportType": {"type": "MDU_Opportunities_Primary_Contact__c"},
        "reportFormat": "TABULAR",
        "folderId": FOLDER_ID,
        "scope": "organization",
        "detailColumns": COLUMNS,
        "reportFilters": FILTERS,
        "reportBooleanFilter": "1 AND 2",
        "sortBy": [{"sortColumn": "Opportunity.Property_State__c", "sortOrder": "Asc"}],
    }
}

sf = Salesforce(*creds())

if "--create" not in sys.argv:
    print("DRY RUN. pass --create.")
    sys.exit(0)

res = sf.restful("analytics/reports", method="POST", json=payload)
rid = res["reportMetadata"]["id"]
inst = sf.base_url.split("/services")[0].replace(".my.salesforce.com", ".lightning.force.com")
print(f"CREATED {rid}  {LABEL}")
print(f"  {inst}/lightning/r/Report/{rid}/view")

# ---- verify ---------------------------------------------------------------
run = sf.restful(f"analytics/reports/{rid}?includeDetails=false", method="GET")
rows = run["factMap"]["T!T"]["aggregates"][-1]["value"]
print(f"\n  scope: {run['reportMetadata']['scope']}")
print(f"  report rows: {rows}")

expected = sf.query(
    "SELECT COUNT(Id) c FROM Opportunity WHERE Property_State__c IN ('NE','TX') "
    "AND (Property_Category__c = null OR Property_Category__c NOT IN ('Cat 2','Cat 3'))"
)["records"][0]["c"]
print(f"  expected (SOQL opportunity count): {expected}")
print("\nPASS - one row per opportunity." if rows == expected
      else f"\nMISMATCH: off by {rows - expected}")

# how many rows actually show a contact
withc = sf.query(
    "SELECT COUNT(Id) c FROM Opportunity WHERE Property_State__c IN ('NE','TX') "
    "AND (Property_Category__c = null OR Property_Category__c NOT IN ('Cat 2','Cat 3')) "
    "AND Primary_Contact__c != null"
)["records"][0]["c"]
print(f"\n  rows WITH a primary contact : {withc}")
print(f"  rows with NO contact at all  : {expected - withc}")
