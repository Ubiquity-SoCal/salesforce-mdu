"""
Build & deploy two PAL/ROE data-cleanup reports into MDU Sales Reports, to be
surfaced on the "MDU/SFU PALs/ROEs" dashboard so Taylor can work the gaps.

Report A  PALROE_Not_Linked_SiteTracker  (Opportunities with Agreements)
    Signed PAL/ROE (or Opp stage >= PAL/ROE Complete) but NO SiteTracker link
    (Opportunity.ST_Build_Status__c blank). Fix = link it.
    Both parameters visible: Signed Date + Overall Project Status (Stage).

Report B  PALROE_Complete_No_Agreement   (Opportunities)
    Opp stage >= PAL/ROE Complete but Agreement_Count__c = 0 (no agreement
    record at all). Fix = create/attach the agreement.

Additive + re-runnable (overwrites the same two reports). Mirrors
2026-05-21-build-signed-pals-report.py.
"""
import os, requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
FOLDER="MDU_Sales_Reports"
BEYOND_STAGES = "PAL/ROE Complete,Marketing/Bulk In Progress,Marketing/Bulk Complete"

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


def cols_xml(cols):
    return "\n    ".join(f"<columns><field>{c}</field></columns>" for c in cols)


# ---------------------------------------------------------------------------
# Report A: Not Linked to SiteTracker  (agreement grain)
# Filter: 1 AND 2 AND (3 OR 4) AND (5 OR (6 AND 7))
#   1 RecordType = MDU
#   2 ST Build Status = blank  (not linked to SiteTracker)
#   3 Signed Date != blank        }  union: signed-paper OR stage-complete
#   4 Stage IN (>= PAL/ROE Complete)
#   5 Agreement Type = PAL        }  dedup: a both-sites property counts once as PAL
#   6 Agreement Type = ROE
#   7 Signed PAL Date Count = 0
# Groupings: Stage > Agreement Type (so the union logic is visible)
# ---------------------------------------------------------------------------
A_API = "PALROE_Not_Linked_SiteTracker"
A_cols = [
    "OPPORTUNITY_NAME",
    "ACCOUNT_NAME",
    "Opportunity.Property_Address__c",
    "Opportunity.Property_State__c",
    "Opportunity.Property_Category__c",
    "Opportunity.MDU_Categorization__c",
    "Opportunity.HOA__c",                   # so HOAs (mostly CA) can be filtered out
    "Agreement__c.Signed_Date__c",          # parameter 1: signed date
    "Opportunity.ST_Build_Status__c",       # blank = the reason it's on this list
    "Opportunity.Units__c",
    "Agreement__c.Status__c",
    "Agreement__c.Sync_Source__c",
    "Agreement__c.IronClad_ID__c",
]
A_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>PALs/ROEs - Not Linked to SiteTracker</name>
    <description>CLEANUP: signed PAL/ROE (or Opp stage PAL/ROE Complete+) with NO SiteTracker link (ST Build Status blank). Grouped by Stage then Agreement Type. Fix = link the SiteTracker project.</description>
    <reportType>OpportunityCustomEntity$Agreement__c</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>STAGE_NAME</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>Agreement__c.Agreement_Type__c</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <timeFrameFilter>
        <dateColumn>CLOSE_DATE</dateColumn>
        <interval>INTERVAL_CUSTOM</interval>
    </timeFrameFilter>
    {cols_xml(A_cols)}
    <filter>
        <booleanFilter>1 AND 2 AND ((3 AND 8) OR 4) AND (5 OR (6 AND 7))</booleanFilter>
        <criteriaItems>
            <column>RECORDTYPE</column>
            <operator>equals</operator>
            <value>Opportunity.MDU</value>
        </criteriaItems>
        <criteriaItems>
            <column>Opportunity.ST_Build_Status__c</column>
            <operator>equals</operator>
            <value></value>
        </criteriaItems>
        <criteriaItems>
            <column>Agreement__c.Signed_Date__c</column>
            <operator>notEqual</operator>
            <value></value>
        </criteriaItems>
        <criteriaItems>
            <column>STAGE_NAME</column>
            <operator>equals</operator>
            <value>{BEYOND_STAGES}</value>
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
        <criteriaItems>
            <column>Agreement__c.Status__c</column>
            <operator>equals</operator>
            <value>Completed,Cancelled</value>
        </criteriaItems>
    </filter>
</Report>"""

# ---------------------------------------------------------------------------
# Report B: PAL/ROE Complete, No Agreement  (opportunity grain)
# Filter: 1 AND 2 AND 3
#   1 RecordType = MDU
#   2 Stage IN (>= PAL/ROE Complete)
#   3 Agreement_Count__c = 0
# Grouping: State (work by region)
# ---------------------------------------------------------------------------
B_API = "PALROE_Complete_No_Agreement"
B_cols = [
    "OPPORTUNITY_NAME",
    "ACCOUNT_NAME",
    "Opportunity.Property_Address__c",
    "Opportunity.Property_Category__c",
    "Opportunity.HOA__c",                   # so HOAs (mostly CA) can be filtered out
    "STAGE_NAME",                           # parameter: stage (all PAL/ROE Complete+)
    "Opportunity.Agreement_Count__c",       # parameter: 0 = the reason it's on this list
    "Opportunity.ST_Build_Status__c",       # surfaces the "built but no paper" ones
    "Opportunity.Units__c",
    "FULL_NAME",                            # opportunity owner
]
B_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>MDU/SFU PAL/ROE Complete - No Agreement</name>
    <description>CLEANUP: Opps at stage PAL/ROE Complete or beyond with NO agreement record (Agreement Count = 0). Some are already SiteTracker-linked (built but no paper recorded). Fix = create/attach the PAL/ROE agreement.</description>
    <reportType>Opportunity</reportType>
    <format>Summary</format>
    <scope>organization</scope>
    <groupingsDown>
        <dateGranularity>None</dateGranularity>
        <field>Opportunity.Property_State__c</field>
        <sortOrder>Asc</sortOrder>
    </groupingsDown>
    <timeFrameFilter>
        <dateColumn>CLOSE_DATE</dateColumn>
        <interval>INTERVAL_CUSTOM</interval>
    </timeFrameFilter>
    {cols_xml(B_cols)}
    <filter>
        <booleanFilter>1 AND 2 AND 3</booleanFilter>
        <criteriaItems>
            <column>RECORDTYPE</column>
            <operator>equals</operator>
            <value>Opportunity.MDU</value>
        </criteriaItems>
        <criteriaItems>
            <column>STAGE_NAME</column>
            <operator>equals</operator>
            <value>{BEYOND_STAGES}</value>
        </criteriaItems>
        <criteriaItems>
            <column>Opportunity.Agreement_Count__c</column>
            <operator>equals</operator>
            <value>0</value>
        </criteriaItems>
    </filter>
</Report>"""

pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>{FOLDER}/{A_API}</members><members>{FOLDER}/{B_API}</members><name>Report</name></types>
    <version>{V}</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg)
    zf.writestr(f"reports/{FOLDER}/{A_API}.report", A_xml)
    zf.writestr(f"reports/{FOLDER}/{B_API}.report", B_xml)

ok = metadata_deploy(buf.getvalue(), "cleanup-reports")
print("\nReports deploy:", "OK" if ok else "FAILED")
if ok:
    print(f"  A: MDU Sales Reports > MDU/SFU PALs/ROEs - Not Linked to SiteTracker  ({A_API})")
    print(f"  B: MDU Sales Reports > MDU/SFU PAL/ROE Complete - No Agreement       ({B_API})")
