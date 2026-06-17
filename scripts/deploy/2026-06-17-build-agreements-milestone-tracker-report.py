"""Builds the 'MDU Agreements Milestone Tracker' report: tabular, Opportunity report
type, one row per MDU opp with a signed PAL or ROE. Columns = Sales POC (Owner),
property, units, address, state, SiteTracker project #, stage, ST build status, and
the five per-type signed-date milestones. Validates check-only first, then deploys."""
from _md_deploy import connect, deploy

sf = connect()
FOLDER = "MDU_Sales_Reports"
API = "MDU_Agreements_Milestone_Tracker"

# Column dev-name tokens. Custom Opp fields are reliable as Opportunity.<API>.
# Standard columns: OPPORTUNITY_NAME, STAGE_NAME, and the Owner token.
OWNER_COL = "FULL_NAME"   # verified token for "Opportunity Owner" (Sales POC)
COLUMNS = [
    OWNER_COL,                              # Sales POC
    "OPPORTUNITY_NAME",                     # Property
    "Opportunity.Units__c",                 # Total Units
    "Opportunity.Property_Address__c",      # Address
    "Opportunity.Property_State__c",        # State
    "Opportunity.ST_Project_Number__c",     # SiteTracker project # (P-XXXXXX)
    "STAGE_NAME",                           # Stage
    "Opportunity.Sub_Bucket__c",            # Stage Status (Sub_Bucket__c formula)
    "Opportunity.PAL_Signed_Date__c",
    "Opportunity.ROE_Signed_Date__c",
    "Opportunity.EMA_Signed_Date__c",
    "Opportunity.Bulk_Signed_Date__c",
    "Opportunity.PAL_Addendum_Signed_Date__c",
]
cols_xml = "".join(f"<columns><field>{c}</field></columns>" for c in COLUMNS)

DESC = ("MDU opportunities with a signed PAL or ROE. One row per property; agreement "
        "milestones (PAL/ROE/EMA/Bulk/PAL Addendum signed dates) as columns. "
        "Signed = Status Completed/Cancelled + Signed Date. All time.")

REPORT = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>MDU Agreements Milestone Tracker</name>
    <description>{DESC}</description>
    <reportType>Opportunity</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown><dateGranularity>None</dateGranularity><field>Opportunity.ST_Build_Status__c</field><sortOrder>Asc</sortOrder></groupingsDown>
    {cols_xml}
    <timeFrameFilter><dateColumn>CLOSE_DATE</dateColumn><interval>INTERVAL_CUSTOM</interval></timeFrameFilter>
    <filter>
        <booleanFilter>1 AND (2 OR 3)</booleanFilter>
        <criteriaItems><column>RECORDTYPE</column><operator>equals</operator><value>Opportunity.MDU</value></criteriaItems>
        <criteriaItems><column>Opportunity.PAL_Signed_Date__c</column><operator>notEqual</operator><value></value></criteriaItems>
        <criteriaItems><column>Opportunity.ROE_Signed_Date__c</column><operator>notEqual</operator><value></value></criteriaItems>
    </filter>
</Report>"""

files = {f"reports/{FOLDER}/{API}.report": REPORT}
members = [(f"{FOLDER}/{API}", "Report")]

# Validate first (check-only). If the OWNER column token is rejected, the failure
# names it — switch OWNER_COL to "FULL_NAME" and re-run.
print("Check-only validation...")
if not deploy(sf, files, members, "report-check", check_only=True):
    raise SystemExit("Validation failed — fix the column token above and re-run.")
print("Validation OK. Deploying for real...")
if not deploy(sf, files, members, "report-deploy"):
    raise SystemExit(1)
print("Report deployed.")
