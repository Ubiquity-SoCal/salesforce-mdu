"""Detail on the 6 SMB ROE Opps + 30 SMB ROE Property_Locations."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Full Opportunity fields
desc = sf.Opportunity.describe()
opp_fields = [f["name"] for f in desc["fields"]]
print(f"Opportunity field count: {len(opp_fields)}")
property_related = [f for f in opp_fields if "propert" in f.lower() or "location" in f.lower() or "address" in f.lower()]
print(f"Property/location/address fields on Opp: {property_related}")
print()

# Pull 6 SMB ROE opps with wide field set
r = sf.query("""
    SELECT Id, Name, StageName, AccountId, Account.Name, OwnerId, Owner.Name,
           CreatedDate, CreatedBy.Name, Description, LeadSource, Amount,
           Agreement_Name__c, RecordType.Name, Property_State__c
    FROM Opportunity
    WHERE Name LIKE '%SMB ROE%'
    ORDER BY CreatedDate DESC
""")
print(f"=== 6 SMB ROE Opps ===")
for row in r["records"]:
    rt = row['RecordType']['Name'] if row.get('RecordType') else 'None'
    acc = row['Account']['Name'] if row.get('Account') else 'None'
    print(f"\nID: {row['Id']}")
    print(f"  Name: {row['Name']}")
    print(f"  Stage: {row['StageName']} | RT: {rt}")
    print(f"  Account: {acc} ({row.get('AccountId')})")
    print(f"  Owner: {row['Owner']['Name']} | Created: {row['CreatedDate'][:10]} by {row['CreatedBy']['Name']}")
    print(f"  State: {row.get('Property_State__c')} | Agreement: {row.get('Agreement_Name__c')}")
    print(f"  Amount: {row.get('Amount')} | Source: {row.get('LeadSource')}")
    if row.get('Description'):
        print(f"  Desc: {row['Description'][:200]}")

# Contacts on these Opps (via OpportunityContactRole or Opportunity_Contact__c)
opp_ids = [f"'{row['Id']}'" for row in r["records"]]
if opp_ids:
    try:
        cr = sf.query(f"""
            SELECT Id, OpportunityId, Opportunity.Name, Contact.Name, Contact.Email, Contact.Phone, Role, IsPrimary
            FROM OpportunityContactRole
            WHERE OpportunityId IN ({','.join(opp_ids)})
        """)
        print(f"\n=== Opportunity Contact Roles ({len(cr['records'])}) ===")
        for row in cr["records"]:
            print(f"  {row['Opportunity']['Name']} | {row['Contact']['Name']} | {row.get('Role')} | primary={row['IsPrimary']}")
    except Exception as e:
        print(f"OCR query failed: {e}")

    try:
        cr = sf.query(f"""
            SELECT Id, Opportunity__c, Opportunity__r.Name, Contact__r.Name, Contact__r.Email, Contact__r.Phone, Role__c, Primary__c
            FROM Opportunity_Contact__c
            WHERE Opportunity__c IN ({','.join(opp_ids)})
        """)
        print(f"\n=== Opportunity_Contact__c Junction ({len(cr['records'])}) ===")
        for row in cr["records"]:
            print(f"  {row['Opportunity__r']['Name']} | {row['Contact__r']['Name']} | {row.get('Role__c')} | primary={row.get('Primary__c')}")
    except Exception as e:
        print(f"Opp_Contact__c query failed: {e}")

print()
print("=== Property_Location fields (name search) ===")
pl_desc = sf.Property_Location__c.describe()
pl_fields = [f["name"] for f in pl_desc["fields"]]
smb_pl = [f for f in pl_fields if "smb" in f.lower() or "roe" in f.lower() or "ff" in f.lower() or "sales" in f.lower() or "assign" in f.lower() or "build" in f.lower()]
print(f"SMB/ROE/FF/Sales/Assign fields: {smb_pl}")

# 30 SMB ROE property locations
r = sf.query(f"""
    SELECT Id, Name, FF_Sales_Project__c, FF_Sales_Assigned_Date__c, Build_Effort__c, Sales_Notes__c, Property_State__c, Mgmt_Company__c, Import_Source_URL__c
    FROM Property_Location__c
    WHERE FF_Sales_Project__c = 'SMB ROE'
    ORDER BY Property_State__c, Name
""")
print(f"\n=== 30 SMB ROE Property_Locations ===")
for row in r["records"]:
    print(f"  {row['Id']} | {row['Name']} | {row.get('Property_State__c')} | Build={row.get('Build_Effort__c')} | Mgmt={row.get('Mgmt_Company__c')}")

# Contacts on these properties
pl_ids = [f"'{row['Id']}'" for row in r["records"]]
c_desc = sf.Contact.describe()
prop_ref = [f["name"] for f in c_desc["fields"] if "propert" in f["name"].lower()]
print(f"\nProperty-related fields on Contact: {prop_ref}")

if pl_ids and "Property_Location__c" in [f["name"] for f in c_desc["fields"]]:
    cr = sf.query(f"""
        SELECT Id, Name, FirstName, LastName, Email, Phone, Title, AccountId, Account.Name, Property_Location__c, Property_Location__r.Name
        FROM Contact
        WHERE Property_Location__c IN ({','.join(pl_ids)})
    """)
    print(f"\n=== Contacts on SMB ROE Properties ({len(cr['records'])}) ===")
    for row in cr["records"]:
        acc = row['Account']['Name'] if row.get('Account') else 'None'
        print(f"  {row['Name']} | {row.get('Title')} | {row.get('Email')} | {row.get('Phone')} | Acc={acc} | Prop={row['Property_Location__r']['Name']}")
