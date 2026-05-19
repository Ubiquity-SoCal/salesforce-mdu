"""Look at the raw stored values of the 4 address fields on the existing Dobson Opp."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username=os.environ['SF_MAIN_USERNAME'],
    password=os.environ['SF_MAIN_PASSWORD'],
    security_token=os.environ['SF_MAIN_TOKEN'],
)
r = sf.Opportunity.get('006WR00000wkEcUYAU')
print('Existing Dobson Ranch Condos (006WR00000wkEcUYAU):')
print(f"  Property_Address__c: {r['Property_Address__c']!r}")
print(f"  Property_City__c:    {r['Property_City__c']!r}")
print(f"  Property_State__c:   {r['Property_State__c']!r}")
print(f"  Property_Zip__c:     {r['Property_Zip__c']!r}")
print()

# How widespread is this? Sample 50 random Opps to see address-field hygiene.
print('Address field hygiene sample (50 active Opps):')
q = ("SELECT Property_Address__c, Property_City__c, Property_State__c, Property_Zip__c "
     "FROM Opportunity WHERE Property_Address__c != null LIMIT 50")
n_clean = n_dirty = 0
for r in sf.query(q)['records']:
    a = r.get('Property_Address__c') or ''
    c = r.get('Property_City__c') or ''
    if c and c.upper() in a.upper():
        n_dirty += 1
        if n_dirty <= 5:
            print(f"  DIRTY (city in addr): addr={a!r} city={c!r}")
    else:
        n_clean += 1
print(f"\n  Clean (city NOT in address): {n_clean}")
print(f"  Dirty (city embedded in address): {n_dirty}")

# State field normalisation
print('\nState field values across the org (top values):')
from collections import Counter
states = [r.get('Property_State__c') for r in sf.query_all(
    "SELECT Property_State__c FROM Opportunity WHERE Property_State__c != null"
)['records']]
for s, n in Counter(states).most_common(15):
    print(f"  {s!r}: {n}")
