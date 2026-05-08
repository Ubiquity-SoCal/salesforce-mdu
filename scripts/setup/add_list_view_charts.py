from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time
import xml.etree.ElementTree as ET

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')

base_url = f'https://{sf.sf_instance}'

# Deploy two new list view charts via Metadata API
# 1. Deals by Stage (Count)
# 2. Units by Stage (Sum of Units__c)

object_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <listViews>
        <fullName>All_MDU_Deals</fullName>
        <columns>Stage_Icon__c</columns>
        <columns>OPPORTUNITY.NAME</columns>
        <columns>ACCOUNT.NAME</columns>
        <columns>OPPORTUNITY.STAGE_NAME</columns>
        <columns>SiteTracker_Project_ID__c</columns>
        <columns>Units__c</columns>
        <columns>Property_City__c</columns>
        <columns>Property_State__c</columns>
        <columns>OPPORTUNITY.CLOSE_DATE</columns>
        <columns>CORE.USERS.FULL_NAME</columns>
        <filterScope>Everything</filterScope>
        <filters>
            <field>OPPORTUNITY.RECORDTYPE</field>
            <operation>equals</operation>
            <value>Opportunity.MDU</value>
        </filters>
        <label>All MDU Deals</label>
    </listViews>
</CustomObject>'''

# List view charts - these are separate metadata
deals_chart_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<ListViewChart xmlns="http://soap.sforce.com/2006/04/metadata">
    <aggregateField>Name</aggregateField>
    <aggregateType>Count</aggregateType>
    <chartType>Donut</chartType>
    <groupingField>StageName</groupingField>
    <listView>All_MDU_Deals</listView>
    <sobjectType>Opportunity</sobjectType>
</ListViewChart>'''

units_chart_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<ListViewChart xmlns="http://soap.sforce.com/2006/04/metadata">
    <aggregateField>Units__c</aggregateField>
    <aggregateType>Sum</aggregateType>
    <chartType>Donut</chartType>
    <groupingField>StageName</groupingField>
    <listView>All_MDU_Deals</listView>
    <sobjectType>Opportunity</sobjectType>
</ListViewChart>'''

package_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Deals_By_Stage</members>
        <members>Units_By_Stage</members>
        <name>ListViewChart</name>
    </types>
    <version>59.0</version>
</Package>'''

# Create deployment zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('listViewCharts/Deals_By_Stage.listViewChart', deals_chart_xml)
    zf.writestr('listViewCharts/Units_By_Stage.listViewChart', units_chart_xml)
zip_b64 = base64.b64encode(buf.getvalue()).decode()

# Deploy via Metadata API
soap_deploy = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:met="http://soap.sforce.com/2006/04/metadata">
  <soap:Header>
    <met:SessionHeader><met:sessionId>{sf.session_id}</met:sessionId></met:SessionHeader>
  </soap:Header>
  <soap:Body>
    <met:deploy>
      <met:ZipFile>{zip_b64}</met:ZipFile>
      <met:DeployOptions>
        <met:singlePackage>true</met:singlePackage>
        <met:rollbackOnError>true</met:rollbackOnError>
      </met:DeployOptions>
    </met:deploy>
  </soap:Body>
</soap:Envelope>'''

print("Deploying list view charts...")
r = requests.post(
    f'{base_url}/services/Soap/m/59.0',
    data=soap_deploy,
    headers={'Content-Type': 'text/xml', 'SOAPAction': 'deploy'}
)

ns = {'met': 'http://soap.sforce.com/2006/04/metadata', 'soap': 'http://schemas.xmlsoap.org/soap/envelope/'}
root = ET.fromstring(r.text)
async_id = root.find('.//met:id', ns)

if async_id is not None:
    print(f"Deploy ID: {async_id.text}")

    # Poll for completion
    for i in range(10):
        time.sleep(3)
        check_xml = f'''<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
          xmlns:met="http://soap.sforce.com/2006/04/metadata">
          <soap:Header>
            <met:SessionHeader><met:sessionId>{sf.session_id}</met:sessionId></met:SessionHeader>
          </soap:Header>
          <soap:Body>
            <met:checkDeployStatus>
              <met:asyncProcessId>{async_id.text}</met:asyncProcessId>
              <met:includeDetails>true</met:includeDetails>
            </met:checkDeployStatus>
          </soap:Body>
        </soap:Envelope>'''

        r2 = requests.post(
            f'{base_url}/services/Soap/m/59.0',
            data=check_xml,
            headers={'Content-Type': 'text/xml', 'SOAPAction': 'checkDeployStatus'}
        )

        root2 = ET.fromstring(r2.text)
        status = root2.find('.//met:status', ns)
        done = root2.find('.//met:done', ns)

        print(f"  Check {i+1}: status={status.text if status is not None else '?'}, done={done.text if done is not None else '?'}")

        if done is not None and done.text == 'true':
            if status is not None and status.text == 'Succeeded':
                print("\nDeploy succeeded!")
            else:
                # Print errors
                print(f"\nDeploy failed with status: {status.text if status is not None else 'unknown'}")
                for msg in root2.findall('.//met:componentFailures', ns):
                    name = msg.find('met:fullName', ns)
                    problem = msg.find('met:problem', ns)
                    print(f"  Error: {name.text if name is not None else '?'}: {problem.text if problem is not None else '?'}")
                # Print full response for debugging
                print("\nFull response:")
                print(r2.text[:3000])
            break
    else:
        print("Timed out waiting for deploy")
else:
    print("No deploy ID returned")
    print(r.text[:2000])
