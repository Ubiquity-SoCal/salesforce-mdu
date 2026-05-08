"""
Match IronClad__c records to Agreement__c records in Salesforce.

Matching strategy (in priority order):
1. AgreeName parse: IronClad Agree_Name__c (City_MDU_PropName) -> parse property name -> match to Opportunity name -> find Agreement__c on that Opportunity with matching type
2. Property Name direct: IronClad Property_Name__c -> match to Opportunity name -> find Agreement on that Opp
3. Property Name fuzzy: normalize and retry (strip "Apartments", "LLC", etc.)

Once matched, updates:
- IronClad__c.Agreement__c (lookup to Agreement__c)
- Agreement__c.IronClad_ID__c (text field, already exists)

Also creates Matched/Unmatched list views.
"""

import requests
import json
import time
import base64
import io
import zipfile
import re
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)


def metadata_deploy(zip_bytes):
    deploy_url = f"{INSTANCE_URL}/services/data/v{API_VERSION}/metadata/deployRequest"
    zip_b64 = base64.b64encode(zip_bytes).decode()
    deploy_body = {"deployOptions": {"checkOnly": False, "ignoreWarnings": True, "rollbackOnError": True, "singlePackage": True}}
    boundary = "----DeployBoundary"
    body_str = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(deploy_body)}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
        f"Content-Type: application/zip\r\n"
        f"Content-Transfer-Encoding: base64\r\n\r\n"
        f"{zip_b64}\r\n"
        f"--{boundary}--"
    )
    headers = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": f"multipart/form-data; boundary={boundary}"}
    resp = requests.post(deploy_url, headers=headers, data=body_str)
    if resp.status_code not in (200, 201):
        print(f"Deploy failed: {resp.status_code} - {resp.text[:500]}")
        return False
    deploy_id = resp.json().get("id")
    for i in range(30):
        time.sleep(3)
        check = requests.get(f"{deploy_url}/{deploy_id}?includeDetails=true", headers={"Authorization": f"Bearer {sf.session_id}"})
        result = check.json()
        status = result.get("deployResult", {}).get("status", "unknown")
        print(f"  Poll {i+1}: {status}")
        if status == "Succeeded":
            return True
        if status in ("Failed", "Canceled", "SucceededPartial"):
            for f in (result.get("deployResult", {}).get("details", {}).get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    return False


# ============================================================
# STEP 1: Add Agreement__c lookup + Matched formula on IronClad__c
# ============================================================
print("=" * 60)
print("STEP 1: Add Agreement lookup + Matched field to IronClad__c")
print("=" * 60)

# Check if field already exists
desc = sf.IronClad__c.describe()
existing = [f["name"] for f in desc["fields"]]

fields_to_add = ""

if "Agreement__c" not in existing:
    fields_to_add += """
    <fields>
        <fullName>Agreement__c</fullName>
        <label>Agreement</label>
        <type>Lookup</type>
        <referenceTo>Agreement__c</referenceTo>
        <relationshipLabel>IronClad Records</relationshipLabel>
        <relationshipName>IronClad_Records</relationshipName>
        <deleteConstraint>SetNull</deleteConstraint>
    </fields>"""
else:
    print("  Agreement__c lookup already exists")

if "Matched__c" not in existing:
    fields_to_add += """
    <fields>
        <fullName>Matched__c</fullName>
        <label>Matched</label>
        <type>Checkbox</type>
        <defaultValue>false</defaultValue>
        <description>True when linked to an Agreement__c record</description>
    </fields>"""
else:
    print("  Matched__c already exists")

if "Match_Method__c" not in existing:
    fields_to_add += """
    <fields>
        <fullName>Match_Method__c</fullName>
        <label>Match Method</label>
        <type>Text</type>
        <length>50</length>
        <description>How this record was matched (AgreeName, PropertyName, Fuzzy, Manual)</description>
    </fields>"""
else:
    print("  Match_Method__c already exists")

if fields_to_add:
    obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>IronClad</label>
    <pluralLabel>IronClad Records</pluralLabel>
    <nameField>
        <label>IronClad Number</label>
        <displayFormat>IC-{{0000}}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ReadWrite</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    {fields_to_add}
</CustomObject>"""

    pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>IronClad__c</members><name>CustomObject</name></types>
    <version>{API_VERSION}</version>
</Package>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg_xml)
        zf.writestr("objects/IronClad__c.object", obj_xml)

    result = metadata_deploy(buf.getvalue())
    if not result:
        print("Field deployment failed!")
        exit(1)
    print("New fields deployed!")

    # Grant FLS on new fields
    fls_fields = []
    if "Agreement__c" not in existing:
        fls_fields.append("Agreement__c")
    if "Matched__c" not in existing:
        fls_fields.append("Matched__c")
    if "Match_Method__c" not in existing:
        fls_fields.append("Match_Method__c")

    if fls_fields:
        field_perms = ""
        for f in fls_fields:
            field_perms += f"""
        <fieldPermissions>
            <editable>true</editable>
            <field>IronClad__c.{f}</field>
            <readable>true</readable>
        </fieldPermissions>"""

        profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    {field_perms}
</Profile>"""

        pkg2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Admin</members><name>Profile</name></types>
    <version>{API_VERSION}</version>
</Package>"""

        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.xml", pkg2)
            zf.writestr("profiles/Admin.profile", profile_xml)

        print("Granting field access...")
        metadata_deploy(buf2.getvalue())

# ============================================================
# STEP 2: Load all data for matching
# ============================================================
print("\n" + "=" * 60)
print("STEP 2: Load data for matching")
print("=" * 60)

# Refresh SF connection after metadata changes
sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# Load all IronClad records
ic_records = sf.query_all(
    "SELECT Id, IronClad_Id__c, Agree_Name__c, Property_Name__c, "
    "Record_Type_IC__c, Counterparty_Name__c, Property_City__c, Agreement__c "
    "FROM IronClad__c"
)["records"]
print(f"IronClad records: {len(ic_records)}")

# Load all Agreement__c records with their Opportunity
agr_records = sf.query_all(
    "SELECT Id, Name, Agreement_Type__c, Status__c, IronClad_ID__c, "
    "Opportunity__c, Opportunity__r.Name "
    "FROM Agreement__c"
)["records"]
print(f"Agreement records: {len(agr_records)}")

# Load all Opportunities
opp_records = sf.query_all("SELECT Id, Name FROM Opportunity")["records"]
print(f"Opportunity records: {len(opp_records)}")

# Build lookup maps
# Opp name (lowercase) -> Opp ID
opp_by_name = {}
for o in opp_records:
    name = o["Name"].lower().strip()
    opp_by_name[name] = o["Id"]

# Opp ID -> list of Agreement records
agr_by_opp = {}
for a in agr_records:
    opp_id = a.get("Opportunity__c")
    if opp_id:
        agr_by_opp.setdefault(opp_id, []).append(a)

# Map IronClad record type to Agreement type
IC_TO_AGR_TYPE = {
    "Premises Access License": "PAL",
    "Right of Entry Agreement": "ROE",
    "Exclusive Marketing Agreement": "EMA",
    "Non-Exclusive Marketing Agreement": "EMA",
    "Bulk Services Agreement": "Bulk",
}


def normalize(name):
    """Normalize property name for fuzzy matching."""
    if not name:
        return ""
    n = name.lower().strip()
    # Remove common suffixes
    for suffix in [" apartments", " apartment homes", " apartment", " apts",
                   " townhomes", " townhouses", " condos", " condominiums",
                   " llc", " inc", " corp", " lp", " ltd",
                   " homes", " home", " villas", " village",
                   " estates", " residences", " residence",
                   " complex", " community", " communities",
                   " senior living", " living"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    # Remove punctuation
    n = re.sub(r"[^a-z0-9\s]", "", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    return n


def find_agreement_match(ic_record, property_name, method_label):
    """Try to match a property name to an Opportunity, then find the right Agreement."""
    if not property_name:
        return None, None

    # Direct match
    opp_id = opp_by_name.get(property_name.lower().strip())

    # Fuzzy match if no direct hit
    if not opp_id:
        norm_prop = normalize(property_name)
        if norm_prop:
            for opp_name, oid in opp_by_name.items():
                if normalize(opp_name) == norm_prop:
                    opp_id = oid
                    method_label = method_label.replace("Direct", "Fuzzy")
                    break

    if not opp_id:
        return None, None

    # Find matching agreement on this opportunity
    agreements = agr_by_opp.get(opp_id, [])
    if not agreements:
        return None, None

    # Try to match by type
    ic_type = ic_record.get("Record_Type_IC__c", "")
    agr_type = IC_TO_AGR_TYPE.get(ic_type)

    if agr_type:
        type_matches = [a for a in agreements if a.get("Agreement_Type__c") == agr_type]
        if type_matches:
            return type_matches[0]["Id"], method_label
        # If no type match but only one agreement, use it anyway
        if len(agreements) == 1:
            return agreements[0]["Id"], method_label + " (type mismatch)"

    # No type info - if only one agreement, use it
    if len(agreements) == 1:
        return agreements[0]["Id"], method_label

    # Multiple agreements, can't disambiguate
    return None, None


# ============================================================
# STEP 3: Run matching
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Running matching")
print("=" * 60)

matches = []  # (IronClad ID, Agreement SF ID, IronClad IC-ID, method)
already_matched = 0
no_match = 0

for ic in ic_records:
    # Skip if already matched
    if ic.get("Agreement__c"):
        already_matched += 1
        continue

    agr_id = None
    method = None

    # Strategy 1: Parse AgreeName (City_MDU_PropertyName)
    agree_name = ic.get("Agree_Name__c")
    if agree_name and not agr_id:
        parts = agree_name.split("_", 2)
        if len(parts) >= 3:
            parsed_prop = parts[2]
            agr_id, method = find_agreement_match(ic, parsed_prop, "AgreeName Direct")

    # Strategy 2: Property Name direct/fuzzy
    prop_name = ic.get("Property_Name__c")
    if prop_name and not agr_id:
        agr_id, method = find_agreement_match(ic, prop_name, "PropertyName Direct")

    if agr_id:
        matches.append((ic["Id"], agr_id, ic["IronClad_Id__c"], method))
    else:
        no_match += 1

print(f"\nResults:")
print(f"  Already matched: {already_matched}")
print(f"  New matches found: {len(matches)}")
print(f"  No match: {no_match}")
print(f"  Total: {already_matched + len(matches) + no_match}")

# Method breakdown
from collections import Counter
method_counts = Counter(m[3] for m in matches)
print("\nMatch methods:")
for method, count in method_counts.most_common():
    print(f"  {method}: {count}")

# ============================================================
# STEP 4: Apply matches
# ============================================================
if matches:
    print("\n" + "=" * 60)
    print(f"STEP 4: Applying {len(matches)} matches")
    print("=" * 60)

    success = 0
    errors = 0

    for ic_sf_id, agr_sf_id, ic_id, method in matches:
        try:
            # Update IronClad__c with Agreement lookup + matched flag
            sf.IronClad__c.update(ic_sf_id, {
                "Agreement__c": agr_sf_id,
                "Matched__c": True,
                "Match_Method__c": method,
            })

            # Update Agreement__c with IronClad ID
            sf.Agreement__c.update(agr_sf_id, {
                "IronClad_ID__c": ic_id,
            })

            success += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ERROR {ic_id}: {str(e)[:200]}")

    print(f"\n  Success: {success}")
    print(f"  Errors: {errors}")


# ============================================================
# STEP 5: Deploy Matched / Unmatched list views
# ============================================================
print("\n" + "=" * 60)
print("STEP 5: Deploy Matched / Unmatched list views")
print("=" * 60)

COLUMNS = """
        <columns>IronClad_Id__c</columns>
        <columns>Record_Name__c</columns>
        <columns>Record_Type_IC__c</columns>
        <columns>Contract_Status__c</columns>
        <columns>Matched__c</columns>
        <columns>Match_Method__c</columns>
        <columns>Agreement__c</columns>
        <columns>Property_Name__c</columns>
        <columns>Property_City__c</columns>
        <columns>Counterparty_Name__c</columns>
        <columns>MDU_or_BUS__c</columns>"""

views_xml = f"""
    <listViews>
        <fullName>Matched_Records</fullName>
        <label>Matched Records</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Matched__c</field>
            <operation>equals</operation>
            <value>1</value>
        </filters>
        {COLUMNS}
    </listViews>
    <listViews>
        <fullName>Unmatched_Records</fullName>
        <label>Unmatched Records</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>Matched__c</field>
            <operation>equals</operation>
            <value>0</value>
        </filters>
        {COLUMNS}
    </listViews>"""

obj_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>IronClad</label>
    <pluralLabel>IronClad Records</pluralLabel>
    <nameField>
        <label>IronClad Number</label>
        <displayFormat>IC-{{0000}}</displayFormat>
        <type>AutoNumber</type>
    </nameField>
    <sharingModel>ReadWrite</sharingModel>
    <deploymentStatus>Deployed</deploymentStatus>
    {views_xml}
</CustomObject>"""

pkg_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>IronClad__c</members><name>CustomObject</name></types>
    <types>
        <members>IronClad__c.Matched_Records</members>
        <members>IronClad__c.Unmatched_Records</members>
        <name>ListView</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("package.xml", pkg_xml)
    zf.writestr("objects/IronClad__c.object", obj_xml)

metadata_deploy(buf.getvalue())

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print("DONE!")
print("=" * 60)
total_matched = already_matched + len(matches)
total = len(ic_records)
print(f"Matched: {total_matched}/{total} ({total_matched/total*100:.1f}%)")
print(f"Unmatched: {total - total_matched}/{total}")
print(f"\nNew list views: 'Matched Records' and 'Unmatched Records'")
print(f"Fields visible: Matched (checkbox), Match Method (text), Agreement (lookup)")
print(f"\nAgreement__c records also updated with IronClad_ID__c for cross-reference.")
