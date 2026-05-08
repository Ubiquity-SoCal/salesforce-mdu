"""
Phase 2 follow-up (2026-04-25):
  1. Update RT labels: add Residential/Commercial/Tenant Suite tags
  2. Add 2 validation rules: MDU on commercial blocked, Business_ROE on residential blocked
  3. Assign MDU Opportunity Layout to Business_ROE RT for Admin + Standard User - Custom profiles

Usage:
  python phase2_followup_2026-04-25.py --preview
  python phase2_followup_2026-04-25.py --apply
"""
import sys, io, time, base64, zipfile, argparse, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
SESSION = sf.session_id
INSTANCE = sf.sf_instance
META_URL = f"https://{INSTANCE}/services/Soap/m/59.0"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

print("=" * 70)
print(f"PHASE 2 FOLLOW-UP — {'APPLY' if args.apply else 'PREVIEW'}")
print("=" * 70)

# ── Retrieve current profiles to extend layoutAssignments ──
print("\n[Retrieve] Pulling Admin, Standard User - Custom, B2B Vendor profiles")
retrieve_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:retrieve>
      <met:retrieveRequest>
        <met:apiVersion>59.0</met:apiVersion>
        <met:singlePackage>true</met:singlePackage>
        <met:unpackaged>
          <types><members>Admin</members><members>Standard User - Custom</members><name>Profile</name></types>
          <version>59.0</version>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

r = requests.post(META_URL, data=retrieve_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "retrieve"})
async_id = ET.fromstring(r.text).find(".//met:id", NS).text
zip_b64 = None
for i in range(60):
    time.sleep(2)
    check = f"""<?xml version="1.0" encoding="utf-8"?>
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
    r = requests.post(META_URL, data=check, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkRetrieveStatus"})
    root = ET.fromstring(r.text)
    if root.find(".//met:done", NS).text == 'true':
        zip_b64 = root.find(".//met:zipFile", NS).text
        break

retrieved = zipfile.ZipFile(io.BytesIO(base64.b64decode(zip_b64)))
backup_path = AUDIT_DIR / f'phase2_followup_backup_{TS.replace(":","-")}.zip'
backup_path.write_bytes(base64.b64decode(zip_b64))
print(f"  ✓ Backup: {backup_path}")
print(f"  Retrieved: {retrieved.namelist()}")

deploy_files = {}

# ── A. RT labels with Residential/Commercial/Tenant Suite tags ──
# ── B. New validation rules for RT/Property_Type mismatch ──
COMMERCIAL = ['Commercial / Business', 'Business Park', 'Strip Mall', 'Office', 'Retail']
RESIDENTIAL = ['Apartments', 'Condos', 'Townhomes', 'Private SFU Neighborhood',
               'Single Family Rental Homes', 'Manufactured Homes / Mobile Homes',
               'Senior Living / Assisted Living']
# Mixed Use: deliberately omitted from both rules — could be either

def or_clause_for_text_picklist(values, field='Property_Location__r.Property_Type__c'):
    parts = [f'TEXT({field}) = &quot;{v}&quot;' for v in values]
    return 'OR(\n        ' + ',\n        '.join(parts) + '\n    )'

opportunity_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <recordTypes>
        <fullName>MDU</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>MDU/SFU - Residential (Property Location level)</label>
        <description>MDU and Single Family Unit pursuits at residential properties. Created at the Property Location (building) level.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business</fullName>
        <active>true</active>
        <businessProcess>Business Sales Process</businessProcess>
        <label>Business Sales - Tenant Suite (Property Unit level)</label>
        <description>B2B tenant revenue sales. Created at the Property Unit (tenant suite) level.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business_ROE</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>Business ROE - Commercial (Property Location level)</label>
        <description>SMB Real Estate building access pursuits at commercial properties. Created at the Property Location (commercial building) level.</description>
    </recordTypes>
</CustomObject>
"""
deploy_files['objects/Opportunity.object'] = opportunity_xml
print("\n  [A] RT labels: adding Residential/Commercial/Tenant Suite tags")
print("  [B] Validation rules SKIPPED — Koa preferred soft warning over hard block.")
print("      Future task: Screen Flow override on +New for soft warning UX (~3-4 hours)")

# ── C. Layout assignment for Business_ROE RT — add to profiles ──
print("\n  [C] Profile layoutAssignments — assign MDU Opportunity Layout to Business_ROE RT")

def add_layout_assignment(profile_name):
    fname = f'profiles/{profile_name}.profile'
    if fname not in retrieved.namelist():
        print(f"    ⚠ {fname} not in retrieve")
        return None
    content = retrieved.read(fname).decode('utf-8')
    if '<recordType>Opportunity.Business_ROE</recordType>' in content and 'MDU Opportunity Layout' in content:
        # Check if the assignment already exists
        if '<layout>Opportunity-MDU Opportunity Layout</layout>\n        <recordType>Opportunity.Business_ROE</recordType>' in content.replace(' ', '').replace('\n','').replace('\t',''):
            print(f"    Already assigned in {profile_name}")
            return content
    # Insert after the LAST </layoutAssignments>
    new_block = (
        '    <layoutAssignments>\n'
        '        <layout>Opportunity-MDU Opportunity Layout</layout>\n'
        '        <recordType>Opportunity.Business_ROE</recordType>\n'
        '    </layoutAssignments>\n'
    )
    last_close = content.rfind('</layoutAssignments>')
    if last_close == -1:
        print(f"    ⚠ No existing layoutAssignments in {profile_name} — appending before </Profile>")
        return content.replace('</Profile>', new_block + '</Profile>')
    insert_at = last_close + len('</layoutAssignments>') + 1
    return content[:insert_at] + new_block + content[insert_at:]

for prof in ['Admin', 'Standard User - Custom']:
    out = add_layout_assignment(prof)
    if out:
        deploy_files[f'profiles/{prof}.profile'] = out
        print(f"    ✓ {prof}: layoutAssignment added")

# ── package.xml ──
profile_members = '\n'.join(f'    <members>{p}</members>' for p in ['Admin', 'Standard User - Custom'] if f'profiles/{p}.profile' in deploy_files)
package_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
    <members>Opportunity</members>
    <name>CustomObject</name>
  </types>
  <types>
{profile_members}
    <name>Profile</name>
  </types>
  <version>59.0</version>
</Package>"""
deploy_files['package.xml'] = package_xml

# Save package
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    for fn, content in deploy_files.items():
        zf.writestr(fn, content)
pkg_path = AUDIT_DIR / f'phase2_followup_package_{TS.replace(":","-")}.zip'
pkg_path.write_bytes(buf.getvalue())
print(f"\n✓ Deploy package built: {pkg_path}")
print(f"  Files:")
for fn in deploy_files:
    print(f"    {fn}")

if not args.apply:
    print("\n[Preview only — re-run with --apply to deploy]")
    sys.exit(0)

# Deploy
buf.seek(0)
deploy_b64 = base64.b64encode(buf.read()).decode('utf-8')
deploy_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{SESSION}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{deploy_b64}</met:ZipFile>
      <met:DeployOptions>
        <met:rollbackOnError>true</met:rollbackOnError>
        <met:singlePackage>true</met:singlePackage>
        <met:checkOnly>false</met:checkOnly>
      </met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""
print("\nDeploying...")
r = requests.post(META_URL, data=deploy_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
deploy_id = ET.fromstring(r.text).find(".//met:id", NS).text
print(f"Deploy async ID: {deploy_id}")

for i in range(120):
    time.sleep(3)
    check = f"""<?xml version="1.0" encoding="utf-8"?>
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
    r = requests.post(META_URL, data=check, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
    root = ET.fromstring(r.text)
    done = root.find(".//met:done", NS).text
    status = root.find(".//met:status", NS).text
    print(f"  status={status}, done={done}")
    if done == 'true':
        success = root.find(".//met:success", NS).text
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
