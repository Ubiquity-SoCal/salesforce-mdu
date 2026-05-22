"""
Build & deploy the "Signed PALs" report (tabular) on the Opportunities with
Agreements report type, into the MDU Sales Reports folder.

Columns mirror the requester's Excel + the IronClad sync provenance.
Filters: Agreement Type = PAL, Signed Date not blank.
Additive (creates a new report). Re-runnable (overwrites the same report).
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="MDU_Sales_Reports"; REPORT_API="Signed_PALs"
if os.environ.get("SF_SESSION_ID"):
    sf = Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL", INSTANCE), session_id=os.environ["SF_SESSION_ID"])
else:
    sf = Salesforce(username=USER, password=PW, security_token=TOK)


def metadata_deploy(zip_bytes, label):
    url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
    b64 = base64.b64encode(zip_bytes).decode()
    body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
    bnd = "----DeployBoundary"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n"
               f"{json.dumps(body)}\r\n--{bnd}\r\n"
               f"Content-Disposition: form-data; name=\"file\"; filename=\"deploy.zip\"\r\n"
               f"Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
    h = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}
    r = requests.post(url, headers=h, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json().get("id")
    for i in range(40):
        time.sleep(3)
        res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
        st = res.get("deployResult", {}).get("status", "?")
        print(f"  [{label}] poll {i+1}: {st}")
        if st == "Succeeded": return True
        if st in ("Failed", "Canceled", "SucceededPartial"):
            for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
                if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    return False


# Column tokens: standard Opp fields use legacy tokens; custom fields use Object.Api__c
columns = [
    "OPPORTUNITY_NAME",                 # Name
    "STAGE_NAME",                       # Overall Project Status
    "Opportunity.Units__c",             # Units
    "Opportunity.Property_Address__c",  # Address
    "Opportunity.Property_Category__c", # Category
    "Opportunity.MDU_Categorization__c",# MDU Categorization (OnNet/OffNet/NearNet) - needs populating
    "Opportunity.Build_Type__c",        # Build Type
    "Opportunity.Prospective_ISPs__c",  # Prospective ISP(s)
    "Opportunity.Confirmed_ISPs__c",    # Confirmed ISP(s)
    "Opportunity.Property_State__c",    # State
    "Opportunity.Sub_Bucket__c",        # Status (pursuit / stage status)
    "Agreement__c.Signed_Date__c",      # PAL/ROE Signed Date
    "Opportunity.ST_Activation_Actual__c",  # Activation Date (SiteTracker)
    "Agreement__c.Status__c",           # Agreement Status (Agreement Type is the grouping)
    "Agreement__c.Sync_Source__c",      # Synced?
    "Agreement__c.IronClad_ID__c",      # IronClad ID
]
cols_xml = "\n    ".join(f"<columns><field>{c}</field></columns>" for c in columns)

report_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>MDU/SFU PALs/ROEs</name>
    <description>MDU; signed PALs + MDU ROEs (site with both = PAL); all time. Grouped by Agreement Type then SiteTracker Build Status.</description>
    <reportType>OpportunityCustomEntity$Agreement__c</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>Agreement__c.Agreement_Type__c</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>Opportunity.ST_Build_Status__c</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <timeFrameFilter>
        <dateColumn>CLOSE_DATE</dateColumn>
        <interval>INTERVAL_CUSTOM</interval>
    </timeFrameFilter>
    {cols_xml}
    <filter>
        <booleanFilter>1 AND 2 AND (3 OR (4 AND 5))</booleanFilter>
        <criteriaItems>
            <column>RECORDTYPE</column>
            <operator>equals</operator>
            <value>Opportunity.MDU</value>
        </criteriaItems>
        <criteriaItems>
            <column>Agreement__c.Signed_Date__c</column>
            <operator>notEqual</operator>
            <value></value>
        </criteriaItems>
        <criteriaItems>
            <column>Agreement__c.Agreement_Type__c</column>
            <operator>equals</operator>
            <value>PAL</value>
        </criteriaItems>
        <criteriaItems>
            <column>Agreement__c.Agreement_Type__c</column>
            <operator>equals</operator>
            <value>ROE</value>
        </criteriaItems>
        <criteriaItems>
            <column>Opportunity.Signed_PAL_Date_Count__c</column>
            <operator>equals</operator>
            <value>0</value>
        </criteriaItems>
    </filter>
</Report>"""

pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>{FOLDER}/{REPORT_API}</members><name>Report</name></types>
    <version>{V}</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr(f"reports/{FOLDER}/{REPORT_API}.report", report_xml)

ok = metadata_deploy(buf.getvalue(), "report")
print("\nReport deploy:", "OK" if ok else "FAILED")
if ok:
    print(f"Location: MDU Sales Reports > Signed PALs")
