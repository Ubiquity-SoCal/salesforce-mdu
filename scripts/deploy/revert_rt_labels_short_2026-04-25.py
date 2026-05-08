"""
Quick fix: revert RT labels to short/clean. Move descriptive context into the
RT Description field (which renders in the +New picker but NOT in Tracker columns,
reports, list views, or page headers).
"""
import sys, io, time, base64, zipfile, argparse, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
SESSION = sf.session_id
META_URL = f"https://{sf.sf_instance}/services/Soap/m/59.0"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}

opportunity_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <recordTypes>
        <fullName>MDU</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>MDU/SFU</label>
        <description>Residential property pursuits (apartments, condos, townhomes, single family, etc) at the Property Location level. Use Business ROE for commercial buildings.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business</fullName>
        <active>true</active>
        <businessProcess>Business Sales Process</businessProcess>
        <label>Business Sales</label>
        <description>B2B tenant revenue sales at the Property Unit (suite) level. Create from a Property Unit page.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business_ROE</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>Business ROE</label>
        <description>Commercial property access pursuits (business parks, strip malls, offices, etc) at the Property Location level. Use MDU/SFU for residential buildings.</description>
    </recordTypes>
</CustomObject>
"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>Opportunity</members><name>CustomObject</name></types>
    <version>59.0</version>
</Package>"""

print("=" * 70)
print(f"REVERT RT LABELS TO SHORT — {'APPLY' if args.apply else 'PREVIEW'}")
print("=" * 70)
print('\nNew labels (short, clean):')
print('  MDU         → "MDU/SFU"')
print('  Business    → "Business Sales"')
print('  Business_ROE → "Business ROE"')
print('\nDescriptive context moved to Description field (shows in picker only).')

if not args.apply:
    sys.exit(0)

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('objects/Opportunity.object', opportunity_xml)
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
        print(f"\n{'✓ DEPLOY SUCCESS' if success == 'true' else '⚠ DEPLOY FAILED'}")
        break
