"""
The report was created with scope='user' (Salesforce default = "My opportunities"),
so it returned 21 rows instead of the full org. Patch scope to 'organization' and make
the filters editable on the run page so Niraj can flip state/category without cloning.

Then VERIFY: independently compute the expected row count from SOQL and compare to what
the report actually returns. Rows != opps, because an Opportunity with N contacts
produces N rows (outer join => opps with 0 contacts still produce 1 row).
"""
import sys
import io
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

REPORT_ID = "00OWR00000Lpbiz2AB"
sf = Salesforce(*creds())

# ---- patch ---------------------------------------------------------------
desc = sf.restful(f"analytics/reports/{REPORT_ID}/describe", method="GET")
rm = dict(desc["reportMetadata"])
rm["scope"] = "organization"
for f in rm.get("reportFilters", []):
    f["isRunPageEditable"] = True

sf.restful(f"analytics/reports/{REPORT_ID}", method="PATCH", json={"reportMetadata": rm})
print("PATCHED scope -> organization, filters -> run-page editable")

# ---- independent expectation from SOQL -----------------------------------
opps = sf.query_all(
    "SELECT Id FROM Opportunity "
    "WHERE Property_State__c IN ('NE','TX') "
    "AND (Property_Category__c = null OR Property_Category__c NOT IN ('Cat 2','Cat 3'))"
)["records"]
opp_ids = {o["Id"] for o in opps}

links = sf.query_all(
    "SELECT Opportunity__c FROM Opportunity_Contact__c WHERE Opportunity__c != null"
)["records"]
per_opp = defaultdict(int)
for r in links:
    if r["Opportunity__c"] in opp_ids:
        per_opp[r["Opportunity__c"]] += 1

expected_rows = sum(max(1, per_opp.get(i, 0)) for i in opp_ids)
print(f"\nSOQL expectation:")
print(f"  Opportunities passing filter : {len(opp_ids)}")
print(f"  ...of those with >=1 contact : {len(per_opp)}")
print(f"  expected report rows         : {expected_rows}")

# ---- what the report actually returns ------------------------------------
run = sf.restful(f"analytics/reports/{REPORT_ID}?includeDetails=false", method="GET")
actual = run["factMap"]["T!T"]["aggregates"][-1]["value"]
print(f"\nReport actually returns        : {actual} rows")
print("  scope now:", run["reportMetadata"]["scope"])

if actual == expected_rows:
    print("\nPASS - report row count matches the independently computed SOQL count.")
else:
    print(f"\nMISMATCH - off by {actual - expected_rows}. Investigate before sending.")
