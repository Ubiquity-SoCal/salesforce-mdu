"""
Add CAMPAIGN.DESCRIPTION as a column on the 'All Active Campaigns' and
'My Active Campaigns' list views.
"""

import requests, base64, io, time, zipfile, re
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]
PASSWORD_TOKEN = (_SF["password"] + _SF["token"])
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"
NS = {"met": "http://soap.sforce.com/2006/04/metadata"}
TARGET_VIEWS = ["AllActiveCampaigns", "MyActiveCampaigns"]


def soap_login():
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body><urn:login><urn:username>{USERNAME}</urn:username><urn:password>{PASSWORD_TOKEN}</urn:password></urn:login></soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post("https://login.salesforce.com/services/Soap/u/" + API_VERSION, data=body,
                      headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"})
    root = ET.fromstring(r.text)
    sid = root.find(".//{urn:partner.soap.sforce.com}sessionId")
    return sid.text if sid is not None else None


def retrieve_campaign(sid):
    inner = f"""
    <met:apiVersion>{API_VERSION}</met:apiVersion>
    <met:unpackaged>
      <met:types>
        <met:members>Campaign.AllActiveCampaigns</met:members>
        <met:members>Campaign.MyActiveCampaigns</met:members>
        <met:name>ListView</met:name>
      </met:types>
    </met:unpackaged>"""
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:retrieve><met:retrieveRequest>{inner}</met:retrieveRequest></met:retrieve></soapenv:Body>
</soapenv:Envelope>"""
    url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION}"
    r = requests.post(url, data=soap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "retrieve"})
    aid = ET.fromstring(r.text).find(".//met:id", NS).text
    for _ in range(20):
        time.sleep(2)
        cs = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkRetrieveStatus><met:asyncProcessId>{aid}</met:asyncProcessId><met:includeZip>true</met:includeZip></met:checkRetrieveStatus></soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=cs, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkRetrieveStatus"})
        if ET.fromstring(cr.text).find(".//met:done", NS).text == "true":
            zel = ET.fromstring(cr.text).find(".//met:zipFile", NS)
            return base64.b64decode(zel.text)
    return None


def deploy(sid, files, desc):
    print(f"  Deploying: {desc}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    url = f"{INSTANCE_URL}/services/Soap/m/{API_VERSION}"
    soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:deploy><met:ZipFile>{b64}</met:ZipFile>
    <met:DeployOptions><met:singlePackage>true</met:singlePackage><met:rollbackOnError>true</met:rollbackOnError></met:DeployOptions>
  </met:deploy></soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(url, data=soap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
    did = ET.fromstring(r.text).find(".//met:id", NS).text
    for _ in range(30):
        time.sleep(2)
        cs = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkDeployStatus><met:asyncProcessId>{did}</met:asyncProcessId><met:includeDetails>true</met:includeDetails></met:checkDeployStatus></soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=cs, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
        root = ET.fromstring(cr.text)
        done = root.find(".//met:done", NS)
        if done is not None and done.text == "true":
            ok = root.find(".//met:success", NS)
            if ok is not None and ok.text == "true":
                print("    OK")
                return True
            print("    FAILED:")
            for el in root.iter():
                t = el.tag.split("}")[-1]
                if t in ("problem", "fullName", "problemType", "componentType"):
                    if el.text: print(f"      {t}: {el.text}")
            return False
    return False


def main():
    sid = soap_login()
    zbytes = retrieve_campaign(sid)
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    obj_xml = None
    obj_path = None
    for n in zf.namelist():
        if n.endswith("Campaign.object"):
            obj_xml = zf.read(n).decode("utf-8")
            obj_path = n
    if not obj_xml:
        print("Campaign.object not in retrieve. Exiting.")
        return

    changes = []
    def process_lv(m):
        block = m.group(0)
        fn_match = re.search(r"<fullName>([^<]+)</fullName>", block)
        fn = fn_match.group(1) if fn_match else "?"
        if fn not in TARGET_VIEWS:
            return block
        if "<columns>CAMPAIGN.DESCRIPTION</columns>" in block:
            changes.append(f"  {fn}: already has DESCRIPTION")
            return block
        # Insert right after <columns>CAMPAIGN.NAME</columns>
        new_block = block.replace(
            "<columns>CAMPAIGN.NAME</columns>",
            "<columns>CAMPAIGN.NAME</columns>\n        <columns>CAMPAIGN.DESCRIPTION</columns>",
            1,
        )
        changes.append(f"  {fn}: DESCRIPTION added")
        return new_block

    new_xml = re.sub(r"<listViews>.*?</listViews>", process_lv, obj_xml, flags=re.DOTALL)
    print("Changes:")
    for c in changes: print(c)
    if new_xml == obj_xml:
        print("Nothing changed.")
        return

    members_xml = "\n".join(f"        <members>Campaign.{v}</members>" for v in TARGET_VIEWS)
    pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
{members_xml}
        <name>ListView</name>
    </types>
    <version>{API_VERSION}</version>
</Package>"""
    deploy(sid, {
        "package.xml": pkg,
        "objects/Campaign.object": new_xml,
    }, "Add DESCRIPTION column to Campaign list views")


if __name__ == "__main__":
    main()
