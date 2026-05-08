"""Generates the Agreement_Niraj_Notifications Flow XML.

Architecture:
    Start (Agreement__c, after-save, filter formula on Status='Completed' and Signed_Date populated, only-when-changed-into)
      -> Get Opportunity
      -> Get CustomNotificationType (DeveloperName='Agreement_Activity')
      -> Decision: signed date >= $Setup cutoff?  no=>terminate. yes=>continue
      -> Decision: which Agreement_Type__c?
           PAL                  -> assign_pal
           EMA                  -> assign_ema
           NEMA                 -> assign_nema
           Bulk                 -> assign_bulk
           PAL Addendum         -> assign_pal_add
           MSA Addendum         -> assign_msa_add
           2nd ISP MSA Addendum -> assign_msa2_add
           2nd ISP NEMA         -> assign_nema2
           default              -> terminate
      -> create_log
      -> send_bell
      -> end (no connector)

Niraj's User Id is hardcoded as a constant collection variable so the Flow
can target him directly without a Get Records on User.
"""
from pathlib import Path

NIRAJ_USER_ID = "005WR000008V4VoYAK"

# Per-type configuration: agreement_type_value, notif_type_picklist, title_template, body_template
# Templates use {OPP}, {ADDR}, {UNITS}, {RT}, {PTYPE}, {ISP}, {ISPS}, {SDATE}
TYPES = [
    {
        "key": "pal", "agr_type": "PAL", "notif": "PAL Signed",
        "title": "PAL Signed: {OPP}",
        "body":  "PAL signed at {OPP}. Address {ADDR}. {UNITS} units. Property Type {PTYPE}. RT {RT}. Signed {SDATE}.",
    },
    {
        "key": "ema", "agr_type": "EMA", "notif": "EMA Signed",
        "title": "EMA Signed: {OPP}",
        "body":  "EMA signed at {OPP}. Confirmed ISP {ISP}. Signed {SDATE}.",
    },
    {
        "key": "nema", "agr_type": "NEMA", "notif": "NEMA Signed",
        "title": "NEMA Signed: {OPP}",
        "body":  "NEMA signed at {OPP}. Confirmed ISP {ISP}. Signed {SDATE}.",
    },
    {
        "key": "bulk", "agr_type": "Bulk", "notif": "Bulk Signed",
        "title": "Bulk Signed: {OPP}",
        "body":  "Bulk signed at {OPP}. Confirmed ISP {ISP}. Signed {SDATE}.",
    },
    {
        "key": "pal_add", "agr_type": "PAL Addendum", "notif": "PAL Addendum Signed",
        "title": "PAL Addendum Signed: {OPP}",
        "body":  "PAL Addendum signed at {OPP}. Signed {SDATE}.",
    },
    {
        "key": "msa_add", "agr_type": "MSA Addendum", "notif": "MSA Addendum Signed",
        "title": "MSA Addendum Signed: {OPP}",
        "body":  "MSA Addendum signed at {OPP}. Confirmed ISP {ISP}. Signed {SDATE}.",
    },
    {
        "key": "msa2_add", "agr_type": "2nd ISP MSA Addendum", "notif": "2nd ISP MSA Addendum Signed",
        "title": "2nd ISP MSA Addendum Signed: {OPP}",
        "body":  "2nd ISP MSA Addendum signed at {OPP}. Confirmed ISPs {ISPS}. Signed {SDATE}.",
    },
    {
        "key": "nema2", "agr_type": "2nd ISP NEMA", "notif": "2nd ISP NEMA Signed",
        "title": "2nd ISP NEMA Signed: {OPP}",
        "body":  "2nd ISP NEMA signed at {OPP}. Confirmed ISPs {ISPS}. Signed {SDATE}.",
    },
]

TOKEN_TO_FLOW = {
    "{OPP}":   "{!get_opportunity.Name}",
    "{ADDR}":  "{!get_opportunity.Property_Address__c}",
    "{UNITS}": "{!get_opportunity.Units__c}",
    "{RT}":    "{!get_opportunity.RecordType.Name}",
    "{PTYPE}": "{!get_opportunity.Property_Type__c}",
    "{ISP}":   "{!get_opportunity.Confirmed_ISP__c}",
    "{ISPS}":  "{!get_opportunity.Confirmed_ISPs__c}",
    "{SDATE}": "{!$Record.Signed_Date__c}",
}


def render_template(s: str) -> str:
    for tok, ref in TOKEN_TO_FLOW.items():
        s = s.replace(tok, ref)
    return s


def assignments_xml(t, y_offset):
    title_str = render_template(t["title"])
    body_str = render_template(t["body"])
    return f"""    <assignments>
        <name>assign_{t['key']}</name>
        <label>Assign {t['agr_type']} Strings</label>
        <locationX>50</locationX>
        <locationY>{y_offset}</locationY>
        <assignmentItems>
            <assignToReference>title</assignToReference>
            <operator>Assign</operator>
            <value><stringValue>{title_str}</stringValue></value>
        </assignmentItems>
        <assignmentItems>
            <assignToReference>body</assignToReference>
            <operator>Assign</operator>
            <value><stringValue>{body_str}</stringValue></value>
        </assignmentItems>
        <assignmentItems>
            <assignToReference>notif_type_value</assignToReference>
            <operator>Assign</operator>
            <value><stringValue>{t['notif']}</stringValue></value>
        </assignmentItems>
        <connector><targetReference>set_recipients</targetReference></connector>
    </assignments>"""


def set_recipients_xml():
    return f"""    <assignments>
        <name>set_recipients</name>
        <label>Set Recipient IDs</label>
        <locationX>176</locationX>
        <locationY>1500</locationY>
        <assignmentItems>
            <assignToReference>recipient_ids</assignToReference>
            <operator>Add</operator>
            <value><stringValue>{NIRAJ_USER_ID}</stringValue></value>
        </assignmentItems>
        <connector><targetReference>create_log</targetReference></connector>
    </assignments>"""


def decision_outcome_xml(t):
    return f"""        <rules>
            <name>route_{t['key']}</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>$Record.Agreement_Type__c</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue><stringValue>{t['agr_type']}</stringValue></rightValue>
            </conditions>
            <connector><targetReference>assign_{t['key']}</targetReference></connector>
            <label>{t['agr_type']}</label>
        </rules>"""


def build_flow_xml() -> str:
    assignments = "\n".join(assignments_xml(t, 600 + i*120) for i, t in enumerate(TYPES)) + "\n\n" + set_recipients_xml()
    type_outcomes = "\n".join(decision_outcome_xml(t) for t in TYPES)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <description>Sends bell-icon Custom Notifications to Niraj and writes Agreement_Notification__c log rows when an Agreement reaches Status=Completed for one of seven tracked types. Gated on Signed_Date__c &gt;= Custom Setting Notification_Settings__c.Active_After_Date__c so cleanup of historical records does not notify.</description>
    <environments>Default</environments>
    <interviewLabel>Agreement Niraj Notifications {{!$Flow.CurrentDateTime}}</interviewLabel>
    <label>Agreement Niraj Notifications</label>
    <processMetadataValues>
        <name>BuilderType</name>
        <value><stringValue>LightningFlowBuilder</stringValue></value>
    </processMetadataValues>
    <processType>AutoLaunchedFlow</processType>
    <runInMode>SystemModeWithSharing</runInMode>
    <status>Active</status>

    <start>
        <locationX>176</locationX>
        <locationY>0</locationY>
        <connector><targetReference>get_opportunity</targetReference></connector>
        <doesRequireRecordChangedToMeetCriteria>true</doesRequireRecordChangedToMeetCriteria>
        <filterFormula>AND( ISPICKVAL({{!$Record.Status__c}}, "Completed"), NOT(ISBLANK({{!$Record.Opportunity__c}})), NOT(ISBLANK({{!$Record.Signed_Date__c}})) )</filterFormula>
        <object>Agreement__c</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
    </start>

    <variables>
        <name>title</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
    </variables>
    <variables>
        <name>body</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
    </variables>
    <variables>
        <name>notif_type_value</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
    </variables>
    <variables>
        <name>recipient_ids</name>
        <dataType>String</dataType>
        <isCollection>true</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
    </variables>

    <constants>
        <name>notif_type_id</name>
        <dataType>String</dataType>
        <value><stringValue>0MLWR000005PimA4AS</stringValue></value>
    </constants>

    <recordLookups>
        <name>get_opportunity</name>
        <label>Get Opportunity</label>
        <locationX>176</locationX>
        <locationY>120</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector><targetReference>get_notif_type</targetReference></connector>
        <getFirstRecordOnly>true</getFirstRecordOnly>
        <object>Opportunity</object>
        <queriedFields>Id</queriedFields>
        <queriedFields>Name</queriedFields>
        <queriedFields>Units__c</queriedFields>
        <queriedFields>Property_Type__c</queriedFields>
        <queriedFields>Confirmed_ISP__c</queriedFields>
        <queriedFields>Confirmed_ISPs__c</queriedFields>
        <queriedFields>Property_Address__c</queriedFields>
        <queriedFields>RecordTypeId</queriedFields>
        <storeOutputAutomatically>true</storeOutputAutomatically>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </filters>
    </recordLookups>

    <recordLookups>
        <name>get_notif_type</name>
        <label>Get Custom Notification Type</label>
        <locationX>176</locationX>
        <locationY>240</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector><targetReference>decide_cutoff</targetReference></connector>
        <getFirstRecordOnly>true</getFirstRecordOnly>
        <object>CustomNotificationType</object>
        <queriedFields>Id</queriedFields>
        <queriedFields>DeveloperName</queriedFields>
        <storeOutputAutomatically>true</storeOutputAutomatically>
        <filterLogic>and</filterLogic>
        <filters>
            <field>DeveloperName</field>
            <operator>EqualTo</operator>
            <value><stringValue>Agreement_Activity</stringValue></value>
        </filters>
    </recordLookups>

    <formulas>
        <name>cutoff_date</name>
        <dataType>Date</dataType>
        <expression>$Setup.Notification_Settings__c.Active_After_Date__c</expression>
    </formulas>
    <formulas>
        <name>past_cutoff_formula</name>
        <dataType>Boolean</dataType>
        <expression>AND( NOT(ISNULL({{!cutoff_date}})), {{!$Record.Signed_Date__c}} &gt;= {{!cutoff_date}} )</expression>
    </formulas>

    <decisions>
        <name>decide_cutoff</name>
        <label>Signed Date Past Cutoff?</label>
        <locationX>176</locationX>
        <locationY>360</locationY>
        <defaultConnectorLabel>Skip (before cutoff)</defaultConnectorLabel>
        <rules>
            <name>past_cutoff</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>past_cutoff_formula</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue><booleanValue>true</booleanValue></rightValue>
            </conditions>
            <connector><targetReference>decide_type</targetReference></connector>
            <label>Past Cutoff</label>
        </rules>
    </decisions>

    <decisions>
        <name>decide_type</name>
        <label>Which Agreement Type?</label>
        <locationX>176</locationX>
        <locationY>480</locationY>
        <defaultConnectorLabel>Other</defaultConnectorLabel>
{type_outcomes}
    </decisions>

{assignments}

    <recordCreates>
        <name>create_log</name>
        <label>Create Notification Log Row</label>
        <locationX>176</locationX>
        <locationY>1600</locationY>
        <connector><targetReference>send_bell</targetReference></connector>
        <inputAssignments>
            <field>Agreement__c</field>
            <value><elementReference>$Record.Id</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Opportunity__c</field>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Recipient__c</field>
            <value><stringValue>{NIRAJ_USER_ID}</stringValue></value>
        </inputAssignments>
        <inputAssignments>
            <field>Notification_Type__c</field>
            <value><elementReference>notif_type_value</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Title__c</field>
            <value><elementReference>title</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Body__c</field>
            <value><elementReference>body</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Sent_DateTime__c</field>
            <value><elementReference>$Flow.CurrentDateTime</elementReference></value>
        </inputAssignments>
        <object>Agreement_Notification__c</object>
    </recordCreates>

    <actionCalls>
        <name>send_bell</name>
        <label>Send Bell Notification</label>
        <locationX>176</locationX>
        <locationY>1720</locationY>
        <actionName>customNotificationAction</actionName>
        <actionType>customNotificationAction</actionType>
        <flowTransactionModel>CurrentTransaction</flowTransactionModel>
        <inputParameters>
            <name>customNotifTypeId</name>
            <value><elementReference>notif_type_id</elementReference></value>
        </inputParameters>
        <inputParameters>
            <name>recipientIds</name>
            <value><elementReference>recipient_ids</elementReference></value>
        </inputParameters>
        <inputParameters>
            <name>title</name>
            <value><elementReference>title</elementReference></value>
        </inputParameters>
        <inputParameters>
            <name>body</name>
            <value><elementReference>body</elementReference></value>
        </inputParameters>
        <inputParameters>
            <name>targetId</name>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </inputParameters>
    </actionCalls>
</Flow>
"""


def main():
    out = Path(__file__).parent / "force-app/main/default/flows/Agreement_Niraj_Notifications.flow-meta.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_flow_xml(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
