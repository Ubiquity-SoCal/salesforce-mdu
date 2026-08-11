"""Baseline ground-truth counts for the Market Penetration tab.
Frozen on 2026-05-26. Re-run to verify the dashboard renders matching numbers."""
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

UNIV = "Address_Type__c='Business' AND Import_Delete_Property__c=false"

def c(where):
    return sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {where}")["totalSize"]

print("=== Universe ===")
print(f"  Total Business PLs:    {c(UNIV)}")
print(f"  Single-unit:           {c(UNIV + ' AND Property_Unit_Count__c = 1')}")
print(f"  Multi-unit:            {c(UNIV + ' AND Property_Unit_Count__c > 1')}")

print("\n=== Lit (drop active or churned) ===")
LIT = UNIV + " AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)"
print(f"  Lit total:             {c(LIT)}")
print(f"  Lit single-unit:       {c(LIT + ' AND Property_Unit_Count__c = 1')}")
print(f"  Lit multi-unit:        {c(LIT + ' AND Property_Unit_Count__c > 1')}")

print("\n=== Multi-unit lit door rollups ===")
r = sf.query(f"""
    SELECT SUM(Property_Unit_Count__c) total_units,
           SUM(Active_Unit_Count__c) active_units
    FROM Property_Location__c
    WHERE {LIT} AND Property_Unit_Count__c > 1
""")["records"][0]
print(f"  Units in lit multi:    {int(r['total_units'] or 0)}")
print(f"  Active units in lit:   {int(r['active_units'] or 0)}")
if r["total_units"]:
    pct = (r["active_units"] or 0) / r["total_units"] * 100
    print(f"  Door-weighted pen:     {pct:.1f}%")

print("\n=== ROE completed but not yet lit ===")
ROE = """
    Id IN (
      SELECT Property_Location__c FROM Agreement__c
      WHERE Status__c='Completed'
        AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
        AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
        AND Property_Location__c != null
    )
"""
NOT_LIT = UNIV + " AND Active_Unit_Count__c = 0 AND Deactive_Unit_Count__c = 0"
print(f"  PLs with completed ROE total:        {c(UNIV + ' AND ' + ROE)}")
print(f"  ROE complete + NOT lit:              {c(NOT_LIT + ' AND ' + ROE)}")
print(f"  ROE complete + NOT lit, single-unit: {c(NOT_LIT + ' AND ' + ROE + ' AND Property_Unit_Count__c = 1')}")
print(f"  ROE complete + NOT lit, multi-unit:  {c(NOT_LIT + ' AND ' + ROE + ' AND Property_Unit_Count__c > 1')}")

print("\n=== By state (lit + total, all PLs) ===")
r = sf.query_all(f"""
    SELECT State__c, COUNT(Id) total
    FROM Property_Location__c
    WHERE {UNIV}
    GROUP BY State__c
    ORDER BY State__c
""")["records"]
for x in r:
    s = x["State__c"]
    lit = c(UNIV + f" AND State__c='{s}' AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)") if s else 0
    print(f"  {(s or '(null)'):>20}  total={x['total']:>5}  lit={lit:>4}")
