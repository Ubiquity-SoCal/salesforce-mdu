from simple_salesforce import Salesforce
import requests, json, base64, io, zipfile, time

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

# Shared related list XML snippets
contacts_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Contact__c</fields>
        <fields>Role__c</fields>
        <relatedList>Opportunity_Contact__c.Opportunity__c</relatedList>
    </relatedLists>"""

agreements_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Agreement_Type__c</fields>
        <fields>Status__c</fields>
        <fields>Signed_Date__c</fields>
        <fields>IronClad_ID__c</fields>
        <relatedList>Agreement__c.Opportunity__c</relatedList>
    </relatedLists>"""

sitetracker_rl = """
    <relatedLists>
        <fields>NAME</fields>
        <fields>Site_Name__c</fields>
        <fields>Build_Status__c</fields>
        <fields>Site_Status__c</fields>
        <fields>PAL_Signed_Date__c</fields>
        <fields>Activation_Forecast__c</fields>
        <relatedList>SiteTracker_Project__c.Opportunity__c</relatedList>
    </relatedLists>"""

notes_rl = """
    <relatedLists>
        <relatedList>RelatedNoteList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedContentNoteList</relatedList>
    </relatedLists>
    <relatedLists>
        <relatedList>RelatedFileList</relatedList>
    </relatedLists>"""

footer = """
    <showHighlightsPanel>false</showHighlightsPanel>
    <showRunAssignmentRulesCheckbox>false</showRunAssignmentRulesCheckbox>
    <showSubmitAndAttachButton>false</showSubmitAndAttachButton>
</Layout>"""

# Business Opportunity Layout
business_layout_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <layoutSections>
        <label>Opportunity Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Required</behavior><field>Name</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>AccountId</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Contact__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Unit__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Type</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Market_Sales_Lead__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Loss_Reason__c</field></layoutItems>
            <layoutItems><behavior>Readonly</behavior><field>Notes_Count__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>OwnerId</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>CloseDate</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>StageName</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Probability</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Amount</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Additional Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>NextStep</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Description</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>LeadSource</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Property Details</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Property_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Category__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Build_Type__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>ISP Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Prospective_ISP__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Confirmed_ISP__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <customLabel>true</customLabel>
        <label>System Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>CreatedById</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>LastModifiedById</field></layoutItems>
        </layoutColumns>
    </layoutSections>""" + contacts_rl + agreements_rl + notes_rl + footer

# MDU Opportunity Layout
mdu_layout_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Layout xmlns="http://soap.sforce.com/2006/04/metadata">
    <layoutSections>
        <label>Opportunity Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Required</behavior><field>Name</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>AccountId</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Contact__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Type</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>CampaignId</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Budget_Confirmed__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Discovery_Completed__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>ROI_Analysis_Completed__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Loss_Reason__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Special_Project__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Market_Sales_Lead__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Agreement_Name__c</field></layoutItems>
            <layoutItems><behavior>Readonly</behavior><field>Notes_Count__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>OwnerId</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>CloseDate</field></layoutItems>
            <layoutItems><behavior>Required</behavior><field>StageName</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Probability</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Amount</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Additional Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>NextStep</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Description</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>LeadSource</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Property Details</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Units__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Category__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Build_Type__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Address__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_City__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_State__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>Property_Zip__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>ISP Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Prospective_ISP__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Confirmed_ISP__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Integration Links</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>SiteTracker_Project_ID__c</field></layoutItems>
            <layoutItems><behavior>Edit</behavior><field>SiteTracker_URL__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>IronClad_URL__c</field></layoutItems>
        </layoutColumns>
    </layoutSections>
    <layoutSections>
        <label>Migration Reference</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Edit</behavior><field>Monday_Item_ID__c</field></layoutItems>
        </layoutColumns>
        <layoutColumns/>
    </layoutSections>
    <layoutSections>
        <customLabel>true</customLabel>
        <label>System Information</label>
        <style>TwoColumnsTopToBottom</style>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>CreatedById</field></layoutItems>
        </layoutColumns>
        <layoutColumns>
            <layoutItems><behavior>Readonly</behavior><field>LastModifiedById</field></layoutItems>
        </layoutColumns>
    </layoutSections>""" + contacts_rl + agreements_rl + sitetracker_rl + notes_rl + footer

package_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>Opportunity-MDU Opportunity Layout</members>
        <members>Opportunity-Business Opportunity Layout</members>
        <name>Layout</name>
    </types>
    <version>59.0</version>
</Package>"""

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('package.xml', package_xml)
    zf.writestr('layouts/Opportunity-MDU Opportunity Layout.layout', mdu_layout_xml)
    zf.writestr('layouts/Opportunity-Business Opportunity Layout.layout', business_layout_xml)
buf.seek(0)
zip_b64 = base64.b64encode(buf.read()).decode()

deploy_url = f'{sf.base_url}metadata/deployRequest'
deploy_body = {
    'deployOptions': {
        'checkOnly': False,
        'ignoreWarnings': True,
        'rollbackOnError': True,
        'singlePackage': True
    }
}
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

headers = {
    'Authorization': f'Bearer {sf.session_id}',
    'Content-Type': f'multipart/form-data; boundary={boundary}'
}
resp = requests.post(deploy_url, headers=headers, data=body_str)
print(f'Deploy: {resp.status_code}')

if resp.status_code == 201:
    deploy_id = resp.json().get('id')
    for i in range(15):
        time.sleep(3)
        check = requests.get(
            f'{deploy_url}/{deploy_id}?includeDetails=true',
            headers={'Authorization': f'Bearer {sf.session_id}'}
        )
        result = check.json()
        status = result.get('deployResult', {}).get('status', 'unknown')
        print(f'  {status}')
        if status in ('Succeeded', 'Failed', 'Canceled'):
            if status == 'Failed':
                details = result.get('deployResult', {}).get('details', {})
                failures = details.get('componentFailures', [])
                if isinstance(failures, dict):
                    failures = [failures]
                for f in failures:
                    print(f'  FAIL: {f.get("fullName")} - {f.get("problem")}')
            break
else:
    print(resp.text[:500])
