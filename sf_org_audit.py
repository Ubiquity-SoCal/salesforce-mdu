"""
Salesforce Org Audit Script
Authenticates via SOAP, then queries metadata for:
- Opportunity: all fields, types, picklist values, Stage values, record types
- Account: custom fields, record types
- Contact: custom fields, record types
- Lightning Apps list
- Page layout info
"""

import requests
import xml.etree.ElementTree as ET
import json
import sys

# ─── Configuration ───────────────────────────────────────────────────────────
LOGIN_URL = "https://login.salesforce.com/services/Soap/u/59.0"
USERNAME = "cass1@ubiquitygp.com"
PASSWORD_TOKEN = "Karate88!Ktc1n9mLmD9vwEcVcl45q0iAD"
API_VERSION = "v59.0"

# ─── SOAP Login ──────────────────────────────────────────────────────────────
def soap_login():
    soap_body = f"""<?xml version="1.0" encoding="utf-8" ?>
    <env:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
      <env:Body>
        <n1:login xmlns:n1="urn:partner.soap.sforce.com">
          <n1:username>{USERNAME}</n1:username>
          <n1:password>{PASSWORD_TOKEN}</n1:password>
        </n1:login>
      </env:Body>
    </env:Envelope>"""

    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "SOAPAction": "login"
    }

    resp = requests.post(LOGIN_URL, data=soap_body, headers=headers)
    if resp.status_code != 200:
        print(f"Login failed ({resp.status_code}):")
        print(resp.text[:2000])
        sys.exit(1)

    # Parse the SOAP response
    ns = {
        'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
        'sf': 'urn:partner.soap.sforce.com'
    }
    root = ET.fromstring(resp.text)
    result = root.find('.//sf:loginResponse/sf:result', ns)
    if result is None:
        # Try to find fault
        fault = root.find('.//soapenv:Body/soapenv:Fault/faultstring', ns)
        if fault is not None:
            print(f"Login fault: {fault.text}")
        else:
            print("Could not parse login response:")
            print(resp.text[:2000])
        sys.exit(1)

    session_id = result.find('sf:sessionId', ns).text
    server_url = result.find('sf:serverUrl', ns).text
    # Extract instance URL from server URL
    # server_url looks like https://instance.salesforce.com/services/Soap/u/59.0/00D...
    instance_url = '/'.join(server_url.split('/')[:3])
    print(f"Logged in successfully.")
    print(f"Instance URL: {instance_url}")
    return session_id, instance_url


def rest_get(instance_url, session_id, path):
    """Make a REST API GET request."""
    url = f"{instance_url}/services/data/{API_VERSION}{path}"
    headers = {"Authorization": f"Bearer {session_id}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"  REST GET {path} failed ({resp.status_code}): {resp.text[:500]}")
        return None
    return resp.json()


def describe_object(instance_url, session_id, obj_name):
    """Get full describe for an sObject."""
    return rest_get(instance_url, session_id, f"/sobjects/{obj_name}/describe")


def print_separator(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def print_fields(fields, custom_only=False):
    """Print field details in a readable format."""
    filtered = fields
    if custom_only:
        filtered = [f for f in fields if f.get('custom', False)]

    if not filtered:
        print("  (none)")
        return

    # Sort alphabetically
    filtered.sort(key=lambda f: f['name'])

    for f in filtered:
        label = f.get('label', '')
        ftype = f.get('type', '')
        custom_tag = " [CUSTOM]" if f.get('custom') else ""
        required = " [REQUIRED]" if not f.get('nillable', True) and f.get('createable', True) else ""
        print(f"  {f['name']:50s} {ftype:20s} {label}{custom_tag}{required}")

        # Print picklist values if any
        if f.get('picklistValues'):
            for pv in f['picklistValues']:
                active = "" if pv.get('active', True) else " (INACTIVE)"
                default = " *DEFAULT*" if pv.get('defaultValue', False) else ""
                print(f"      -> {pv['value']}{active}{default}")


def print_record_types(record_types):
    """Print record type info."""
    if not record_types:
        print("  No record types configured (using Master only)")
        return
    for rt in record_types:
        default = " [DEFAULT]" if rt.get('defaultRecordTypeMapping', False) else ""
        active = "" if rt.get('active', True) else " (INACTIVE)"
        print(f"  {rt['name']:40s} ID: {rt.get('recordTypeId', 'N/A')}{default}{active}")
        if rt.get('developerName'):
            print(f"      Developer Name: {rt['developerName']}")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    session_id, instance_url = soap_login()

    # ── 1. OPPORTUNITY ───────────────────────────────────────────────────────
    print_separator("OPPORTUNITY OBJECT")
    opp = describe_object(instance_url, session_id, "Opportunity")
    if opp:
        fields = opp.get('fields', [])
        std_fields = [f for f in fields if not f.get('custom')]
        cust_fields = [f for f in fields if f.get('custom')]

        print(f"\n  Total fields: {len(fields)} ({len(std_fields)} standard, {len(cust_fields)} custom)")

        print(f"\n--- Standard Fields ({len(std_fields)}) ---")
        print_fields(std_fields)

        print(f"\n--- Custom Fields ({len(cust_fields)}) ---")
        print_fields(cust_fields)

        # Stage picklist specifically
        stage_field = next((f for f in fields if f['name'] == 'StageName'), None)
        if stage_field:
            print(f"\n--- Stage Picklist Values ---")
            for pv in stage_field.get('picklistValues', []):
                active = "" if pv.get('active', True) else " (INACTIVE)"
                default = " *DEFAULT*" if pv.get('defaultValue', False) else ""
                print(f"  {pv['value']}{active}{default}")

        # Record Types
        print(f"\n--- Opportunity Record Types ---")
        print_record_types(opp.get('recordTypeInfos', []))

    # ── 2. ACCOUNT ───────────────────────────────────────────────────────────
    print_separator("ACCOUNT OBJECT (Custom Fields & Record Types)")
    acct = describe_object(instance_url, session_id, "Account")
    if acct:
        fields = acct.get('fields', [])
        cust_fields = [f for f in fields if f.get('custom')]
        print(f"\n  Total fields: {len(fields)} (showing {len(cust_fields)} custom)")

        print(f"\n--- Custom Fields ---")
        print_fields(cust_fields)

        print(f"\n--- Account Record Types ---")
        print_record_types(acct.get('recordTypeInfos', []))

    # ── 3. CONTACT ───────────────────────────────────────────────────────────
    print_separator("CONTACT OBJECT (Custom Fields & Record Types)")
    con = describe_object(instance_url, session_id, "Contact")
    if con:
        fields = con.get('fields', [])
        cust_fields = [f for f in fields if f.get('custom')]
        print(f"\n  Total fields: {len(fields)} (showing {len(cust_fields)} custom)")

        print(f"\n--- Custom Fields ---")
        print_fields(cust_fields)

        print(f"\n--- Contact Record Types ---")
        print_record_types(con.get('recordTypeInfos', []))

    # ── 4. LIGHTNING APPS ────────────────────────────────────────────────────
    print_separator("LIGHTNING APPS (AppSwitcher)")
    apps = rest_get(instance_url, session_id, "")
    # The appMenu endpoint is slightly different path
    app_url = f"{instance_url}/services/data/{API_VERSION}/appMenu/AppSwitcher"
    headers = {"Authorization": f"Bearer {session_id}"}
    resp = requests.get(app_url, headers=headers)
    if resp.status_code == 200:
        app_data = resp.json()
        app_items = app_data.get('appMenuItems', [])
        print(f"\n  Found {len(app_items)} apps:\n")
        for app in app_items:
            app_type = app.get('type', 'Unknown')
            print(f"  {app.get('label', 'N/A'):40s} Type: {app_type:20s} DevName: {app.get('name', 'N/A')}")
            if app.get('description'):
                print(f"      Description: {app['description']}")
    else:
        print(f"  AppSwitcher request failed ({resp.status_code}): {resp.text[:500]}")

    # ── 5. PAGE LAYOUTS ──────────────────────────────────────────────────────
    print_separator("PAGE LAYOUTS")
    print("\nChecking page layouts via describe for each object...\n")

    # Tooling API approach - query Layout object
    tooling_url = f"{instance_url}/services/data/{API_VERSION}/tooling/query"
    headers = {"Authorization": f"Bearer {session_id}"}

    for obj_name in ["Opportunity", "Account", "Contact"]:
        query = f"SELECT Id, Name, TableEnumOrId FROM Layout WHERE TableEnumOrId = '{obj_name}'"
        resp = requests.get(tooling_url, params={"q": query}, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            records = data.get('records', [])
            print(f"  {obj_name} Layouts ({len(records)}):")
            for rec in records:
                print(f"    - {rec.get('Name', 'N/A')}  (ID: {rec.get('Id', 'N/A')})")
        else:
            print(f"  {obj_name}: Tooling query failed ({resp.status_code})")
            # Fallback: check describe layouts
            desc = describe_object(instance_url, session_id, obj_name)
            if desc:
                for rt in desc.get('recordTypeInfos', []):
                    layout_url_path = f"/sobjects/{obj_name}/describe/layouts/{rt.get('recordTypeId', '')}"
                    layout = rest_get(instance_url, session_id, layout_url_path)
                    if layout:
                        print(f"    Layout for RT '{rt['name']}': found")
        print()

    # ── 6. Quick summary of all custom objects too ───────────────────────────
    print_separator("BONUS: CUSTOM OBJECTS IN ORG")
    sobjects = rest_get(instance_url, session_id, "/sobjects")
    if sobjects:
        custom_objs = [s for s in sobjects.get('sobjects', []) if s.get('custom')]
        print(f"\n  Found {len(custom_objs)} custom objects:\n")
        for obj in sorted(custom_objs, key=lambda x: x['name']):
            print(f"  {obj['name']:50s} Label: {obj.get('label', 'N/A')}")

    print(f"\n{'='*80}")
    print("  AUDIT COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
