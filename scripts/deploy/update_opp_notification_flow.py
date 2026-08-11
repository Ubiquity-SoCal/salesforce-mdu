"""
Update the New_Opportunity_Notification Flow via Metadata API:
1. Add address fields to email body
2. Resolve Property_Unit__c name via Get Records
3. Add Lucas Dixon (ldixon@fiberfirst.com) as CC
"""
from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# The Flow XML with all modifications applied
flow_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>65.0</apiVersion>
    <description>Sends notification when new Opportunity is created. Includes address, property unit name, CC to Lucas Dixon.</description>
    <environments>Default</environments>
    <interviewLabel>New_Opportunity_Notification {!$Flow.CurrentDateTime}</interviewLabel>
    <label>New_Opportunity_Notification</label>
    <processMetadataValues>
        <name>BuilderType</name>
        <value><stringValue>LightningFlowBuilder</stringValue></value>
    </processMetadataValues>
    <processMetadataValues>
        <name>CanvasMode</name>
        <value><stringValue>AUTO_LAYOUT_CANVAS</stringValue></value>
    </processMetadataValues>
    <processMetadataValues>
        <name>OriginBuilderType</name>
        <value><stringValue>LightningFlowBuilder</stringValue></value>
    </processMetadataValues>
    <processType>AutoLaunchedFlow</processType>
    <status>Active</status>

    <!-- Start: Record-triggered on Opportunity After Save (Create and Update) -->
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector>
            <targetReference>Get_Opportunity_Record</targetReference>
        </connector>
        <doesRequireRecordChangedToMeetCriteria>true</doesRequireRecordChangedToMeetCriteria>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Market_Sales_Lead__c</field>
            <operator>NotEqualTo</operator>
            <value><stringValue></stringValue></value>
        </filters>
        <object>Opportunity</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
    </start>

    <!-- Step 1: Get Opportunity Owner name -->
    <recordLookups>
        <name>Get_Opportunity_Record</name>
        <label>Get_Opportunity_OwnerID</label>
        <locationX>50</locationX>
        <locationY>100</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector>
            <targetReference>Get_Opportunity_MarketManager</targetReference>
        </connector>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.OwnerId</elementReference></value>
        </filters>
        <getFirstRecordOnly>true</getFirstRecordOnly>
        <object>User</object>
        <storeOutputAutomatically>true</storeOutputAutomatically>
    </recordLookups>

    <!-- Step 2: Get Market Sales Lead name -->
    <recordLookups>
        <name>Get_Opportunity_MarketManager</name>
        <label>Get_Opportunity_MarketManager</label>
        <locationX>50</locationX>
        <locationY>200</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector>
            <targetReference>Get_Property_Unit</targetReference>
        </connector>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Market_Sales_Lead__c</elementReference></value>
        </filters>
        <getFirstRecordOnly>true</getFirstRecordOnly>
        <object>User</object>
        <storeOutputAutomatically>true</storeOutputAutomatically>
    </recordLookups>

    <!-- Step 3: Get Property Unit name (NEW) -->
    <recordLookups>
        <name>Get_Property_Unit</name>
        <label>Get_Property_Unit</label>
        <locationX>50</locationX>
        <locationY>300</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector>
            <targetReference>New_Opportunity</targetReference>
        </connector>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Property_Unit__c</elementReference></value>
        </filters>
        <getFirstRecordOnly>true</getFirstRecordOnly>
        <object>Property_Unit__c</object>
        <storeOutputAutomatically>true</storeOutputAutomatically>
    </recordLookups>

    <!-- Step 4: Send Email -->
    <actionCalls>
        <name>New_Opportunity</name>
        <label>New_Opportunity</label>
        <locationX>50</locationX>
        <locationY>400</locationY>
        <actionName>emailSimple</actionName>
        <actionType>emailSimple</actionType>
        <flowTransactionModel>CurrentTransaction</flowTransactionModel>
        <inputParameters>
            <name>emailSubject</name>
            <value><stringValue>New Opportunity Created: {!$Record.Name}</stringValue></value>
        </inputParameters>
        <inputParameters>
            <name>emailBody</name>
            <value><stringValue>New Opportunity Created
========================

A new opportunity has been created. Please review the details below:

View Opportunity: https://fun-power-747.lightning.force.com/{!$Record.Id}

Opportunity Name: {!$Record.Name}

Amount: {!$Record.Amount}

Close Date: {!$Record.CloseDate}

Stage: {!$Record.StageName}

Address: {!$Record.Property_Address__c}, {!$Record.Property_City__c}, {!$Record.Property_State__c} {!$Record.Property_Zip__c}

Property Unit: {!Get_Property_Unit.Name}

Probability: {!$Record.Probability}

Type: {!$Record.Type}

Lead Source: {!$Record.LeadSource}

Opportunity Owner: {!Get_Opportunity_Record.Name}

Market Sales Lead: {!Get_Opportunity_MarketManager.Name}

========================
Please review at your earliest convenience.</stringValue></value>
        </inputParameters>
        <inputParameters>
            <name>recipientId</name>
            <value><elementReference>$Record.Market_Sales_Lead__c</elementReference></value>
        </inputParameters>
        <inputParameters>
            <name>ccAddresses</name>
            <value><stringValue>ldixon@fiberfirst.com</stringValue></value>
        </inputParameters>
        <inputParameters>
            <name>senderType</name>
            <value><stringValue>CurrentUser</stringValue></value>
        </inputParameters>
        <inputParameters>
            <name>relatedRecordId</name>
            <value><elementReference>$Record.Id</elementReference></value>
        </inputParameters>
    </actionCalls>
</Flow>"""

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>New_Opportunity_Notification</members>
        <name>Flow</name>
    </types>
    <version>65.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('flows/New_Opportunity_Notification.flow', flow_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f'{sf.base_url}metadata/deployRequest'
deploy_body = {'deployOptions': {'checkOnly': False, 'ignoreWarnings': True, 'rollbackOnError': True, 'singlePackage': True}}
boundary = '----DeployBoundary'
body_str = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
    f'{json.dumps(deploy_body)}\r\n'
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="deploy.zip"\r\n'
    f'Content-Type: application/zip\r\n'
    f'Content-Transfer-Encoding: base64\r\n\r\n'
    f'{zip_b64}\r\n'
    f'--{boundary}--'
)

print("Deploying updated New_Opportunity_Notification Flow...")
resp = requests.post(
    deploy_url,
    headers={'Authorization': f'Bearer {sf.session_id}', 'Content-Type': f'multipart/form-data; boundary={boundary}'},
    data=body_str
)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(20):
        time.sleep(3)
        check = requests.get(
            f'{deploy_url}/{deploy_id}?includeDetails=true',
            headers={'Authorization': f'Bearer {sf.session_id}'}
        )
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  Poll {i+1}: {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict):
                    failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            elif status == 'Succeeded':
                print('\nSUCCESS — Flow updated!')
                print('Changes:')
                print('  1. Address fields added to email body')
                print('  2. Property Unit now resolves to name via Get Records')
                print('  3. Lucas Dixon (ldixon@fiberfirst.com) CC\'d on all notifications')
            break
else:
    print(resp.text[:500])
