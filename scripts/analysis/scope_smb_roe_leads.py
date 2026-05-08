"""Scope: current Leads, SMB ROE Opportunities, SMB ROE Campaign."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=TOKEN)

print("=" * 70)
print("LEADS")
print("=" * 70)
r = sf.query("SELECT COUNT() FROM Lead")
print(f"Total Leads: {r['totalSize']}")

r = sf.query("SELECT COUNT() FROM Lead WHERE IsConverted = false")
print(f"Unconverted: {r['totalSize']}")

r = sf.query("SELECT COUNT() FROM Lead WHERE IsConverted = true")
print(f"Converted: {r['totalSize']}")

# Breakdown by status / owner / source
r = sf.query("SELECT Status, COUNT(Id) cnt FROM Lead GROUP BY Status")
print("\nBy Status:")
for row in r["records"]:
    print(f"  {row['Status']}: {row['cnt']}")

r = sf.query("SELECT LeadSource, COUNT(Id) cnt FROM Lead GROUP BY LeadSource")
print("\nBy Source:")
for row in r["records"]:
    print(f"  {row['LeadSource']}: {row['cnt']}")

# All 9 leads
r = sf.query("SELECT Id, Name, Company, Status, LeadSource, CreatedDate, Owner.Name FROM Lead ORDER BY CreatedDate DESC")
print("\nAll Leads:")
for row in r["records"]:
    print(f"  {row['Id']} | {row['Name']} | {row['Company']} | {row['Status']} | {row['LeadSource']} | {row['CreatedDate'][:10]} | {row['Owner']['Name']}")

print()
print("=" * 70)
print("SMB ROE OPPORTUNITIES")
print("=" * 70)

# Find Opps tagged SMB ROE - check a few likely fields
# Property_Location__c.FF_Sales_Project__c = "SMB ROE" was the tag per memory
# But Opp could link via Property or directly

# Check fields on Opportunity
desc = sf.Opportunity.describe()
smb_fields = [f["name"] for f in desc["fields"] if "smb" in f["name"].lower() or "roe" in f["name"].lower() or "ff" in f["name"].lower()]
print(f"SMB/ROE/FF fields on Opportunity: {smb_fields}")

# Try querying Opps where name or a field mentions SMB ROE
try:
    r = sf.query("SELECT COUNT() FROM Opportunity WHERE Name LIKE '%SMB ROE%'")
    print(f"Opps with 'SMB ROE' in Name: {r['totalSize']}")
except Exception as e:
    print(f"Name LIKE failed: {e}")

# Check Property_Location__c SMB ROE tag
try:
    r = sf.query("SELECT COUNT() FROM Property_Location__c WHERE FF_Sales_Project__c = 'SMB ROE'")
    print(f"Property_Location__c tagged 'SMB ROE': {r['totalSize']}")
except Exception as e:
    print(f"Property query failed: {e}")

# Get those properties
try:
    r = sf.query("SELECT Id, Name, FF_Sales_Project__c, RE_Assigned__c, Build_Effort__c, Property_State__c FROM Property_Location__c WHERE FF_Sales_Project__c = 'SMB ROE'")
    print(f"\nSMB ROE Property_Locations ({len(r['records'])}):")
    for row in r["records"]:
        print(f"  {row['Id']} | {row['Name']} | {row.get('Property_State__c')} | RE={row.get('RE_Assigned__c')} | Build={row.get('Build_Effort__c')}")
except Exception as e:
    print(f"Property detail query failed: {e}")

# Look for Opps that link to those properties
try:
    r = sf.query("""
        SELECT Id, Name, StageName, RecordType.Name, Property_Location__c, Property_Location__r.FF_Sales_Project__c
        FROM Opportunity
        WHERE Property_Location__r.FF_Sales_Project__c = 'SMB ROE'
    """)
    print(f"\nOpps linked to SMB ROE Property_Locations ({len(r['records'])}):")
    for row in r["records"]:
        rt = row['RecordType']['Name'] if row.get('RecordType') else 'None'
        print(f"  {row['Id']} | {row['Name']} | Stage={row['StageName']} | RT={rt}")
except Exception as e:
    print(f"Opp-via-Property query failed: {e}")

print()
print("=" * 70)
print("CAMPAIGNS")
print("=" * 70)

r = sf.query("SELECT Id, Name, IsActive, Status, Type, NumberOfContacts, NumberOfLeads FROM Campaign ORDER BY CreatedDate DESC")
print(f"Total Campaigns: {len(r['records'])}")
for row in r["records"]:
    print(f"  {row['Id']} | {row['Name']} | Active={row['IsActive']} | Status={row['Status']} | Type={row['Type']} | Leads={row['NumberOfLeads']} | Contacts={row['NumberOfContacts']}")
