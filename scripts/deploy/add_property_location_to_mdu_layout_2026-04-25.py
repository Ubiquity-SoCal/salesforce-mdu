"""
Add Property_Location__c lookup to MDU Opportunity Layout (used by MDU/SFU + Business_ROE RTs).

Places it at top of Property Details section so it's prominent — RE/MDU team
uses this to navigate to the parent building.
"""
import sys, io, time, base64, zipfile, argparse, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce
from datetime import datetime
from pathlib import Path

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
SESSION = sf.session_id
META_URL = f"https://{sf.sf_instance}/services/Soap/m/59.0"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

# Retrieve MDU Opportunity Layout
print("[Retrieve] MDU Opportunity Layout")
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
          <types><members>Opportunity-MDU Opportunity Layout</members><name>Layout</name></types>
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
backup_path = AUDIT_DIR / f'mdu_layout_backup_{TS.replace(":","-")}.zip'
backup_path.write_bytes(base64.b64decode(zip_b64))
print(f"  ✓ Backup: {backup_path}")

layout_xml = retrieved.read('layouts/Opportunity-MDU Opportunity Layout.layout').decode('utf-8')

if 'Property_Location__c' in layout_xml:
    print("  Property_Location__c already on layout — no action needed.")
    sys.exit(0)

# Insert Property_Location__c at the TOP of the Property Details section
# Find <label>Property Details</label> and add a layoutItem to the first layoutColumn within
# Simple string-based: find the section, find its first <layoutColumns>, insert <layoutItems> at top
new_item = (
    '            <layoutItems>\n'
    '                <behavior>Edit</behavior>\n'
    '                <field>Property_Location__c</field>\n'
    '            </layoutItems>\n'
)

# Locate "Property Details" section and inject into its first layoutColumns block
section_marker = '<label>Property Details</label>'
section_pos = layout_xml.find(section_marker)
if section_pos == -1:
    print("  ⚠ 'Property Details' section not found in layout")
    sys.exit(1)

# Find the first <layoutColumns> after the section_marker
first_col_pos = layout_xml.find('<layoutColumns>', section_pos)
if first_col_pos == -1:
    print("  ⚠ No <layoutColumns> in Property Details section")
    sys.exit(1)

# Insert new_item right after the opening <layoutColumns> tag
insert_at = first_col_pos + len('<layoutColumns>') + 1  # after tag + newline
new_layout = layout_xml[:insert_at] + new_item + layout_xml[insert_at:]

print("\nPlanning to add Property_Location__c at top of Property Details section.")

if not args.apply:
    print("\n[Preview only — re-run with --apply to deploy]")
    sys.exit(0)

# Build deploy package
package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Opportunity-MDU Opportunity Layout</members><name>Layout</name></types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('layouts/Opportunity-MDU Opportunity Layout.layout', new_layout)
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

r = requests.post(META_URL, data=deploy_xml, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
deploy_id = ET.fromstring(r.text).find(".//met:id", NS).text
print(f"\nDeploy ID: {deploy_id}")

for i in range(60):
    time.sleep(2)
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
    if root.find(".//met:done", NS).text == 'true':
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
