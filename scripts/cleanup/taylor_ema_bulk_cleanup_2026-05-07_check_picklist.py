"""Check current Substatus__c picklist values + dependencies.

Goal: figure out which of Taylor's 5 values are already in the picklist,
which (if any) are new, and which are valid for the current stage of each Opp.
"""
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

TAYLOR_VALUES = [
    'ISP or Funding Needed',
    'Incumbent EMA',
    'Bulk/EMA Rejected',
    'No Marketing/Bulk Needed',
    'Owner Unresponsive',
]

# Pull global Substatus picklist values
desc = sf.Opportunity.describe()
substatus_field = next((f for f in desc['fields'] if f['name'] == 'Substatus__c'), None)
if not substatus_field:
    print('Substatus__c not found on Opportunity!')
    raise SystemExit(1)

print('== Substatus__c global picklist values ==')
all_pl_values = [pv['value'] for pv in substatus_field['picklistValues']]
for pv in substatus_field['picklistValues']:
    print(f'  {"[ACTIVE]" if pv["active"] else "[INACT] "} {pv["value"]!r}'
          f' (label={pv.get("label")})')
print(f'  total: {len(all_pl_values)} values\n')

print('== Taylor\'s 5 values vs global picklist ==')
for v in TAYLOR_VALUES:
    in_pl = v in all_pl_values
    print(f'  {"YES " if in_pl else "MISSING"}  {v!r}')

# Pull dependent picklist info via Tooling API field metadata
# (controllingField is StageName, valueSet has dependency rules)
# simple_salesforce doesn't directly expose dependent values in describe(),
# so we also need to test by stage.

# Cross-check: pull recent samples per stage where Substatus is set, see what values appear
print('\n== Currently used Substatus values per Stage (from existing data) ==')
rs = sf.query_all("""
    SELECT StageName, Substatus__c, COUNT(Id) cnt
    FROM Opportunity
    WHERE Substatus__c != NULL
    GROUP BY StageName, Substatus__c
    ORDER BY StageName, COUNT(Id) DESC
""")['records']
for r in rs:
    print(f"  [{r['StageName']}] {r['Substatus__c']!r}: {r['cnt']}")

# Check who set Substatus historically — was it Taylor?
print('\n== Who has been writing Substatus values recently? (sample of LastModifiedBy on Opps with Substatus set) ==')
rs2 = sf.query_all("""
    SELECT Substatus__c, LastModifiedBy.Name, COUNT(Id) cnt
    FROM Opportunity
    WHERE Substatus__c != NULL
    GROUP BY Substatus__c, LastModifiedBy.Name
    ORDER BY COUNT(Id) DESC
""")['records']
for r in rs2[:30]:
    print(f"  {r['Substatus__c']!r} <- {r['LastModifiedBy']['Name']}: {r['cnt']}")
