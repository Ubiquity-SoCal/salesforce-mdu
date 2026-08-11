"""Look at how existing Accounts are classified — what Type values, Industry, fields used."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import Counter
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# All Account fields including standard ones we may have missed
print("=== ALL Account fields (standard + custom) ===")
d = sf.Account.describe()
for f in d['fields']:
    n, label, t = f['name'], f['label'], f['type']
    extra = ''
    if t == 'picklist':
        vals = [v['value'] for v in f.get('picklistValues', []) if v.get('active')]
        extra = f"  values={vals[:15]}{'...' if len(vals)>15 else ''}"
    print(f"  {n:45s} {label[:35]:35s} {t:12s}{extra}")

print(f"\n=== Existing Account count + Type distribution ===")
all_accts = sf.query_all("SELECT Id, Name, Type, Industry FROM Account")['records']
print(f"  Total Accounts: {len(all_accts)}")
type_dist = Counter(a.get('Type') for a in all_accts)
print(f"  Type distribution:")
for t, n in type_dist.most_common():
    print(f"    {n:4d}  {t}")
ind_dist = Counter(a.get('Industry') for a in all_accts)
print(f"  Industry distribution (top 15):")
for ind, n in ind_dist.most_common(15):
    print(f"    {n:4d}  {ind}")

print(f"\n=== Sample existing Accounts (first 30) ===")
for a in all_accts[:30]:
    print(f"  {a['Name'][:55]:55s} Type={a.get('Type')!s:15s} Industry={a.get('Industry')!s:25s}")

# Check what Opportunity.Management_Company__c references
print(f"\n=== Opportunity.Management_Company__c reference target ===")
od = sf.Opportunity.describe()
for f in od['fields']:
    if f['name'] == 'Management_Company__c':
        print(f"  references: {f.get('referenceTo')}")
        print(f"  relationshipName: {f.get('relationshipName')}")

# Are there any Opps with Management_Company__c populated already?
mc_filled = sf.query("SELECT COUNT(Id) FROM Opportunity WHERE Management_Company__c != null")['records'][0]
print(f"\n  Opps with Management_Company__c populated: {mc_filled.get('expr0')}")

# How many have AccountId populated?
ai_filled = sf.query("SELECT COUNT(Id) FROM Opportunity WHERE AccountId != null")['records'][0]
print(f"  Opps with AccountId populated: {ai_filled.get('expr0')}")

# Sample of Opps with Account
print(f"\n=== Sample Opps with both AccountId and Management_Company__c (if any) ===")
sample = sf.query_all("SELECT Id, Name, Account.Name, Account.Type, Management_Company__r.Name, Management_Company__r.Type FROM Opportunity WHERE Management_Company__c != null LIMIT 10")['records']
for s in sample:
    a = s.get('Account') or {}
    mc = s.get('Management_Company__r') or {}
    print(f"  {s['Name'][:45]:45s}")
    print(f"    Account: {a.get('Name')!s:40s} Type={a.get('Type')}")
    print(f"    MC:      {mc.get('Name')!s:40s} Type={mc.get('Type')}")
