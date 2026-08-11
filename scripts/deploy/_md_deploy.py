"""Shared Metadata-API deploy helper for the 2026-06-17 MDU Agreements Tracker build.
Zips a metadata package and deploys via the Metadata REST deployRequest endpoint.
Reused by every deploy script in this build so the deploy logic lives in one place."""
import os, io, json, time, base64, zipfile, requests
from collections import OrderedDict
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


V = "59.0"
_FALLBACK = dict(username=_SF["username"], password=_SF["password"],
                 security_token=_SF["token"])


def connect():
    """Salesforce client: prefer SF_SESSION_ID env (CI/daily run), else inline creds."""
    if os.environ.get("SF_SESSION_ID"):
        return Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL",
                          "https://fun-power-747.my.salesforce.com"),
                          session_id=os.environ["SF_SESSION_ID"])
    return Salesforce(**_FALLBACK)


def deploy(sf, files, members_types, label, check_only=False):
    """files: {zip_path: xml_content}; members_types: [(member, metaType), ...].
    Members are grouped by type into one <types> block each (valid package.xml)."""
    grouped = OrderedDict()
    for m, t in members_types:
        grouped.setdefault(t, []).append(m)
    types_xml = "".join("<types>" + "".join(f"<members>{m}</members>" for m in ms)
                        + f"<name>{t}</name></types>" for t, ms in grouped.items())
    pkg = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<Package xmlns="http://soap.sforce.com/2006/04/metadata">'
           f'{types_xml}<version>{V}</version></Package>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg)
        for path, content in files.items():
            zf.writestr(path, content)
    instance = f"https://{sf.sf_instance}"
    url = f"{instance}/services/data/v{V}/metadata/deployRequest"
    raw = base64.b64encode(buf.getvalue()).decode()
    b64 = "\r\n".join(raw[i:i + 76] for i in range(0, len(raw), 76))  # wrap for multipart
    body = {"deployOptions": {"checkOnly": check_only, "ignoreWarnings": True,
                              "rollbackOnError": True, "singlePackage": True}}
    bnd = "----B"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\n"
               f"Content-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
               f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\n"
               f"Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n"
               f"{b64}\r\n--{bnd}--")
    hdr = {"Authorization": f"Bearer {sf.session_id}",
           "Content-Type": f"multipart/form-data; boundary={bnd}"}
    r = requests.post(url, headers=hdr, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json()["id"]
    for i in range(40):
        time.sleep(3)
        res = requests.get(f"{url}/{did}?includeDetails=true",
                           headers={"Authorization": f"Bearer {sf.session_id}"}).json()
        st = res.get("deployResult", {}).get("status", "?")
        print(f"  [{label}] poll {i + 1}: {st}")
        if st == "Succeeded":
            return True
        if st in ("Failed", "Canceled", "SucceededPartial"):
            for f in (res.get("deployResult", {}).get("details", {})
                      .get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    print(f"  [{label}] timed out"); return False
