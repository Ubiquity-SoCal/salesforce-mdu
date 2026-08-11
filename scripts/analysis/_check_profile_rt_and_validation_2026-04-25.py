"""
Pre-deploy verification:
  1. Current RT visibility per profile on Opportunity (B2B Vendor, Standard User - Custom, System Administrator)
  2. ErrorConditionFormula text for the 6 active Opportunity validation rules — confirm Business ROE RT won't trip them
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# ── 1. RT visibility per profile via Metadata retrieve ──
print("[1] Querying ProfileRecordTypeVisibility-equivalent via Tooling")
# Tooling API exposes RecordType visibility through a few entities; cleanest is to retrieve profiles
# via Metadata API. But we can approximate via SetupEntityAccess for RT.
profiles_of_interest = ['B2B Vendor', 'Standard User - Custom', 'System Administrator']
prof_map = {}
for pn in profiles_of_interest:
    res = sf.query(f"SELECT Id, Name FROM Profile WHERE Name='{pn}'")
    if res['records']:
        prof_map[pn] = res['records'][0]['Id']
        print(f"  {pn:30s} = {prof_map[pn]}")

# RT IDs from earlier
rts = sf.query("SELECT Id, Name, DeveloperName FROM RecordType WHERE SObjectType='Opportunity'")
rt_id_to_name = {r['Id']: r['DeveloperName'] for r in rts['records']}
print(f"\n  Opportunity RTs: {list(rt_id_to_name.values())}")

# Try to read ProfileLayout style — actually the cleanest is to check via UI API for each user
# Use the profile login via setup audit trail isn't ideal either. Let's use the metadata describe approach:
# Per-profile RT visibility lives in Profile.recordTypeVisibilities. Easiest reliable read is Metadata API retrieve.
# Use the simple_salesforce metadata mod.
print("\n[1b] Retrieving profiles via Metadata API to read recordTypeVisibilities")
import requests, base64, zipfile, io as bio, time
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


INSTANCE = sf.sf_instance
SESSION = sf.session_id
META_URL = f"https://{INSTANCE}/services/Soap/m/59.0"

# Build retrieve request
members = '\n'.join(f'    <members>{p}</members>' for p in profiles_of_interest)
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
          <types>
{members}
            <name>Profile</name>
          </types>
          <version>59.0</version>
        </met:unpackaged>
      </met:retrieveRequest>
    </met:retrieve>
  </soapenv:Body>
</soapenv:Envelope>"""

hdrs = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "retrieve"}
r = requests.post(META_URL, data=retrieve_xml, headers=hdrs)
ns = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "met": "http://soap.sforce.com/2006/04/metadata"}
root = ET.fromstring(r.text)
async_id = root.find(".//met:id", ns).text
print(f"  Retrieve async ID: {async_id}")

# Poll
for i in range(30):
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
    done = root.find(".//met:done", ns)
    if done is not None and done.text == "true":
        zip_b64 = root.find(".//met:zipFile", ns).text
        break
    print(f"  ...polling ({i+1})")
else:
    print("  TIMEOUT")
    sys.exit(1)

# Extract profile XMLs
zip_bytes = base64.b64decode(zip_b64)
zf = zipfile.ZipFile(bio.BytesIO(zip_bytes))
print("\n  Files:", zf.namelist())

ns_p = {"sf": "http://soap.sforce.com/2006/04/metadata"}
print("\n[1c] RT visibility per profile:")
for fn in zf.namelist():
    if fn.endswith(".profile"):
        content = zf.read(fn).decode("utf-8")
        proot = ET.fromstring(content)
        prof_name = fn.split("/")[-1].replace(".profile", "")
        print(f"\n  {prof_name}:")
        for rtv in proot.findall("sf:recordTypeVisibilities", ns_p):
            rt_el = rtv.find("sf:recordType", ns_p)
            vis_el = rtv.find("sf:visible", ns_p)
            def_el = rtv.find("sf:default", ns_p)
            rt = rt_el.text if rt_el is not None else "?"
            if rt.startswith("Opportunity."):
                print(f"    {rt:40s}  visible={vis_el.text if vis_el is not None else '?'}  default={def_el.text if def_el is not None else '?'}")

# ── 2. Validation rule formulas ──
print("\n[2] Validation rule formulas on Opportunity")
vrs = sf.toolingexecute(
    "query/?q=" + "SELECT+Id,ValidationName,Active,ErrorConditionFormula,ErrorMessage+FROM+ValidationRule+WHERE+EntityDefinition.QualifiedApiName='Opportunity'+AND+Active=true"
)
for v in vrs.get('records', []):
    print(f"\n  {v['ValidationName']}:")
    print(f"    Formula: {v['ErrorConditionFormula']}")
    print(f"    Message: {v['ErrorMessage']}")
