"""Find both Dobson Ranch Condos Opps and inventory their child records.

Goal: identify Melissa's new duplicate (created today, 2026-05-19) vs the existing Opp.
Inventory: contacts, agreements, notes, attachments, property location, sitetracker links.
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

# 1. Find all Dobson Ranch Condos Opps
q = ("SELECT Id, Name, StageName, Owner.Name, CreatedDate, CreatedBy.Name, "
     "LastModifiedDate, Probability, Units__c, Property_Address__c, "
     "Property_City__c, Property_State__c, Property_Zip__c, Property_Category__c, "
     "Build_Type__c, Property_Type__c, Incumbent_Provider__c, Incumbent_Agreement_Type__c, "
     "Incumbent_Agreement_Expiration__c, RecordType.Name, "
     "Projected_Close_Date__c, CloseDate, Agreement_Name__c, "
     "Property_Location__c, Property_Location__r.Name, "
     "Description, Next_Action__c, Next_Action_Date__c, "
     "Sales_Status__c, Hold_Reason__c, Substatus__c, Sub_Bucket__c, "
     "Prospective_ISP__c, Confirmed_ISP__c, HOA__c, New_Construction__c, "
     "Property_Classification__c, RE_Assigned__r.Name, Portfolio__r.Name, Management_Company__r.Name, "
     "FF_Notes__c, Closed_Notes__c, Loss_Reason__c "
     "FROM Opportunity "
     "WHERE Name LIKE '%Dobson Ranch%' "
     "ORDER BY CreatedDate DESC")
opps = sf.query(q)['records']
print(f'Found {len(opps)} Dobson Ranch Opps:\n')
for o in opps:
    print(f"  Id={o['Id']}")
    print(f"    Name:         {o['Name']}")
    print(f"    Site Name:    {o.get('Agreement_Name__c')}")  # field labeled "Site Name" in UI
    print(f"    Stage:        {o['StageName']}  (Prob={o.get('Probability')})")
    print(f"    RecordType:   {o.get('RecordType') and o['RecordType']['Name']}")
    print(f"    Owner:        {o.get('Owner') and o['Owner']['Name']}")
    print(f"    Created:      {o['CreatedDate']} by {o.get('CreatedBy') and o['CreatedBy']['Name']}")
    print(f"    Modified:     {o['LastModifiedDate']}")
    print(f"    Address:      {o.get('Property_Address__c')}, {o.get('Property_City__c')}, "
          f"{o.get('Property_State__c')} {o.get('Property_Zip__c')}")
    print(f"    Units:        {o.get('Units__c')}  Build={o.get('Build_Type__c')}  PropType={o.get('Property_Type__c')}")
    print(f"    Category:     {o.get('Property_Category__c')}  Classification={o.get('Property_Classification__c')}")
    print(f"    Incumbent:    {o.get('Incumbent_Provider__c')}  {o.get('Incumbent_Agreement_Type__c')}  exp {o.get('Incumbent_Agreement_Expiration__c')}")
    print(f"    ISP:          prosp={o.get('Prospective_ISP__c')}  conf={o.get('Confirmed_ISP__c')}")
    print(f"    Close:        proj={o.get('Projected_Close_Date__c')}  close={o['CloseDate']}")
    print(f"    Property_Location:  {o.get('Property_Location__c')}  ({o.get('Property_Location__r') and o['Property_Location__r']['Name']})")
    print(f"    RE_Assigned:  {o.get('RE_Assigned__r') and o['RE_Assigned__r']['Name']}")
    print(f"    Portfolio:    {o.get('Portfolio__r') and o['Portfolio__r']['Name']}")
    print(f"    Mgmt Co:      {o.get('Management_Company__r') and o['Management_Company__r']['Name']}")
    print(f"    HOA:          {o.get('HOA__c')}  NewConstr={o.get('New_Construction__c')}")
    print(f"    Sales_Status: {o.get('Sales_Status__c')}  Hold_Reason={o.get('Hold_Reason__c')}  Substatus={o.get('Substatus__c')}  SubBucket={o.get('Sub_Bucket__c')}")
    print(f"    Next_Action:  {o.get('Next_Action__c')}  (date={o.get('Next_Action_Date__c')})")
    print(f"    FF_Notes:     {o.get('FF_Notes__c')}")
    print(f"    Closed_Notes: {o.get('Closed_Notes__c')}")
    print(f"    Description:  {o.get('Description')}")
    print(f"    Loss_Reason:  {o.get('Loss_Reason__c')}")
    print()

if len(opps) < 2:
    print('Need at least 2 Opps to compare. Exiting.')
    sys.exit(0)

# Inventory child records for the two Dobson Ranch CONDOS Opps only
focus_ids = {'006WR000015Ifm7YAC', '006WR00000wkEcUYAU'}
for o in [o for o in opps if o['Id'] in focus_ids]:
    oid = o['Id']
    print(f'\n=== Child records for {o["Name"]} ({oid}) ===')

    # Contact junctions (Opportunity_Contact__c)
    oc = sf.query_all(
        f"SELECT Id, Name, Contact__c, Contact__r.Name, Contact__r.Email, "
        f"Role__c, CreatedDate, CreatedBy.Name "
        f"FROM Opportunity_Contact__c WHERE Opportunity__c = '{oid}'"
    )['records']
    print(f'  Contacts ({len(oc)}):')
    for c in oc:
        print(f"    {c['Name']}  Contact={c.get('Contact__r') and c['Contact__r']['Name']}  "
              f"Email={c.get('Contact__r') and c['Contact__r'].get('Email')}  Role={c.get('Role__c')}  "
              f"Created={c['CreatedDate']} by {c.get('CreatedBy') and c['CreatedBy']['Name']}")

    # Agreements
    ag = sf.query_all(
        f"SELECT Id, Name, Status__c, Agreement_Type__c, IronClad_ID__c, "
        f"Signed_Date__c, CreatedDate, CreatedBy.Name FROM Agreement__c WHERE Opportunity__c = '{oid}'"
    )['records']
    print(f'  Agreements ({len(ag)}):')
    for a in ag:
        print(f"    {a['Name']}  type={a.get('Agreement_Type__c')}  status={a.get('Status__c')}  "
              f"IC={a.get('IronClad_ID__c')}  signed={a.get('Signed_Date__c')}  "
              f"Created={a['CreatedDate']} by {a.get('CreatedBy') and a['CreatedBy']['Name']}")

    # SiteTracker projects
    st = sf.query_all(
        f"SELECT Id, Name, CreatedDate, CreatedBy.Name FROM SiteTracker_Project__c WHERE Opportunity__c = '{oid}'"
    )['records']
    print(f'  SiteTracker Projects ({len(st)}):')
    for s in st:
        print(f"    {s['Name']}  Created={s['CreatedDate']}")

    # Notes (Note__c custom object if it exists, otherwise ContentNote via ContentDocumentLink)
    try:
        nt = sf.query_all(
            f"SELECT Id, Name, Body__c, CreatedDate, CreatedBy.Name "
            f"FROM Note__c WHERE Opportunity__c = '{oid}'"
        )['records']
        print(f'  Notes ({len(nt)}):')
        for n in nt:
            body = (n.get('Body__c') or '')[:80]
            print(f"    {n['Name']}: {body}  Created={n['CreatedDate']} by {n.get('CreatedBy') and n['CreatedBy']['Name']}")
    except Exception as e:
        print(f'  Notes (Note__c): query failed - {e}')

    # ContentDocumentLinks (Files / ContentNotes attached via Files)
    cdls = sf.query_all(
        f"SELECT ContentDocumentId, ContentDocument.Title, ContentDocument.FileType, "
        f"ContentDocument.CreatedDate, ContentDocument.CreatedBy.Name "
        f"FROM ContentDocumentLink WHERE LinkedEntityId = '{oid}'"
    )['records']
    print(f'  Files/ContentNotes via ContentDocumentLink ({len(cdls)}):')
    for cdl in cdls:
        cd = cdl.get('ContentDocument') or {}
        print(f"    {cd.get('Title')}  type={cd.get('FileType')}  "
              f"Created={cd.get('CreatedDate')} by {(cd.get('CreatedBy') or {}).get('Name')}")

    # Activities (tasks/events) - via standard ActivityHistory subquery
    acts = sf.query_all(
        f"SELECT Id, Subject, ActivityDate, CreatedDate, CreatedBy.Name, Status "
        f"FROM Task WHERE WhatId = '{oid}'"
    )['records']
    print(f'  Tasks ({len(acts)}):')
    for t in acts:
        print(f"    {t['Subject']}  date={t.get('ActivityDate')}  status={t.get('Status')}  "
              f"Created={t['CreatedDate']} by {t.get('CreatedBy') and t['CreatedBy']['Name']}")

    evs = sf.query_all(
        f"SELECT Id, Subject, ActivityDate, CreatedDate, CreatedBy.Name "
        f"FROM Event WHERE WhatId = '{oid}'"
    )['records']
    print(f'  Events ({len(evs)}):')
    for e in evs:
        print(f"    {e['Subject']}  date={e.get('ActivityDate')}  Created={e['CreatedDate']}")
