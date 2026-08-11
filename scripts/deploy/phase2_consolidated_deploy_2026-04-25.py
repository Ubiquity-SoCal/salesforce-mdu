"""
Phase 2 — Consolidated Metadata Deploy (2026-04-25)

Single atomic deploy via Metadata API SOAP. If any component fails, the whole
package rolls back. Audit log captures the deployed state.

Components:
  A. Property_Type__c — add 4 commercial picklist values (Business Park, Strip Mall, Office, Retail)
  B. Opportunity custom fields — Closed_Notes__c, Off_Hold_Date__c, FF_Notes__c, Sales_Handoff_Date__c
  C. SMB_RE_Field_Access permset — extend FLS for the 4 new fields
  D. Opportunity Record Types — rename MDU→"MDU/SFU" label, rename Business→"Business Sales" label,
                                 deactivate SFU, create Business_ROE bound to MDU Sales Process
  E. MDU Sales Process — add ROE Secured stage; Business Sales Process — keep current shape
                         (stale stages have 0 records after Phase 1 cleanup; trim deferred to be safe)
  F. Profiles — B2B Vendor sees Business RT only; Standard User - Custom + Admin see all 3
  G. Validation rules — extend MDU_No_Closed_Won and Require_City_State_Zip to also cover Business_ROE;
                        new Business_Sales_Requires_Property_Unit (ISNEW only)
  H. MDU Opportunity Layout — add 4 new fields in a new "Pursuit Tracking" section
  I. List views — RE team filtered by Business_ROE RT

Usage:
  python phase2_consolidated_deploy_2026-04-25.py --preview      # build package, save zip, no deploy
  python phase2_consolidated_deploy_2026-04-25.py --apply        # build + deploy
"""
import sys, io, time, base64, zipfile, json, argparse, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true', help='Execute the deploy (default: preview only)')
args = ap.parse_args()
APPLY = args.apply

USERNAME = _SF["username"]
PASSWORD = _SF["password"]
TOKEN = _SF["token"]
INSTANCE_URL = 'https://fun-power-747.my.salesforce.com'
API_VER = '59.0'

AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().isoformat(timespec='seconds')
PKG_PATH = AUDIT_DIR / f'phase2_package_{TS.replace(":","-")}.zip'

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=TOKEN)
SESSION = sf.session_id
META_URL = f"{INSTANCE_URL}/services/Soap/m/{API_VER}"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
NS_M = {"sf": "http://soap.sforce.com/2006/04/metadata"}

print("=" * 70)
print(f"PHASE 2 CONSOLIDATED DEPLOY — {'APPLY' if APPLY else 'PREVIEW'}")
print(f"Timestamp: {TS}")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────
# STEP 1: Retrieve current state of metadata we plan to modify
# ─────────────────────────────────────────────────────────────────────
print("\n[Retrieve] Pulling current metadata for layout, profiles, permset, validation rules, Sales Processes")

retrieve_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>{API_VER}</met:apiVersion>
        <met:singlePackage>true</met:singlePackage>
        <met:unpackaged>
          <types><members>Opportunity</members><name>CustomObject</name></types>
          <types><members>Opportunity-MDU Opportunity Layout</members><members>Opportunity-Business Opportunity Layout</members><name>Layout</name></types>
          <types><members>B2B Vendor</members><members>Standard User - Custom</members><members>Admin</members><name>Profile</name></types>
          <types><members>SMB_RE_Field_Access</members><name>PermissionSet</name></types>
          <types><members>Opportunity.MDU_No_Closed_Won</members><members>Opportunity.Require_City_State_Zip_On_New_MDU</members><name>ValidationRule</name></types>
          <version>{API_VER}</version>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

r = requests.post(META_URL, data=retrieve_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "retrieve"})
async_id = ET.fromstring(r.text).find(".//met:id", NS).text
print(f"  Retrieve async ID: {async_id}")

zip_b64 = None
for i in range(60):
    time.sleep(2)
    check_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:checkRetrieveStatus>
      <met:asyncProcessId>{async_id}</met:asyncProcessId>
      <met:includeZip>true</met:includeZip>
    </met:checkRetrieveStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(META_URL, data=check_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkRetrieveStatus"})
    root = ET.fromstring(r.text)
    if root.find(".//met:done", NS).text == "true":
        zip_b64 = root.find(".//met:zipFile", NS).text
        msgs = root.findall(".//met:messages", NS)
        for m in msgs:
            problem = m.find('met:problem', NS)
            if problem is not None:
                print(f"  ⚠ retrieve message: {problem.text}")
        break
    print(f"  ...polling ({i+1})")
else:
    print("  TIMEOUT on retrieve")
    sys.exit(1)

# Save retrieve zip for backup
backup_path = AUDIT_DIR / f'phase2_pre_deploy_backup_{TS.replace(":","-")}.zip'
backup_path.write_bytes(base64.b64decode(zip_b64))
print(f"  ✓ Pre-deploy backup saved: {backup_path}")

retrieved = zipfile.ZipFile(io.BytesIO(base64.b64decode(zip_b64)))
print(f"  Files retrieved: {retrieved.namelist()}")

# ─────────────────────────────────────────────────────────────────────
# STEP 2: Build deploy package
# ─────────────────────────────────────────────────────────────────────
print("\n[Build] Constructing deploy package")
deploy_files = {}

# ── A. Property_Type__c picklist additions ──
# Get current state of field
print("\n  [A] Property_Type__c — adding Business Park, Strip Mall, Office, Retail")
existing_property_type_xml = retrieved.read('objects/Opportunity.object').decode('utf-8')
# Extract existing values from the field
prop_root = ET.fromstring(existing_property_type_xml)
existing_pt_values = []
for fld in prop_root.findall('sf:fields', NS_M):
    name_el = fld.find('sf:fullName', NS_M)
    if name_el is not None and name_el.text == 'Property_Type__c':
        vs = fld.find('sf:valueSet', NS_M)
        if vs is not None:
            for v in vs.findall('sf:valueSetDefinition/sf:value', NS_M):
                existing_pt_values.append(v.find('sf:fullName', NS_M).text)
print(f"    Existing values: {existing_pt_values}")
NEW_PT_VALUES = ['Business Park', 'Strip Mall', 'Office', 'Retail']
NEW_PT_VALUES = [v for v in NEW_PT_VALUES if v not in existing_pt_values]
print(f"    New values to add: {NEW_PT_VALUES}")

# ── B. New Opp custom fields ──
print(f"\n  [B] 4 new Opp custom fields")
new_fields = [
    {'name': 'Closed_Notes__c', 'label': 'Closed Notes', 'type': 'LongTextArea', 'length': 32768, 'visibleLines': 5,
     'description': 'Supplemental notes when Opp is Closed Lost or Closed Won.'},
    {'name': 'Off_Hold_Date__c', 'label': 'Off Hold Date', 'type': 'Date',
     'description': 'Date the Opp came back from On Hold status.'},
    {'name': 'FF_Notes__c', 'label': 'Fiber First Notes', 'type': 'LongTextArea', 'length': 32768, 'visibleLines': 5,
     'description': 'Notes from Fiber First Sales team about this pursuit.'},
    {'name': 'Sales_Handoff_Date__c', 'label': 'Sales Handoff Date', 'type': 'Date',
     'description': 'Date RE team handed this Opp off to Sales (typically when ROE was secured).'},
]

# ── D. RT changes ──
print(f"\n  [D] Record Type changes")
print(f"    - Rename MDU label → MDU/SFU")
print(f"    - Rename Business label → Business Sales")
print(f"    - Deactivate SFU (zero records)")
print(f"    - Create Business_ROE bound to MDU Sales Process")

# ── E. MDU Sales Process — add ROE Secured stage ──
print(f"\n  [E] MDU Sales Process — add ROE Secured stage")

# Build the consolidated Opportunity.object XML
# This includes: new fields, modified RTs, modified businessProcesses, modified Property_Type values
opportunity_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
"""

# Add 4 new fields
for f in new_fields:
    if f['type'] == 'Date':
        opportunity_xml += f"""    <fields>
        <fullName>{f['name']}</fullName>
        <label>{f['label']}</label>
        <type>{f['type']}</type>
        <description>{f['description']}</description>
        <inlineHelpText>{f['description']}</inlineHelpText>
        <required>false</required>
        <trackHistory>false</trackHistory>
    </fields>
"""
    elif f['type'] == 'LongTextArea':
        opportunity_xml += f"""    <fields>
        <fullName>{f['name']}</fullName>
        <label>{f['label']}</label>
        <type>{f['type']}</type>
        <length>{f['length']}</length>
        <visibleLines>{f['visibleLines']}</visibleLines>
        <description>{f['description']}</description>
        <inlineHelpText>{f['description']}</inlineHelpText>
        <required>false</required>
        <trackHistory>false</trackHistory>
    </fields>
"""

# Property_Type__c — full field definition with extended values
# Build the full picklist definition by reading existing and appending new
# Need to re-emit the Property_Type__c field definition with all values
existing_pt_field_xml = None
for fld in prop_root.findall('sf:fields', NS_M):
    name_el = fld.find('sf:fullName', NS_M)
    if name_el is not None and name_el.text == 'Property_Type__c':
        existing_pt_field_xml = ET.tostring(fld, encoding='unicode')
        break

if existing_pt_field_xml and NEW_PT_VALUES:
    # Parse the field XML, locate valueSet, append new values
    field_root = ET.fromstring(existing_pt_field_xml)
    # Strip default namespace from element tags for easier manipulation
    for elem in field_root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}')[1]
    vs_def = field_root.find('valueSet/valueSetDefinition')
    if vs_def is not None:
        for new_val in NEW_PT_VALUES:
            v = ET.SubElement(vs_def, 'value')
            ET.SubElement(v, 'fullName').text = new_val
            ET.SubElement(v, 'default').text = 'false'
            ET.SubElement(v, 'label').text = new_val
    # Re-add namespace
    field_xml = ET.tostring(field_root, encoding='unicode')
    # Wrap with namespace
    field_xml = field_xml.replace('<fields>', '<fields xmlns="http://soap.sforce.com/2006/04/metadata">')
    opportunity_xml += '    ' + field_xml + '\n'

# Sales Processes — emit BOTH (preserves existing) and add ROE Secured to MDU
opportunity_xml += """    <businessProcesses>
        <fullName>MDU Sales Process</fullName>
        <isActive>true</isActive>
        <values><fullName>Prospecting</fullName></values>
        <values><fullName>Engaged</fullName></values>
        <values><fullName>ROE Secured</fullName></values>
        <values><fullName>Contract Negotiations</fullName></values>
        <values><fullName>Under Contract</fullName></values>
        <values><fullName>Closed Won</fullName></values>
        <values><fullName>Closed Lost</fullName></values>
        <values><fullName>On Hold</fullName></values>
    </businessProcesses>
    <businessProcesses>
        <fullName>Business Sales Process</fullName>
        <isActive>true</isActive>
        <values><fullName>Prospecting</fullName></values>
        <values><fullName>Engaged</fullName></values>
        <values><fullName>Contract Negotiations</fullName></values>
        <values><fullName>Under Contract</fullName></values>
        <values><fullName>Closed Won</fullName></values>
        <values><fullName>Closed Lost</fullName></values>
        <values><fullName>On Hold</fullName></values>
    </businessProcesses>
"""

# Record Types
opportunity_xml += """    <recordTypes>
        <fullName>MDU</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>MDU/SFU</label>
        <description>MDU and Single Family Unit pursuits (consolidated 2026-04-25)</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business</fullName>
        <active>true</active>
        <businessProcess>Business Sales Process</businessProcess>
        <label>Business Sales</label>
        <description>B2B tenant revenue sales</description>
    </recordTypes>
    <recordTypes>
        <fullName>SFU</fullName>
        <active>false</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>SFU</label>
        <description>DEPRECATED 2026-04-25 — merged into MDU/SFU. Zero records at deactivation.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business_ROE</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>Business ROE</label>
        <description>SMB Real Estate building access pursuits (commercial properties)</description>
    </recordTypes>
"""

# Validation rules (extend formulas)
opportunity_xml += """    <validationRules>
        <fullName>MDU_No_Closed_Won</fullName>
        <active>true</active>
        <description>MDU and Business ROE opportunities cannot be set to Closed Won. Building-pursuit pipelines end at Under Contract.</description>
        <errorConditionFormula>AND(
    OR(RecordType.DeveloperName = &quot;MDU&quot;, RecordType.DeveloperName = &quot;Business_ROE&quot;),
    ISPICKVAL(StageName, &quot;Closed Won&quot;)
)</errorConditionFormula>
        <errorMessage>MDU and Business ROE opportunities end at Under Contract. Closed Won is only available for Business Sales (tenant revenue) opportunities.</errorMessage>
    </validationRules>
    <validationRules>
        <fullName>Require_City_State_Zip_On_New_MDU</fullName>
        <active>true</active>
        <description>Require Property City, State, Zip on new MDU and Business ROE Opportunity creation.</description>
        <errorConditionFormula>AND(
    OR(RecordType.DeveloperName = &apos;MDU&apos;, RecordType.DeveloperName = &apos;Business_ROE&apos;),
    OR(
        AND(ISNEW(), OR(ISBLANK(Property_City__c), ISBLANK(Property_State__c), ISBLANK(Property_Zip__c))),
        AND(ISCHANGED(Property_City__c), ISBLANK(Property_City__c)),
        AND(ISCHANGED(Property_State__c), ISBLANK(Property_State__c)),
        AND(ISCHANGED(Property_Zip__c), ISBLANK(Property_Zip__c))
    )
)</errorConditionFormula>
        <errorMessage>City, State, and Zip are required for MDU and Business ROE opportunities. These fields cannot be left blank or cleared once set.</errorMessage>
    </validationRules>
    <validationRules>
        <fullName>Business_Sales_Requires_Property_Unit</fullName>
        <active>true</active>
        <description>Business Sales (tenant) opportunities must be linked to a Property Unit at creation time. Existing records grandfathered.</description>
        <errorConditionFormula>AND(
    RecordType.DeveloperName = &quot;Business&quot;,
    ISNEW(),
    ISBLANK(Property_Unit__c)
)</errorConditionFormula>
        <errorMessage>Business Sales opportunities must be linked to a Property Unit. Open the Property Unit and create the Opportunity from there, or set Property Unit before saving.</errorMessage>
    </validationRules>
"""

# RE Team list views (filtered by Business_ROE RT)
# Column refs verified: OPPORTUNITY.NAME, OPPORTUNITY.STAGE_NAME, ACCOUNT.NAME, OPPORTUNITY.OWNER_FULL_NAME
opportunity_xml += """    <listViews>
        <fullName>RE_All_Pursuits</fullName>
        <label>RE - All Pursuits</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business_ROE</value>
        </filters>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Property_Type__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>RE_Assigned__c</columns>
    </listViews>
    <listViews>
        <fullName>RE_Open_Pursuits</fullName>
        <label>RE - Open</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business_ROE</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>notEqual</operation>
            <value>Closed Won,Closed Lost</value>
        </filters>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Property_Type__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>RE_Assigned__c</columns>
    </listViews>
    <listViews>
        <fullName>RE_Mine</fullName>
        <label>RE - Mine</label>
        <filterScope>Mine</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business_ROE</value>
        </filters>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>Property_Type__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
    </listViews>
    <listViews>
        <fullName>RE_On_Hold</fullName>
        <label>RE - On Hold</label>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.Business_ROE</value>
        </filters>
        <filters>
            <field>OPPORTUNITY.STAGE_NAME</field>
            <operation>equals</operation>
            <value>On Hold</value>
        </filters>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>Hold_Reason__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>RE_Assigned__c</columns>
    </listViews>
"""

opportunity_xml += "</CustomObject>\n"
deploy_files['objects/Opportunity.object'] = opportunity_xml

# ── C. Permission Set — extend SMB_RE_Field_Access for FLS on 4 new fields ──
# Use string injection to avoid ElementTree namespace round-trip issues
print("\n  [C] SMB_RE_Field_Access permset — add FLS for 4 new fields")
existing_permset_xml = retrieved.read('permissionsets/SMB_RE_Field_Access.permissionset').decode('utf-8')
NEW_FIELDS_FOR_FLS = [f'Opportunity.{f["name"]}' for f in new_fields]
new_fp_block = ''
for nf in NEW_FIELDS_FOR_FLS:
    if f'<field>{nf}</field>' in existing_permset_xml:
        print(f"    Already present: {nf}")
        continue
    new_fp_block += f'    <fieldPermissions>\n        <editable>true</editable>\n        <field>{nf}</field>\n        <readable>true</readable>\n    </fieldPermissions>\n'

if new_fp_block:
    # Insert AFTER the last existing </fieldPermissions> to keep schema-grouped, NOT at end of file
    last_fp_close = existing_permset_xml.rfind('</fieldPermissions>')
    if last_fp_close != -1:
        insert_at = last_fp_close + len('</fieldPermissions>') + 1  # after closing tag + newline
        permset_xml = existing_permset_xml[:insert_at] + new_fp_block + existing_permset_xml[insert_at:]
    else:
        # No existing fieldPermissions — just insert before </PermissionSet>
        permset_xml = existing_permset_xml.replace('</PermissionSet>', new_fp_block + '</PermissionSet>')
    deploy_files['permissionsets/SMB_RE_Field_Access.permissionset'] = permset_xml
    print(f"    ✓ Adding FLS for {len(new_fields)} fields")
else:
    print(f"    All FLS already present, skipping permset update")

# ── F. Profile updates — RT visibility for Business_ROE ──
# String injection (skip if already present, otherwise insert before </Profile>)
print("\n  [F] Profiles — RT visibility for new Business_ROE RT")

def update_profile_rt(profile_name, business_roe_visible, business_roe_default=False):
    """Inject Business_ROE recordTypeVisibility into profile XML."""
    fname = f'profiles/{profile_name}.profile'
    if fname not in retrieved.namelist():
        print(f"    ⚠ {fname} not in retrieve")
        return None
    content = retrieved.read(fname).decode('utf-8')
    if '<recordType>Opportunity.Business_ROE</recordType>' in content:
        print(f"    Already present in {profile_name}, skipping")
        return content  # leave as is
    new_block = (
        f'    <recordTypeVisibilities>\n'
        f'        <default>{"true" if business_roe_default else "false"}</default>\n'
        f'        <recordType>Opportunity.Business_ROE</recordType>\n'
        f'        <visible>{"true" if business_roe_visible else "false"}</visible>\n'
        f'    </recordTypeVisibilities>\n'
    )
    # Insert AFTER the last existing </recordTypeVisibilities> to keep schema-grouped
    last_close = content.rfind('</recordTypeVisibilities>')
    if last_close != -1:
        insert_at = last_close + len('</recordTypeVisibilities>') + 1
        return content[:insert_at] + new_block + content[insert_at:]
    return content.replace('</Profile>', new_block + '</Profile>')

# B2B Vendor: Business_ROE NOT visible
b2b_xml = update_profile_rt('B2B Vendor', business_roe_visible=False)
if b2b_xml:
    deploy_files['profiles/B2B Vendor.profile'] = b2b_xml
    print(f"    ✓ B2B Vendor: Business_ROE hidden")

# Standard User - Custom: Business_ROE visible
suc_xml = update_profile_rt('Standard User - Custom', business_roe_visible=True)
if suc_xml:
    deploy_files['profiles/Standard User - Custom.profile'] = suc_xml
    print(f"    ✓ Standard User - Custom: Business_ROE visible")

# System Administrator (API name: Admin): Business_ROE visible
sa_xml = update_profile_rt('Admin', business_roe_visible=True)
if sa_xml:
    deploy_files['profiles/Admin.profile'] = sa_xml
    print(f"    ✓ Admin (System Administrator): Business_ROE visible")

# ── H. Layout update — add 4 new fields to MDU Opportunity Layout ──
# String injection: insert new layoutSections block before the first non-layoutSections element
# Salesforce schema requires layoutSections to come before other elements like miniLayout, summaryLayout, etc.
print("\n  [H] MDU Opportunity Layout — add Pursuit Tracking section with 4 new fields")
layout_fname = 'layouts/Opportunity-MDU Opportunity Layout.layout'
if layout_fname in retrieved.namelist():
    layout_xml = retrieved.read(layout_fname).decode('utf-8')
    if 'Pursuit Tracking' in layout_xml:
        print(f"    Pursuit Tracking section already present, skipping")
    else:
        new_section = (
            '    <layoutSections>\n'
            '        <customLabel>true</customLabel>\n'
            '        <detailHeading>true</detailHeading>\n'
            '        <editHeading>true</editHeading>\n'
            '        <label>Pursuit Tracking</label>\n'
            '        <layoutColumns>\n'
            '            <layoutItems><behavior>Edit</behavior><field>Closed_Notes__c</field></layoutItems>\n'
            '            <layoutItems><behavior>Edit</behavior><field>Off_Hold_Date__c</field></layoutItems>\n'
            '        </layoutColumns>\n'
            '        <layoutColumns>\n'
            '            <layoutItems><behavior>Edit</behavior><field>FF_Notes__c</field></layoutItems>\n'
            '            <layoutItems><behavior>Edit</behavior><field>Sales_Handoff_Date__c</field></layoutItems>\n'
            '        </layoutColumns>\n'
            '        <style>TwoColumnsTopToBottom</style>\n'
            '    </layoutSections>\n'
        )
        # Insert right before the LAST </layoutSections> closing tag, which puts the new section after existing ones
        # but still before miniLayout/summaryLayout/relatedLists (which come after layoutSections in the schema)
        last_section_close = layout_xml.rfind('</layoutSections>')
        if last_section_close == -1:
            print(f"    ⚠ No </layoutSections> in layout — falling back to before </Layout>")
            out_layout = layout_xml.replace('</Layout>', new_section + '</Layout>')
        else:
            insert_at = last_section_close + len('</layoutSections>') + 1  # after the closing tag + newline
            out_layout = layout_xml[:insert_at] + new_section + layout_xml[insert_at:]
        deploy_files[layout_fname] = out_layout
        print(f"    ✓ MDU Opportunity Layout updated with Pursuit Tracking section")
else:
    print(f"    ⚠ {layout_fname} not found in retrieve — layout update skipped")

# ── package.xml ──
pkg_members = []
pkg_members.append(('CustomObject', ['Opportunity']))
pkg_members.append(('PermissionSet', ['SMB_RE_Field_Access']))
profiles_in_deploy = []
for fn in deploy_files:
    if fn.startswith('profiles/'):
        profiles_in_deploy.append(fn.replace('profiles/', '').replace('.profile', ''))
if profiles_in_deploy:
    pkg_members.append(('Profile', profiles_in_deploy))
layouts_in_deploy = []
for fn in deploy_files:
    if fn.startswith('layouts/'):
        layouts_in_deploy.append(fn.replace('layouts/', '').replace('.layout', ''))
if layouts_in_deploy:
    pkg_members.append(('Layout', layouts_in_deploy))

types_xml = ''
for tname, members in pkg_members:
    members_xml = '\n'.join(f'    <members>{m}</members>' for m in members)
    types_xml += f"  <types>\n{members_xml}\n    <name>{tname}</name>\n  </types>\n"

package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
{types_xml}  <version>{API_VER}</version>
</Package>"""
deploy_files['package.xml'] = package_xml

# Save package zip
zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn, content in deploy_files.items():
        zf.writestr(fn, content)
PKG_PATH.write_bytes(zip_buffer.getvalue())
print(f"\n✓ Deploy package built: {PKG_PATH}")
print(f"  Files in package:")
for fn in deploy_files:
    print(f"    {fn}")

if not APPLY:
    print("\n[Preview mode — no deploy. Review the package zip above. Re-run with --apply to execute.]")
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────
# STEP 3: Deploy
# ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("DEPLOYING")
print("=" * 70)

zip_buffer.seek(0)
deploy_b64 = base64.b64encode(zip_buffer.read()).decode('utf-8')

deploy_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{deploy_b64}</met:ZipFile>
      <met:DeployOptions>
        <met:allowMissingFiles>false</met:allowMissingFiles>
        <met:autoUpdatePackage>false</met:autoUpdatePackage>
        <met:checkOnly>false</met:checkOnly>
        <met:ignoreWarnings>false</met:ignoreWarnings>
        <met:performRetrieve>false</met:performRetrieve>
        <met:purgeOnDelete>false</met:purgeOnDelete>
        <met:rollbackOnError>true</met:rollbackOnError>
        <met:singlePackage>true</met:singlePackage>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""

r = requests.post(META_URL, data=deploy_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
deploy_id = ET.fromstring(r.text).find(".//met:id", NS)
if deploy_id is None:
    print(f"⚠ Deploy request failed: {r.text[:1000]}")
    sys.exit(1)
deploy_id = deploy_id.text
print(f"Deploy async ID: {deploy_id}")

# Poll
for i in range(120):
    time.sleep(3)
    check_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:checkDeployStatus>
      <met:asyncProcessId>{deploy_id}</met:asyncProcessId>
      <met:includeDetails>true</met:includeDetails>
    </met:checkDeployStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(META_URL, data=check_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
    root = ET.fromstring(r.text)
    done_el = root.find(".//met:done", NS)
    status_el = root.find(".//met:status", NS)
    success_el = root.find(".//met:success", NS)
    done = done_el.text if done_el is not None else 'unknown'
    status = status_el.text if status_el is not None else 'unknown'
    print(f"  Polling... status={status}, done={done}")
    if done == 'true':
        success = success_el.text if success_el is not None else 'unknown'
        if success == 'true':
            print("\n✓ DEPLOY SUCCESS")
        else:
            print("\n⚠ DEPLOY FAILED")
            for el in root.iter():
                tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
                if tag == 'componentFailures':
                    for c in el:
                        ctag = c.tag.split('}')[-1] if '}' in c.tag else c.tag
                        if c.text:
                            print(f"  {ctag}: {c.text}")
        break
else:
    print("⚠ TIMEOUT")
    sys.exit(1)

print("\nDone.")
