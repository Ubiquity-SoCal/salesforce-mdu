"""
Add 2 picklist values to Sales_Status__c on Opportunity:
  - Research Completed (sub-status under Prospecting — research done, no contact yet)
  - FF Sales - Tenant Interest Required (sub-status under Engaged — PM verbally agreed
    contingent on tenant demand, FF Sales finding tenants)

Required before the SMB ROE backfill can run.
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
META_URL = f"https://{sf.sf_instance}/services/Soap/m/59.0"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

# Retrieve current Sales_Status field
print("[Retrieve] current Sales_Status__c field state")
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
          <types><members>Opportunity.Sales_Status__c</members><name>CustomField</name></types>
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
backup = AUDIT_DIR / f'sales_status_backup_{TS.replace(":","-")}.zip'
backup.write_bytes(base64.b64decode(zip_b64))
print(f"  ✓ Backup: {backup}")

# The retrieve places Sales_Status__c inside objects/Opportunity.object
fname = 'objects/Opportunity.object'
print(f"  Reading: {fname}")
obj_xml = retrieved.read(fname).decode('utf-8')

NEW_VALUES = ['Research Completed', 'FF Sales - Tenant Interest Required']
to_add = [v for v in NEW_VALUES if f'<fullName>{v}</fullName>' not in obj_xml]
print(f"\n  Values to add: {to_add}")
if not to_add:
    print("  All target values already present.")
    sys.exit(0)

# Build modified XML — inject new <value> blocks into Sales_Status__c's valueSetDefinition.
# Need to find the right valueSetDefinition (the one inside Sales_Status__c field).
# Approach: find <fullName>Sales_Status__c</fullName>, then within that field block, find </valueSetDefinition>
ss_marker = '<fullName>Sales_Status__c</fullName>'
ss_pos = obj_xml.find(ss_marker)
if ss_pos == -1:
    print("  ⚠ Sales_Status__c field not found in Opportunity.object")
    sys.exit(1)
# Find the next </valueSetDefinition> after the field's fullName marker
vsd_close = obj_xml.find('</valueSetDefinition>', ss_pos)
if vsd_close == -1:
    print("  ⚠ </valueSetDefinition> not found after Sales_Status__c marker")
    sys.exit(1)

new_value_block = ''
for v in to_add:
    new_value_block += (
        '                <value>\n'
        f'                    <fullName>{v}</fullName>\n'
        '                    <default>false</default>\n'
        f'                    <label>{v}</label>\n'
        '                </value>\n'
    )

new_field_xml = obj_xml[:vsd_close] + new_value_block + '            ' + obj_xml[vsd_close:]
fname_for_deploy = 'objects/Opportunity.object'
new_field_xml_to_deploy = new_field_xml

print("\n  Modified field XML preview (truncated):")
for line in new_field_xml.split('\n'):
    if any(v in line for v in NEW_VALUES) or 'value' in line.lower():
        print(f"    {line.strip()}")

if not args.apply:
    print("\n[Preview only — re-run with --apply to deploy]")
    sys.exit(0)

# Build deploy package
package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Opportunity.Sales_Status__c</members><name>CustomField</name></types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr(fname_for_deploy, new_field_xml_to_deploy)
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
