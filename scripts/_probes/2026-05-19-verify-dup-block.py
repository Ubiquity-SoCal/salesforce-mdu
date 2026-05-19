"""Verify OpportunityAddressDupBlock blocks creation of a dup at 1942 South Emerson."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce, exceptions

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)

# Clean up any leftover test records from previous probe runs
for nm in ('TEST DUP BLOCK 1942 EMERSON', 'TEST DUP CASE VARIANT', 'TEST UNIQUE INSERT'):
    leftovers = sf.query(
        f"SELECT Id FROM Opportunity WHERE Name = '{nm}'"
    )['records']
    for r in leftovers:
        sf.Opportunity.delete(r['Id'])
        print(f"  Cleaned up leftover {r['Id']} ({nm})")

# Look up MDU/SFU record type id
rt = sf.query("SELECT Id FROM RecordType WHERE SObjectType='Opportunity' AND DeveloperName='MDU' LIMIT 1")['records']
if not rt:
    print('No MDU RecordType found; aborting')
    sys.exit(1)
rt_id = rt[0]['Id']

# Attempt 1: dup at the same address as the existing Dobson Ranch Condos Opp
print("Attempt 1: insert dup at '1942 South Emerson, Mesa, AZ 85210' (existing: Dobson Ranch Condos)")
payload = {
    'Name': 'TEST DUP BLOCK 1942 EMERSON',
    'StageName': 'Prospecting',
    'CloseDate': '2026-12-31',
    'RecordTypeId': rt_id,
    'Sales_Status__c': 'Contact Pending',
    'Property_Address__c': '1942 South Emerson',
    'Property_City__c': 'Mesa',
    'Property_State__c': 'AZ',
    'Property_Zip__c': '85210',
}
try:
    res = sf.Opportunity.create(payload)
    print(f'  UNEXPECTED SUCCESS: created {res["id"]}  (rule did not block)')
    # Clean up since we don't want a stray test record
    sf.Opportunity.delete(res['id'])
    print(f'  Cleaned up {res["id"]}')
except exceptions.SalesforceMalformedRequest as e:
    print(f'  BLOCKED as expected: {e.content[0].get("message")}')

# Attempt 2: case + whitespace variant
print("\nAttempt 2: case-insensitive dup '  1942 SOUTH EMERSON  / mesa / az / 85210'")
payload2 = dict(payload, Name='TEST DUP CASE VARIANT')
payload2['Property_Address__c'] = '  1942 SOUTH EMERSON  '
payload2['Property_City__c'] = 'mesa'
payload2['Property_State__c'] = 'az'
try:
    res = sf.Opportunity.create(payload2)
    print(f'  UNEXPECTED SUCCESS: created {res["id"]}')
    sf.Opportunity.delete(res['id'])
except exceptions.SalesforceMalformedRequest as e:
    print(f'  BLOCKED as expected: {e.content[0].get("message")}')

# Attempt 3: a unique address (should succeed) - then clean up
print("\nAttempt 3: insert at unused address '9999 TEST DUP CHECK BLVD, Mesa, AZ 85210' (should succeed)")
payload3 = dict(payload, Name='TEST UNIQUE INSERT')
payload3['Property_Address__c'] = '9999 TEST DUP CHECK BLVD'
try:
    res = sf.Opportunity.create(payload3)
    print(f'  SUCCESS as expected: created {res["id"]}')
    sf.Opportunity.delete(res['id'])
    print(f'  Cleaned up {res["id"]}')
except exceptions.SalesforceMalformedRequest as e:
    print(f'  UNEXPECTED BLOCK: {e.content[0].get("message")}')
