from simple_salesforce import Salesforce
import requests, json

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')
soap_url = f"https://{sf.sf_instance}/services/Soap/m/59.0"

# Try updateMetadata via SOAP to set the picklist values
new_roles = [
    "Property Manager", "Property Owner", "Leasing Contact", "HOA Contact",
    "General Contractor", "Developer", "Legal Contact", "Broker", "Other"
]

values_xml = ""
for role in new_roles:
    values_xml += f"""
            <standardValue>
                <fullName>{role}</fullName>
                <default>false</default>
                <label>{role}</label>
                <isActive>true</isActive>
            </standardValue>"""

soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:met="http://soap.sforce.com/2006/04/metadata">
    <soapenv:Header>
        <met:SessionHeader>
            <met:sessionId>{sf.session_id}</met:sessionId>
        </met:SessionHeader>
    </soapenv:Header>
    <soapenv:Body>
        <met:updateMetadata>
            <met:metadata xsi:type="met:StandardValueSet" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <met:fullName>OpptyContactRole</met:fullName>
                <sorted>false</sorted>{values_xml}
            </met:metadata>
        </met:updateMetadata>
    </soapenv:Body>
</soapenv:Envelope>"""

print("Updating OpptyContactRole via SOAP Metadata API...")
resp = requests.post(
    soap_url,
    headers={
        'Content-Type': 'text/xml; charset=UTF-8',
        'SOAPAction': 'updateMetadata'
    },
    data=soap_body
)
print(f'Status: {resp.status_code}')
print(resp.text[:2000])

# If that fails, try with ContractContactRole
if 'INVALID' in resp.text or 'error' in resp.text.lower():
    # Also try listing what's available
    list_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:met="http://soap.sforce.com/2006/04/metadata">
    <soapenv:Header>
        <met:SessionHeader>
            <met:sessionId>{sf.session_id}</met:sessionId>
        </met:SessionHeader>
    </soapenv:Header>
    <soapenv:Body>
        <met:listMetadata>
            <met:queries>
                <met:type>StandardValueSet</met:type>
            </met:queries>
            <met:asOfVersion>59.0</met:asOfVersion>
        </met:listMetadata>
    </soapenv:Body>
</soapenv:Envelope>"""

    print("\nListing all StandardValueSets...")
    resp2 = requests.post(
        soap_url,
        headers={'Content-Type': 'text/xml; charset=UTF-8', 'SOAPAction': 'listMetadata'},
        data=list_body
    )
    print(f'List: {resp2.status_code}')
    # Extract fullName values from response
    import re
    names = re.findall(r'<fullName>([^<]+)</fullName>', resp2.text)
    for n in sorted(names):
        if 'contact' in n.lower() or 'role' in n.lower() or 'oppty' in n.lower() or 'opp' in n.lower():
            print(f'  ** {n}')
        # else:
        #     print(f'     {n}')
    print(f'  Total: {len(names)} standard value sets')

# Verify current state regardless
print("\nCurrent Role picklist values:")
desc = sf.OpportunityContactRole.describe()
for f in desc['fields']:
    if f['name'] == 'Role':
        for pv in f['picklistValues']:
            print(f"  {pv['value']} (active: {pv['active']})")
