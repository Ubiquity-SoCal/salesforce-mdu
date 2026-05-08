"""
Pre-deploy verification, round 2:
  1. SFU RT usage (count of active Opps, breakdown by Stage and Owner)
  2. How RT visibility is granted in this org (profile vs permset)
  3. Property_Type__c and Sales_Status__c picklist contents
  4. Stale Business stages usage (Ready for Eng / Under Construction / Activation)
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce
from collections import Counter

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

# ── 1. SFU RT usage ──
print("=" * 70)
print("[1] SFU Record Type usage")
print("=" * 70)
rts = sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SObjectType='Opportunity'")
rt_id = {r['DeveloperName']: r['Id'] for r in rts['records']}

sfu_opps = sf.query_all(f"SELECT Id, Name, StageName, Owner.Name, IsClosed, Property_Type__c, CreatedDate FROM Opportunity WHERE RecordTypeId='{rt_id['SFU']}'")
print(f"\nTotal SFU Opps: {sfu_opps['totalSize']}")
if sfu_opps['totalSize']:
    by_stage = Counter(o['StageName'] for o in sfu_opps['records'])
    by_owner = Counter(o['Owner']['Name'] for o in sfu_opps['records'] if o.get('Owner'))
    by_closed = Counter('Closed' if o['IsClosed'] else 'Open' for o in sfu_opps['records'])
    by_proptype = Counter(o.get('Property_Type__c') or '(blank)' for o in sfu_opps['records'])
    print(f"  Open vs Closed: {dict(by_closed)}")
    print(f"  By Stage:")
    for s, c in by_stage.most_common():
        print(f"    {s:30s} {c}")
    print(f"  By Owner:")
    for o, c in by_owner.most_common():
        print(f"    {o:30s} {c}")
    print(f"  By Property_Type:")
    for p, c in by_proptype.most_common():
        print(f"    {p:40s} {c}")

# ── 2. MDU + Business breakdowns ──
print("\n" + "=" * 70)
print("[2] MDU + Business RT counts (for context)")
print("=" * 70)
for rt_name in ['MDU', 'Business']:
    cnt = sf.query(f"SELECT COUNT(Id) c FROM Opportunity WHERE RecordTypeId='{rt_id[rt_name]}'")['records'][0]['c']
    open_cnt = sf.query(f"SELECT COUNT(Id) c FROM Opportunity WHERE RecordTypeId='{rt_id[rt_name]}' AND IsClosed=false")['records'][0]['c']
    print(f"  {rt_name:15s} total={cnt:5d}  open={open_cnt}")

# ── 3. Stale Business stages usage ──
print("\n" + "=" * 70)
print("[3] Stale Business stages usage (Ready for Eng / Under Construction / Activation)")
print("=" * 70)
for stage in ['Ready for Engineering', 'Under Construction', 'Activation', 'Negotiation', 'Construction', 'Qualification', 'Needs Analysis', 'Engineering', 'Proposal']:
    cnt = sf.query_all(f"SELECT Id, RecordType.DeveloperName FROM Opportunity WHERE StageName='{stage}'")
    n = cnt['totalSize']
    if n:
        by_rt = Counter(r['RecordType']['DeveloperName'] for r in cnt['records'])
        print(f"  {stage:30s} total={n}  by RT: {dict(by_rt)}")
    else:
        print(f"  {stage:30s} 0 records")

# ── 4. Property_Type__c picklist ──
print("\n" + "=" * 70)
print("[4] Property_Type__c picklist values")
print("=" * 70)
desc = sf.Opportunity.describe()
for f in desc['fields']:
    if f['name'] == 'Property_Type__c':
        print(f"  Total values: {len(f['picklistValues'])}")
        for v in f['picklistValues']:
            print(f"    {v['value']:40s} active={v['active']!s:5s}")
        break

# ── 5. Sales_Status__c picklist ──
print("\n" + "=" * 70)
print("[5] Sales_Status__c picklist values")
print("=" * 70)
for f in desc['fields']:
    if f['name'] == 'Sales_Status__c':
        print(f"  Total values: {len(f['picklistValues'])}")
        for v in f['picklistValues']:
            print(f"    {v['value']:50s} active={v['active']!s:5s}")
        break

# ── 6. Sales_Status__c usage by Stage ──
print("\n" + "=" * 70)
print("[6] Sales_Status__c usage by Stage")
print("=" * 70)
opps = sf.query_all("SELECT Id, StageName, Sales_Status__c FROM Opportunity WHERE Sales_Status__c != null")
print(f"  Opps with Sales_Status set: {opps['totalSize']}")
combos = Counter((o['StageName'], o['Sales_Status__c']) for o in opps['records'])
for (stage, ss), c in combos.most_common():
    print(f"    {stage:30s} | {ss:40s} {c}")

# ── 7. RT visibility check via Permission Set assignments ──
print("\n" + "=" * 70)
print("[7] Permission Sets that grant RT access on Opportunity")
print("=" * 70)
# RT access lives in PermissionSet via Tooling API as PermissionSetRecordTypeAccess (not a standard object)
# Easier: query SetupEntityAccess for RecordType entities? Actually RT visibility is in Profile.recordTypeVisibilities
# OR PermissionSet.recordTypeVisibilities. Easiest read = retrieve via Metadata API.
import requests, base64, zipfile, io as bio, time
from xml.etree import ElementTree as ET

INSTANCE = sf.sf_instance
SESSION = sf.session_id
META_URL = f"https://{INSTANCE}/services/Soap/m/59.0"

# Get all custom permission set names
psets_query = sf.query("SELECT Name FROM PermissionSet WHERE IsCustom=true AND Name NOT LIKE 'X00%' AND Name NOT LIKE 'sfdc%'")
pset_names = [p['Name'] for p in psets_query['records']]
print(f"  Custom permsets to check: {pset_names}")

members = '\n'.join(f'    <members>{p}</members>' for p in pset_names)
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
            <name>PermissionSet</name>
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
else:
    print("  TIMEOUT")
    sys.exit(1)

zip_bytes = base64.b64decode(zip_b64)
zf = zipfile.ZipFile(bio.BytesIO(zip_bytes))

ns_p = {"sf": "http://soap.sforce.com/2006/04/metadata"}
print("\n  Permission Set RT visibility for Opportunity:")
for fn in zf.namelist():
    if fn.endswith(".permissionset"):
        content = zf.read(fn).decode("utf-8")
        proot = ET.fromstring(content)
        ps_name = fn.split("/")[-1].replace(".permissionset", "")
        opp_rts = []
        for rtv in proot.findall("sf:recordTypeVisibilities", ns_p):
            rt_el = rtv.find("sf:recordType", ns_p)
            vis_el = rtv.find("sf:visible", ns_p)
            rt = rt_el.text if rt_el is not None else "?"
            if rt.startswith("Opportunity."):
                opp_rts.append(f"{rt} (visible={vis_el.text if vis_el is not None else '?'})")
        if opp_rts:
            print(f"\n  {ps_name}:")
            for entry in opp_rts:
                print(f"    {entry}")

# ── 8. Profile RT visibility — also re-pull via direct REST describe-layouts ──
print("\n" + "=" * 70)
print("[8] Profile RT visibility (via /describe/layouts endpoint as System Admin)")
print("=" * 70)
# Use the REST API describe layouts which includes recordTypeMappings (effective access)
hdr = {'Authorization': f'Bearer {sf.session_id}'}
url = f"https://{sf.sf_instance}/services/data/v59.0/sobjects/Opportunity/describe/layouts"
r = requests.get(url, headers=hdr)
if r.status_code == 200:
    data = r.json()
    rtms = data.get('recordTypeMappings', [])
    print(f"  RT mappings visible to current user (cass1, System Admin): {len(rtms)}")
    for rtm in rtms:
        print(f"    {rtm.get('developerName',''):20s} available={rtm.get('available')}  default={rtm.get('defaultRecordTypeMapping')}  layoutId={rtm.get('layoutId')}")
