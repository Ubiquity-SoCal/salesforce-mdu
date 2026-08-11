"""Look up Property_Location candidates for the 4 clean MDU Engaged opps,
and pull all notes for the 2 stale ones."""
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

desc = sf.Property_Location__c.describe()
fields = sorted(f['name'] for f in desc['fields'] if not f['name'].startswith('Last') and f['name'] not in ('Id','OwnerId','IsDeleted','SystemModstamp','CreatedById','LastModifiedById','CurrencyIsoCode'))
print("Property_Location__c fields:", fields)
addr_field = next((f for f in fields if 'Address' in f or 'Street' in f), None)
city_field = next((f for f in fields if f in ('City__c','BillingCity','City') or 'City' in f), None)
state_field = next((f for f in fields if f in ('State__c','BillingState','State') or 'State' in f), None)
zip_field = next((f for f in fields if 'Zip' in f or 'PostalCode' in f), None)
print(f"Using addr={addr_field} city={city_field} state={state_field} zip={zip_field}")

print("=" * 80)
print("PROPERTY_LOCATION CANDIDATES")
print("=" * 80)

searches = [
    ('Howard Street',          ['Howard']),
    ('Terrace Garden',          ['Terrace Garden', 'Terrace']),
    ('Santa Helena Park',       ['Santa Helena']),
    ('Mineral Wells Shady Oak', ['Shady Oak', 'Mineral Wells']),
]
for label, terms in searches:
    print(f"\n{label}:")
    fld_list = ['Property_Location_Name__c','City__c','State__c','Property_Type__c','Property_Unit_Count__c','Active_Unit_Count__c']
    cols = ', '.join(fld_list)
    for t in terms:
        q = sf.query(f"""
            SELECT Id, Name, {cols}
            FROM Property_Location__c
            WHERE Name LIKE '%{t}%' OR Property_Location_Name__c LIKE '%{t}%'
            LIMIT 10
        """)
        for r in q['records']:
            extras = ' | '.join(f"{f}={r.get(f)}" for f in fld_list if r.get(f) is not None)
            print(f"  [{t}] {r['Id']}  {r['Name']}  | {extras}")

print()
print("=" * 80)
print("REVIEW CANDIDATES — full note history")
print("=" * 80)

review = ['006WR00000yur0lYAA', '006WR00000ywTYXYA2']
for opp_id in review:
    opp = sf.query(f"""
        SELECT Id, Name, Owner.Name, Sales_Status__c, CreatedDate, LastModifiedDate,
               StageName, Next_Action__c, Property_Location__c, Account.Name
        FROM Opportunity WHERE Id = '{opp_id}'
    """)['records'][0]
    print(f"\n{opp['Name']}  Owner: {opp['Owner']['Name']}")
    print(f"  Created: {opp['CreatedDate'][:10]}  Modified: {opp['LastModifiedDate'][:10]}")
    print(f"  Sales_Status: {opp['Sales_Status__c']}  PL: {opp['Property_Location__c']}  Acct: {(opp.get('Account') or {}).get('Name')}")

    cdl = sf.query(f"""
        SELECT ContentDocumentId FROM ContentDocumentLink
        WHERE LinkedEntityId = '{opp_id}'
    """)
    doc_ids = [r['ContentDocumentId'] for r in cdl['records']]
    if doc_ids:
        ids_str = "','".join(doc_ids)
        cv = sf.query(f"""
            SELECT Id, Title, TextPreview, CreatedDate, CreatedBy.Name
            FROM ContentVersion
            WHERE ContentDocumentId IN ('{ids_str}') AND IsLatest = TRUE
            ORDER BY CreatedDate DESC
        """)
        for r in cv['records']:
            print(f"  Note {r['CreatedDate'][:10]} by {r['CreatedBy']['Name']}: {r['Title']}")
            if r.get('TextPreview'):
                print(f"    > {r['TextPreview'][:300]}")
    else:
        print("  No notes")
