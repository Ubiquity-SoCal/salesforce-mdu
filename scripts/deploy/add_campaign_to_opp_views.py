"""
Retrieve the 4 main Opportunity list views, add CampaignId as a column (after Stage),
and deploy back. Idempotent: skips if CampaignId column already present.

List views updated:
  - Opportunity.MDU_All
  - Opportunity.MDU_Open
  - Opportunity.BUS_All
  - Opportunity.BUS_Open
"""

import requests
import base64
import io
import time
import zipfile
import re
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]
PASSWORD_TOKEN = (_SF["password"] + _SF["token"])
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "59.0"
NS_META = {"met": "http://soap.sforce.com/2006/04/metadata"}

LIST_VIEWS = ["MDU_All", "MDU_Open", "BUS_All", "BUS_Open"]


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


def retrieve(sid, members):
    """Retrieve ListView metadata for given list view full names (Opportunity.Name)."""
    types_xml = "\n".join(f"      <met:members>{m}</met:members>" for m in members)
    inner = f"""
    <met:apiVersion>{API_VERSION}</met:apiVersion>
    <met:unpackaged>
      <met:types>
{types_xml}
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
    root = ET.fromstring(r.text)
    aid = root.find(".//met:id", NS_META)
    if aid is None:
        print("  retrieve request failed:", r.text[:500])
        return None
    for _ in range(30):
        time.sleep(2)
        csoap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkRetrieveStatus><met:asyncProcessId>{aid.text}</met:asyncProcessId><met:includeZip>true</met:includeZip></met:checkRetrieveStatus></soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=csoap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkRetrieveStatus"})
        cr_root = ET.fromstring(cr.text)
        done = cr_root.find(".//met:done", NS_META)
        if done is not None and done.text == "true":
            zel = cr_root.find(".//met:zipFile", NS_META)
            if zel is not None and zel.text:
                return base64.b64decode(zel.text)
            print("  retrieve returned no zip. Messages:")
            for m in cr_root.iter():
                t = m.tag.split("}")[-1]
                if t in ("problem", "fileName", "problemType"):
                    if m.text:
                        print(f"    {t}: {m.text}")
            return None
    print("  retrieve timeout")
    return None


def deploy(sid, files, desc):
    print(f"\n  Deploying: {desc}")
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
  <soapenv:Body>
    <met:deploy>
      <met:ZipFile>{b64}</met:ZipFile>
      <met:DeployOptions><met:singlePackage>true</met:singlePackage><met:rollbackOnError>true</met:rollbackOnError></met:DeployOptions>
    </met:deploy>
  </soapenv:Body>
</soapenv:Envelope>"""
    r = requests.post(url, data=soap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "deploy"})
    root = ET.fromstring(r.text)
    did = root.find(".//met:id", NS_META)
    if did is None:
        print("    deploy request failed:", r.text[:500])
        return False
    for _ in range(30):
        time.sleep(2)
        csoap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soapenv:Header><met:SessionHeader><met:sessionId>{sid}</met:sessionId></met:SessionHeader></soapenv:Header>
  <soapenv:Body><met:checkDeployStatus><met:asyncProcessId>{did.text}</met:asyncProcessId><met:includeDetails>true</met:includeDetails></met:checkDeployStatus></soapenv:Body>
</soapenv:Envelope>"""
        cr = requests.post(url, data=csoap, headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "checkDeployStatus"})
        cr_root = ET.fromstring(cr.text)
        done = cr_root.find(".//met:done", NS_META)
        if done is not None and done.text == "true":
            ok = cr_root.find(".//met:success", NS_META)
            if ok is not None and ok.text == "true":
                print("    OK")
                return True
            print("    FAILED details:")
            for el in cr_root.iter():
                t = el.tag.split("}")[-1]
                if t in ("problem", "fullName", "problemType", "componentType", "fileName"):
                    if el.text:
                        print(f"      {t}: {el.text}")
            return False
    print("    timeout")
    return False


def add_campaign_column(xml_str):
    """Insert <columns>CampaignId</columns> after StageName column. If already present, return None."""
    # Normalize: strip namespaces for easier matching, then rebuild
    if "<columns>CampaignId</columns>" in xml_str:
        return None
    # Insert after <columns>STAGE_NAME</columns>
    if "<columns>STAGE_NAME</columns>" in xml_str:
        return xml_str.replace(
            "<columns>STAGE_NAME</columns>",
            "<columns>STAGE_NAME</columns>\n    <columns>CampaignId</columns>",
            1,
        )
    # Fallback: insert after first <columns> block
    return re.sub(
        r"(<columns>[^<]+</columns>)",
        r"\1\n    <columns>CampaignId</columns>",
        xml_str,
        count=1,
    )


def main():
    sid = soap_login()
    if not sid:
        print("login failed")
        return

    members = [f"Opportunity.{v}" for v in LIST_VIEWS]
    print(f"Retrieving {len(members)} list views...")
    zbytes = retrieve(sid, members)
    if not zbytes:
        return

    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    # Extract the Opportunity.object XML (ListViews come bundled inside it)
    obj_path = None
    for name in zf.namelist():
        if name.endswith("Opportunity.object"):
            obj_path = name
            break
    if not obj_path:
        print("No Opportunity.object in retrieve result.")
        return

    obj_xml = zf.read(obj_path).decode("utf-8")

    # Find each <listViews> block and add CAMPAIGN column after STAGE_NAME if missing
    # Use a simple regex-based in-place edit since we want to preserve everything else.
    changes = []
    def process_listview(match):
        block = match.group(0)
        # Extract fullName
        fn_match = re.search(r"<fullName>([^<]+)</fullName>", block)
        fn = fn_match.group(1) if fn_match else "?"
        if fn not in LIST_VIEWS:
            return block  # not one we're targeting
        if "<columns>CampaignId</columns>" in block:
            changes.append(f"  {fn}: already has CAMPAIGN, skipping")
            return block
        if "<columns>STAGE_NAME</columns>" in block:
            new_block = block.replace(
                "<columns>STAGE_NAME</columns>",
                "<columns>STAGE_NAME</columns>\n        <columns>CampaignId</columns>",
                1,
            )
        else:
            # insert after first <columns>
            new_block = re.sub(
                r"(<columns>[^<]+</columns>)",
                r"\1\n        <columns>CampaignId</columns>",
                block,
                count=1,
            )
        changes.append(f"  {fn}: CAMPAIGN column added")
        return new_block

    new_obj_xml = re.sub(
        r"<listViews>.*?</listViews>",
        process_listview,
        obj_xml,
        flags=re.DOTALL,
    )

    print("\nChanges:")
    for c in changes:
        print(c)

    if new_obj_xml == obj_xml:
        print("\nNo changes needed. Done.")
        return

    # Deploy: only ship the ListView members we changed
    lv_members = [f"Opportunity.{v}" for v in LIST_VIEWS]
    pkg = f"""<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
  <types>
{chr(10).join(f'    <members>{m}</members>' for m in lv_members)}
    <name>ListView</name>
  </types>
  <version>{API_VERSION}</version>
</Package>"""

    deploy(sid, {
        "package.xml": pkg,
        "objects/Opportunity.object": new_obj_xml,
    }, "Add CAMPAIGN column to Opp list views")


if __name__ == "__main__":
    main()
