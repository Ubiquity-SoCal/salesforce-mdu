"""
Salesforce Schema Explorer
- Authenticates via SOAP API
- Lists all custom objects and their fields
- Checks standard objects in use
- Attempts to retrieve Lightning App metadata
"""

import requests
import json
from xml.etree import ElementTree as ET

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# ── Config ──────────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = _SF["username"]
PASSWORD_TOKEN = (_SF["password"] + _SF["token"])
INSTANCE_URL = "https://fun-power-747.my.salesforce.com"
API_VERSION = "v59.0"

# ── Step 1: SOAP Login ─────────────────────────────────────────────────
def soap_login():
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:urn="urn:partner.soap.sforce.com">
  <soapenv:Body>
    <urn:login>
      <urn:username>{USERNAME}</urn:username>
      <urn:password>{PASSWORD_TOKEN}</urn:password>
    </urn:login>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "login",
    }

    print("Authenticating via SOAP API...")
    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)

    if resp.status_code != 200:
        print(f"SOAP login failed ({resp.status_code}):")
        print(resp.text[:2000])
        return None, None

    # Parse XML response
    ns = {
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "sf": "urn:partner.soap.sforce.com",
    }
    root = ET.fromstring(resp.text)

    # Check for fault
    fault = root.find(".//soapenv:Fault", ns)
    if fault is not None:
        print("SOAP Fault:", ET.tostring(fault, encoding="unicode"))
        return None, None

    session_id = root.find(".//sf:sessionId", ns)
    server_url = root.find(".//sf:serverUrl", ns)

    if session_id is None:
        print("Could not find sessionId in response.")
        print(resp.text[:2000])
        return None, None

    print(f"Authenticated successfully.")
    print(f"Server URL: {server_url.text}")
    return session_id.text, server_url.text


def rest_get(session_id, path):
    """Helper for REST API GET requests."""
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}{path}"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"  REST error {resp.status_code} for {path}: {resp.text[:500]}")
        return None
    return resp.json()


# ── Step 2: Explore SObjects ───────────────────────────────────────────
def explore_objects(session_id):
    print("\n" + "=" * 70)
    print("FETCHING ALL SOBJECTS")
    print("=" * 70)

    data = rest_get(session_id, "/sobjects/")
    if not data:
        return

    all_sobjects = data.get("sobjects", [])
    print(f"Total SObjects in org: {len(all_sobjects)}")

    # ── Custom Objects ──────────────────────────────────────────────
    custom_objects = [
        obj for obj in all_sobjects
        if obj["name"].endswith("__c") and obj.get("queryable", False)
    ]

    print(f"\n{'=' * 70}")
    print(f"CUSTOM OBJECTS ({len(custom_objects)})")
    print(f"{'=' * 70}")

    for obj in sorted(custom_objects, key=lambda o: o["name"]):
        label = obj.get("label", "")
        name = obj["name"]
        print(f"\n  {name}  ({label})")
        print(f"    Createable: {obj.get('createable')}  |  "
              f"Updateable: {obj.get('updateable')}  |  "
              f"Deletable: {obj.get('deletable')}")

        # Get fields for this custom object
        describe = rest_get(session_id, f"/sobjects/{name}/describe/")
        if describe:
            fields = describe.get("fields", [])
            print(f"    Fields ({len(fields)}):")
            for f in sorted(fields, key=lambda x: x["name"]):
                ftype = f["type"]
                flabel = f["label"]
                fname = f["name"]
                req = " [required]" if not f.get("nillable", True) and f.get("createable", False) else ""
                ref = ""
                if f.get("referenceTo"):
                    ref = f" -> {', '.join(f['referenceTo'])}"
                print(f"      - {fname} ({ftype}) \"{flabel}\"{req}{ref}")

            # Record types
            record_types = describe.get("recordTypeInfos", [])
            if record_types and len(record_types) > 1:
                print(f"    Record Types:")
                for rt in record_types:
                    if rt.get("name") != "Master":
                        print(f"      - {rt['name']} ({rt.get('recordTypeId', 'N/A')})")

    # ── Standard Objects ────────────────────────────────────────────
    standard_names = ["Account", "Contact", "Opportunity", "Lead", "Case"]
    print(f"\n{'=' * 70}")
    print("STANDARD OBJECTS IN USE")
    print(f"{'=' * 70}")

    for sname in standard_names:
        obj_info = next((o for o in all_sobjects if o["name"] == sname), None)
        if not obj_info:
            print(f"\n  {sname}: NOT FOUND in org")
            continue

        print(f"\n  {sname}")
        describe = rest_get(session_id, f"/sobjects/{sname}/describe/")
        if describe:
            fields = describe.get("fields", [])
            custom_fields = [f for f in fields if f["name"].endswith("__c")]
            print(f"    Total fields: {len(fields)}  |  Custom fields: {len(custom_fields)}")
            if custom_fields:
                print(f"    Custom fields:")
                for f in sorted(custom_fields, key=lambda x: x["name"]):
                    ftype = f["type"]
                    flabel = f["label"]
                    fname = f["name"]
                    ref = ""
                    if f.get("referenceTo"):
                        ref = f" -> {', '.join(f['referenceTo'])}"
                    print(f"      - {fname} ({ftype}) \"{flabel}\"{ref}")

            # Record count estimate via SOQL
            try:
                count_data = rest_get(session_id, f"/query/?q=SELECT+COUNT()+FROM+{sname}")
                if count_data and "totalSize" in count_data:
                    print(f"    Record count: {count_data['totalSize']}")
            except Exception:
                pass

            # Record types
            record_types = describe.get("recordTypeInfos", [])
            if record_types and len(record_types) > 1:
                print(f"    Record Types:")
                for rt in record_types:
                    if rt.get("name") != "Master":
                        print(f"      - {rt['name']}")


# ── Step 3: Lightning Apps / Installed Packages ────────────────────────
def explore_apps_and_packages(session_id):
    print(f"\n{'=' * 70}")
    print("LIGHTNING APPS (via Tooling API)")
    print(f"{'=' * 70}")

    # Try Tooling API for Lightning apps
    url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tooling/query/"
    headers = {"Authorization": f"Bearer {session_id}", "Accept": "application/json"}

    # CustomApplication query
    query = "SELECT Id, DeveloperName, Label, Description FROM CustomApplication"
    resp = requests.get(url, headers=headers, params={"q": query})
    if resp.status_code == 200:
        apps = resp.json().get("records", [])
        print(f"  Found {len(apps)} Custom Applications:")
        for app in sorted(apps, key=lambda a: a.get("Label", "")):
            desc = app.get("Description") or ""
            desc_str = f' - {desc[:80]}' if desc else ""
            print(f"    - {app.get('Label', 'N/A')} (DeveloperName: {app.get('DeveloperName', 'N/A')}){desc_str}")
    else:
        print(f"  Could not query CustomApplication: {resp.status_code}")
        print(f"  {resp.text[:500]}")

    # Installed packages
    print(f"\n{'=' * 70}")
    print("INSTALLED PACKAGES")
    print(f"{'=' * 70}")

    query2 = "SELECT Id, SubscriberPackage.Name, SubscriberPackage.NamespacePrefix, SubscriberPackageVersion.MajorVersion, SubscriberPackageVersion.MinorVersion FROM InstalledSubscriberPackage"
    resp2 = requests.get(url, headers=headers, params={"q": query2})
    if resp2.status_code == 200:
        pkgs = resp2.json().get("records", [])
        if pkgs:
            print(f"  Found {len(pkgs)} installed packages:")
            for pkg in pkgs:
                sp = pkg.get("SubscriberPackage", {})
                sv = pkg.get("SubscriberPackageVersion", {})
                name = sp.get("Name", "N/A") if sp else "N/A"
                ns = sp.get("NamespacePrefix", "") if sp else ""
                major = sv.get("MajorVersion", "?") if sv else "?"
                minor = sv.get("MinorVersion", "?") if sv else "?"
                ns_str = f" (ns: {ns})" if ns else ""
                print(f"    - {name}{ns_str} v{major}.{minor}")
        else:
            print("  No installed packages found.")
    else:
        print(f"  Could not query packages: {resp2.status_code}")

    # Tabs / custom tabs
    print(f"\n{'=' * 70}")
    print("CUSTOM TABS")
    print(f"{'=' * 70}")

    tabs_url = f"{INSTANCE_URL}/services/data/{API_VERSION}/tabs/"
    resp3 = requests.get(tabs_url, headers=headers)
    if resp3.status_code == 200:
        tabs = resp3.json()
        custom_tabs = [t for t in tabs if t.get("custom", False)]
        print(f"  Total tabs: {len(tabs)}  |  Custom tabs: {len(custom_tabs)}")
        if custom_tabs:
            for t in sorted(custom_tabs, key=lambda x: x.get("label", "")):
                print(f"    - {t.get('label', 'N/A')} ({t.get('sobjectName', t.get('url', 'N/A'))})")
    else:
        print(f"  Could not fetch tabs: {resp3.status_code}")


# ── Main ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id, server_url = soap_login()
    if not session_id:
        print("Authentication failed. Exiting.")
        exit(1)

    explore_objects(session_id)
    explore_apps_and_packages(session_id)

    print(f"\n{'=' * 70}")
    print("EXPLORATION COMPLETE")
    print(f"{'=' * 70}")
