"""
Create Niraj's report natively in Salesforce via the Analytics REST API.

Why the API and not Report metadata XML: the Metadata API rejects the column tokens
that /analytics/reportTypes advertises for a custom report type. The Analytics API
takes the advertised names verbatim, and lets us run the report immediately to verify
row counts instead of trusting the deploy.

Report type MDU_Opportunities_with_Contacts__c was deployed separately
(deploys/2026-07-09-niraj-opp-contact-report/).

Filter rationale (see scripts/_probes/2026-07-09-cat1-onnet-filter-cost.py):
  Property_State__c IN (NE, TX)          -- Koa's scope
  Property_Category__c NOT IN (Cat 2/3)  -- NOT "= Cat 1". Category is blank on 50.7%
                                            of NE/TX Closed Lost; an "= Cat 1" filter
                                            silently drops 278 of 548 closed-lost opps,
                                            the exact population Niraj wants to review.

Usage:
    python 2026-07-09-create-niraj-opp-contact-report.py            # dry run: print payload + preview
    python 2026-07-09-create-niraj-opp-contact-report.py --create   # actually create
"""
import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

REPORT_TYPE = "MDU_Opportunities_with_Contacts__c"
FOLDER_ID = "00lWR000005rBnFYAU"  # MDU Sales Reports
DEV_NAME = "NE_TX_Opportunity_Contacts_Ownership"
LABEL = "NE TX Opportunity Contacts and Ownership"

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
    "Opportunity_Contact__c.Contact__c.Name",
    "Opportunity_Contact__c.Role__c",
    "Opportunity_Contact__c.Contact__c.Account.Name",
    "Opportunity_Contact__c.Contact__c.Title",
    "Opportunity_Contact__c.Contact__c.Phone",
    "Opportunity_Contact__c.Contact__c.Email",
]

FILTERS = [
    {"column": "Opportunity.Property_State__c", "operator": "equals", "value": "NE,TX"},
    {"column": "Opportunity.Property_Category__c", "operator": "notEqual", "value": "Cat 2,Cat 3"},
]

payload = {
    "reportMetadata": {
        "name": LABEL,
        "developerName": DEV_NAME,
        "reportType": {"type": REPORT_TYPE},
        "reportFormat": "TABULAR",
        "folderId": FOLDER_ID,
        "detailColumns": COLUMNS,
        "reportFilters": FILTERS,
        "reportBooleanFilter": "1 AND 2",
        "sortBy": [{"sortColumn": "Opportunity.Property_State__c", "sortOrder": "Asc"}],
        "currency": None,
    }
}

sf = Salesforce(*creds())

if "--create" not in sys.argv:
    print("DRY RUN. Payload:")
    print(json.dumps(payload, indent=2)[:1400])
    print("\n... pass --create to create the report.")
    sys.exit(0)

res = sf.restful("analytics/reports", method="POST", json=payload)
rid = res["reportMetadata"]["id"]
print(f"CREATED report {rid}  ({LABEL})")
print(f"  URL: {sf.base_url.split('/services')[0]}/lightning/r/Report/{rid}/view")

# ---- verify by running it ------------------------------------------------
run = sf.restful(f"analytics/reports/{rid}?includeDetails=true", method="GET")
fact = run["factMap"]["T!T"]
rows = fact["rows"]
print(f"\nVERIFY: report returns {len(rows)} detail rows "
      f"(API caps preview at 2000; grand total below is authoritative)")
print("  grand total rowCount:", run["factMap"]["T!T"]["aggregates"][-1]["value"])
print("  filters applied:", [(f["column"], f["operator"], f["value"])
                             for f in run["reportMetadata"]["reportFilters"]])
