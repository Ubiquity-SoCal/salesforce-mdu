"""
Support the combined Signed PALs & MDU ROEs report.
Adds:
  - Agreement__c.Is_Signed_PAL__c  (formula checkbox: Type=PAL AND Signed_Date populated)
  - Opportunity.Signed_PAL_Date_Count__c (roll-up COUNT of Is_Signed_PAL__c=true)
Used by report filter logic so ROE rows are excluded on sites that have a signed PAL.
Aligned to the report's "signed = has a Signed Date" definition. Additive, no data touched.
"""
import requests, json, time, base64, io, zipfile
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
sf = Salesforce(username=USER, password=PW, security_token=TOK)


def deploy(files, members_types, label):
    """files: dict path->content ; members_types: list of (member,type)"""
    types_xml = "".join(f"<types><members>{m}</members><name>{t}</name></types>" for m, t in members_types)
    pkg = f'<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">{types_xml}<version>{V}</version></Package>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg)
        for path, content in files.items():
            zf.writestr(path, content)
    url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
    b64 = base64.b64encode(buf.getvalue()).decode()
    body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
    bnd = "----B"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
               f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
               f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
    r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json()["id"]
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


AGR_HDR = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label><pluralLabel>Agreements</pluralLabel>
    <nameField><label>Agreement Number</label><displayFormat>AGR-{0000}</displayFormat><type>AutoNumber</type></nameField>
    <sharingModel>ControlledByParent</sharingModel><deploymentStatus>Deployed</deploymentStatus>
    <fields>
        <fullName>Is_Signed_PAL__c</fullName>
        <label>Is Signed PAL</label>
        <type>Checkbox</type>
        <formula>ISPICKVAL(Agreement_Type__c, "PAL") &amp;&amp; NOT(ISBLANK(Signed_Date__c))</formula>
        <description>Signed PALs report: true when a PAL has a Signed Date. Drives the Opportunity signed-PAL rollup.</description>
    </fields>
</CustomObject>"""

# Step 1: Agreement formula field
if "Is_Signed_PAL__c" in [f["name"] for f in sf.Agreement__c.describe()["fields"]]:
    print("Is_Signed_PAL__c exists; skip")
else:
    if not deploy({"objects/Agreement__c.object": AGR_HDR}, [("Agreement__c", "CustomObject")], "agr-bool"):
        raise SystemExit(1)

# Step 2: Opportunity rollup (references the formula field, so deploy after it exists)
OPP = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Signed_PAL_Date_Count__c</fullName>
        <label>Signed PAL Count (by Date)</label>
        <summaryForeignKey>Agreement__c.Opportunity__c</summaryForeignKey>
        <summaryOperation>count</summaryOperation>
        <summaryFilterItems>
            <field>Agreement__c.Is_Signed_PAL__c</field>
            <operation>equals</operation>
            <value>True</value>
        </summaryFilterItems>
        <type>Summary</type>
        <description>Count of signed PALs (by Signed Date) on this Opportunity. Used to exclude ROE rows on sites that already have a signed PAL.</description>
    </fields>
</CustomObject>"""
if "Signed_PAL_Date_Count__c" in [f["name"] for f in sf.Opportunity.describe()["fields"]]:
    print("Signed_PAL_Date_Count__c exists; skip")
else:
    if not deploy({"objects/Opportunity.object": OPP}, [("Opportunity", "CustomObject")], "opp-rollup"):
        raise SystemExit(1)
    # FLS read for Admin (rollup is read-only)
    prof = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions><editable>false</editable><field>Opportunity.Signed_PAL_Date_Count__c</field><readable>true</readable></fieldPermissions>
</Profile>"""
    deploy({"profiles/Admin.profile": prof}, [("Admin", "Profile")], "fls")

# verify rollup populates correctly
sf2 = Salesforce(username=USER, password=PW, security_token=TOK)
def c(q): return sf2.query(q)["records"][0]["c"]
print("\nVerification:")
print("  Opps Signed_PAL_Date_Count>0:", c("SELECT COUNT(Id) c FROM Opportunity WHERE Signed_PAL_Date_Count__c>0"), "(expect 358)")
print("  signed-PAL-by-date sites missed:", c("SELECT COUNT(Id) c FROM Opportunity WHERE Id IN (SELECT Opportunity__c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null) AND (Signed_PAL_Date_Count__c=0 OR Signed_PAL_Date_Count__c=null)"), "(expect 0)")
