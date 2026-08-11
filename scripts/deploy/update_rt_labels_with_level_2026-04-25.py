"""
Quick follow-up to Phase 2: append "(Property Location level)" / "(Property Unit level)"
to Opportunity Record Type labels so the +New popup tells users where in the hierarchy
the RT belongs.

Usage:
  python update_rt_labels_with_level_2026-04-25.py --apply
"""
import sys, io, time, base64, zipfile, argparse, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from xml.etree import ElementTree as ET
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
SESSION = sf.session_id
INSTANCE_URL = sf.sf_instance
META_URL = f"https://{INSTANCE_URL}/services/Soap/m/59.0"
NS = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}

# Build CustomObject deploy with just the recordTypes update
opportunity_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <recordTypes>
        <fullName>MDU</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>MDU/SFU (Property Location level)</label>
        <description>MDU and Single Family Unit pursuits. Created at the Property Location (building) level.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business</fullName>
        <active>true</active>
        <businessProcess>Business Sales Process</businessProcess>
        <label>Business Sales (Property Unit level)</label>
        <description>B2B tenant revenue sales. Created at the Property Unit (tenant suite) level.</description>
    </recordTypes>
    <recordTypes>
        <fullName>Business_ROE</fullName>
        <active>true</active>
        <businessProcess>MDU Sales Process</businessProcess>
        <label>Business ROE (Property Location level)</label>
        <description>SMB Real Estate building access pursuits. Created at the Property Location (commercial building) level.</description>
    </recordTypes>
</CustomObject>
"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity</members>
        <name>CustomObject</name>
    </types>
    <version>59.0</version>
</Package>"""

print("=" * 70)
print(f"RT LABEL UPDATE — {'APPLY' if args.apply else 'PREVIEW'}")
print("=" * 70)
print("\nTarget labels:")
print('  MDU         → "MDU/SFU (Property Location level)"')
print('  Business    → "Business Sales (Property Unit level)"')
print('  Business_ROE → "Business ROE (Property Location level)"')

if not args.apply:
    print("\n[Preview only — re-run with --apply to deploy]")
    sys.exit(0)

# Build zip
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
print(f"\nDeploy async ID: {deploy_id}")

for i in range(60):
    time.sleep(2)
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
    print(f"  Polling... done={root.find('.//met:done', NS).text}")
