"""Search IronClad__c records that might match the 8 target properties."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
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

KEYWORDS = [
    ("Del Mar Beach Club",          ["del mar beach", "137 S Shore", "137 South Shore"]),
    ("Del Mar Shores Terrace",      ["del mar shores", "180 Del Mar Shores"]),
    ("Las Brisas",                  ["las brisas", "135 S Sierra", "135 South Sierra"]),
    ("Seascape Chateau",            ["seascape chateau", "707 S Sierra", "707 South Sierra"]),
    ("Seascape Shores",             ["seascape shores", "325 S Sierra", "325 South Sierra"]),
    ("Surfsong",                    ["surfsong", "205 S Helix", "205 South Helix"]),
    ("Oceanic Drive",               ["oceanic", "1145 Oceanic"]),
    ("Portico At Rancho Carrillo",  ["portico", "rancho carrillo", "terraza portico"]),
]


def dq(s):
    return s.replace("'", "\\'")


for label, keys in KEYWORDS:
    conds = []
    for k in keys:
        k = dq(k)
        conds.append(f"Property_Name__c LIKE '%{k}%'")
        conds.append(f"Counterparty_Name__c LIKE '%{k}%'")
        conds.append(f"Property_Address__c LIKE '%{k}%'")
        conds.append(f"Record_Name__c LIKE '%{k}%'")
    where = " OR ".join(conds)
    soql = f"""
        SELECT Id, Name, Record_Name__c, IronClad_Id__c, Record_Type_IC__c,
               Contract_Status__c, Stage_IC__c, Agreement_Date__c, Executed_Date__c,
               Effective_Date__c, Expiration_Date__c,
               Property_Name__c, Property_Address__c, Property_City__c, Property_State__c,
               Counterparty_Name__c, Counterparty_Signer_Name__c, Number_of_Units_ROE__c,
               Workflow_Link__c, Repository_Link__c, Matched__c, Agreement__c
        FROM IronClad__c
        WHERE ({where})
        LIMIT 100
    """
    try:
        rows = sf.query_all(soql)["records"]
    except Exception as e:
        print(f"\n▶ {label}: query error: {e}")
        continue
    print(f"\n▶ {label}: {len(rows)} IronClad record(s)")
    for r in rows:
        print(f"  • {r.get('Name')} | IC: {r.get('IronClad_Id__c')} | Type: {r.get('Record_Type_IC__c')} | Status: {r.get('Contract_Status__c')} | Stage: {r.get('Stage_IC__c')}")
        print(f"    Record Name: {r.get('Record_Name__c')}")
        print(f"    Property: {r.get('Property_Name__c')} | {r.get('Property_Address__c')}, {r.get('Property_City__c')}, {r.get('Property_State__c')}")
        print(f"    Counterparty: {r.get('Counterparty_Name__c')} (signer: {r.get('Counterparty_Signer_Name__c')})")
        print(f"    Units ROE: {r.get('Number_of_Units_ROE__c')} | Matched to SF Ag: {r.get('Matched__c')} | Ag: {r.get('Agreement__c')}")
        print(f"    Agreement Date: {r.get('Agreement_Date__c')} | Executed: {r.get('Executed_Date__c')} | Effective: {r.get('Effective_Date__c')} | Exp: {r.get('Expiration_Date__c')}")
        print(f"    Workflow: {r.get('Workflow_Link__c')}")
        print(f"    Repository: {r.get('Repository_Link__c')}")
