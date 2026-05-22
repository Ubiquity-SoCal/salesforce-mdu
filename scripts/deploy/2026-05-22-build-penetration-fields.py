"""
Stage 1 of the Business Penetration dashboard build: add two NON-DESTRUCTIVE
formula fields to Property_Location__c. Existing Priority__c is left untouched.

  Penetration__c           Percent = Active/Total*100 (per-building penetration)
  Penetration_Priority__c  Text, mirrors Priority__c BUT moves the deactivated
                           check ahead of the single-unit branch, so churned
                           single-suite buildings land in Category 1 (lit) instead
                           of Category 3. lit = Category 1 + All Active.

Grants FLS (read) to the System Administrator profile (new fields need explicit FLS).
Then verifies: prints old Priority__c vs new Penetration_Priority__c distribution
for business (non-stale) to confirm the ONLY movement is single-churned Cat3 -> Cat1.

Deploys via Metadata REST deployRequest (same mechanism as the PAL/ROE build).
"""
import requests, json, time, base64, io, zipfile
from collections import Counter
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
INSTANCE="https://fun-power-747.my.salesforce.com"; V="59.0"
sf = Salesforce(username=USER, password=PW, security_token=TOK)

# Percent type multiplies the formula result by 100 for display, so the formula
# must return the raw ratio (0-1), NOT *100.
PEN_FORMULA = ("IF(Property_Unit_Count__c &gt; 0, "
               "Active_Unit_Count__c / Property_Unit_Count__c, 0)")
PRIO_FORMULA = ('IF(Hold__c = TRUE, "Hold", '
                'IF(Property_Unit_Count__c = 0, "", '
                'IF(Active_Unit_Count__c = Property_Unit_Count__c, "All Active", '
                'IF(OR(Active_Unit_Count__c &gt; 0, Deactive_Unit_Count__c &gt; 0), "Category 1", '
                'IF(Property_Unit_Count__c = 1, "Category 3", "Category 2")))))')

OBJECT_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Penetration__c</fullName>
        <externalId>false</externalId>
        <formula>{PEN_FORMULA}</formula>
        <formulaTreatBlanksAs>BlankAsZero</formulaTreatBlanksAs>
        <label>Penetration</label>
        <precision>5</precision>
        <required>false</required>
        <scale>1</scale>
        <type>Percent</type>
        <description>Active_Unit_Count / Property_Unit_Count, as a percent. Door-level penetration for a building.</description>
    </fields>
    <fields>
        <fullName>Penetration_Priority__c</fullName>
        <externalId>false</externalId>
        <formula>{PRIO_FORMULA}</formula>
        <formulaTreatBlanksAs>BlankAsZero</formulaTreatBlanksAs>
        <label>Penetration Priority</label>
        <required>false</required>
        <type>Text</type>
        <unique>false</unique>
        <description>Lit-corrected Priority: deactivated check precedes single-unit branch so churned single-suite buildings are Category 1, not Category 3. lit = Category 1 + All Active.</description>
    </fields>
</CustomObject>"""

PROFILE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions>
        <editable>false</editable>
        <field>Property_Location__c.Penetration__c</field>
        <readable>true</readable>
    </fieldPermissions>
    <fieldPermissions>
        <editable>false</editable>
        <field>Property_Location__c.Penetration_Priority__c</field>
        <readable>true</readable>
    </fieldPermissions>
</Profile>"""

PKG = (f'<?xml version="1.0" encoding="UTF-8"?>'
       f'<Package xmlns="http://soap.sforce.com/2006/04/metadata">'
       f'<types><members>Property_Location__c.Penetration__c</members>'
       f'<members>Property_Location__c.Penetration_Priority__c</members>'
       f'<name>CustomField</name></types>'
       f'<types><members>Admin</members><name>Profile</name></types>'
       f'<version>{V}</version></Package>')

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", PKG)
    zf.writestr("objects/Property_Location__c.object", OBJECT_XML)
    zf.writestr("profiles/Admin.profile", PROFILE_XML)

url = f"{INSTANCE}/services/data/v{V}/metadata/deployRequest"
_raw = base64.b64encode(buf.getvalue()).decode()
b64 = "\r\n".join(_raw[i:i+76] for i in range(0, len(_raw), 76))
body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
bnd = "----B"
payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\nContent-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\nContent-Type: application/zip\r\n"
           f"Content-Transfer-Encoding: base64\r\n\r\n{b64}\r\n--{bnd}--")
r = requests.post(url, headers={"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={bnd}"}, data=payload)
if r.status_code not in (200, 201):
    print(f"POST {r.status_code}: {r.text[:800]}"); raise SystemExit(1)
did = r.json()["id"]
ok = False
for i in range(40):
    time.sleep(3)
    res = requests.get(f"{url}/{did}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"}).json()
    st = res.get("deployResult", {}).get("status", "?")
    print(f"  poll {i+1}: {st}")
    if st == "Succeeded":
        ok = True; break
    if st in ("Failed", "Canceled", "SucceededPartial"):
        for f in (res.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
            if isinstance(f, dict): print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
        raise SystemExit(1)
if not ok:
    print("timeout"); raise SystemExit(1)
print("Fields deployed.\n")

# ── Verify: old Priority vs new Penetration_Priority on business (non-stale) ──
recs = sf.query_all(
    "SELECT Priority__c, Penetration_Priority__c, Penetration__c, "
    "Property_Unit_Count__c, Active_Unit_Count__c, Deactive_Unit_Count__c, Name "
    "FROM Property_Location__c WHERE Address_Type__c='Business' "
    "AND Import_Delete_Property__c=false"
)['records']
old = Counter(); new = Counter()
for r in recs:
    old[r.get('Priority__c') or '(blank)'] += 1
    new[r.get('Penetration_Priority__c') or '(blank)'] += 1
keys = ['Category 1', 'Category 2', 'Category 3', 'All Active', 'Hold', '(blank)']
print(f"  {'bucket':<14} {'old Priority':>13} {'new PenPriority':>16}")
for k in keys:
    print(f"  {k:<14} {old.get(k,0):>13,} {new.get(k,0):>16,}")
lit_new = new.get('Category 1', 0) + new.get('All Active', 0)
lit_old = old.get('Category 1', 0) + old.get('All Active', 0)
print(f"\n  lit (Cat1 + All Active):  old={lit_old:,}  new={lit_new:,}  "
      f"(delta {lit_new-lit_old:+,} = single-unit churned reclassified)")

# Spot-check the percent field on a known multi-unit building
sample = sf.query("SELECT Name, Property_Unit_Count__c, Active_Unit_Count__c, "
                  "Penetration__c, Penetration_Priority__c FROM Property_Location__c "
                  "WHERE Name LIKE '3333 COUNTY ROAD 119%' AND Address_Type__c='Business' LIMIT 1")['records']
if sample:
    s = sample[0]
    print(f"\n  Spot-check {s['Name']}: {s.get('Active_Unit_Count__c')}/{s.get('Property_Unit_Count__c')} "
          f"-> Penetration__c={s.get('Penetration__c')}  ({s.get('Penetration_Priority__c')})")
