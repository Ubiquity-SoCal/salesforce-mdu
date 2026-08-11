"""Diagnostic: figure out the 2 unresolved dupe Opps + the stage discrepancy."""
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

print('== Issue 1: stage discrepancy ==')
print('Sampling 5 of the "EMA/Bulk delete" Opps to see current stage in SF\n')
sample_names = ['Baldwin Manor', 'Bali Apartments', 'Purgatory Creek Townhomes',
                'Stonebridge Gardens', 'Villas on Horne']
for n in sample_names:
    r = sf.query(f"""
        SELECT Id, Name, StageName, Owner.Name, LastModifiedDate
        FROM Opportunity WHERE Name = '{n}'
    """)['records']
    for o in r:
        print(f"  [{o['Owner']['Name']}] {o['Name']} ({o['Id']}): {o['StageName']}  lastMod={o['LastModifiedDate']}")

print('\n== Issue 2: unresolved dupes ==')

# Killeen_MDU_Bradley Arms by Tanya — try variants
print('\n-- "Killeen_MDU_Bradley Arms" search --')
for q in [
    "Name = 'Killeen_MDU_Bradley Arms'",
    "Name LIKE '%Bradley Arms%'",
    "Name LIKE '%Killeen%Bradley%' OR Name LIKE '%Bradley%Killeen%'",
]:
    rs = sf.query(f"SELECT Id, Name, Owner.Name, StageName FROM Opportunity WHERE {q}")['records']
    print(f'  query: {q}  -> {len(rs)} hits')
    for o in rs:
        print(f"    [{o['Owner']['Name']}] {o['Name']} ({o['Id']}): {o['StageName']}")

# 117 and 121 W Avenue A Apartments by Melissa
print('\n-- "117 and 121 W Avenue A Apartments" search --')
for q in [
    "Name = '117 and 121 W Avenue A Apartments'",
    "Name LIKE '%Avenue A%'",
    "Name LIKE '%117%121%'",
]:
    rs = sf.query(f"SELECT Id, Name, Owner.Name, StageName FROM Opportunity WHERE {q}")['records']
    print(f'  query: {q}  -> {len(rs)} hits')
    for o in rs:
        print(f"    [{o['Owner']['Name']}] {o['Name']} ({o['Id']}): {o['StageName']}")

# the one that DID match — maybe by direct Id so we know which version
print('\n-- "Killeen_MDU_The Bungalows" (the 1 that resolved) --')
rs = sf.query("SELECT Id, Name, Owner.Name, StageName FROM Opportunity WHERE Name LIKE '%Bungalows%'")['records']
for o in rs:
    print(f"    [{o['Owner']['Name']}] {o['Name']} ({o['Id']}): {o['StageName']}")
