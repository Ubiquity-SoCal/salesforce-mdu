"""Investigate the 81 CA lit multi-unit Property_Locations that the new dashboard
shows but the 5/22 Excel doesn't. Find out what they actually are."""
from collections import Counter
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

# Pull all 81 with all interesting fields
rows = sf.query_all("""
    SELECT Id, Name, City__c, State__c,
           Property_Unit_Count__c, Active_Unit_Count__c, Deactive_Unit_Count__c,
           Priority__c, Penetration_Priority__c,
           FDH_Activated_Date__c, FDH_Name__c,
           Address_Type__c,
           Existing_Fiber_Provider__c,
           Build_Effort__c, Building_Floor_Type__c
    FROM Property_Location__c
    WHERE Address_Type__c='Business'
      AND Import_Delete_Property__c=false
      AND State__c='CA'
      AND Property_Unit_Count__c > 1
      AND Lit__c = true
    ORDER BY Active_Unit_Count__c DESC, Name
""")["records"]
print(f"Total CA lit multi-unit Business PLs: {len(rows)}\n")

# Distribution by Priority
print("=== Priority__c distribution ===")
for v, n in Counter(r.get("Priority__c") or "(null)" for r in rows).most_common():
    print(f"  {n:>4}  {v}")

print("\n=== Penetration_Priority__c distribution ===")
for v, n in Counter(r.get("Penetration_Priority__c") or "(null)" for r in rows).most_common():
    print(f"  {n:>4}  {v}")

print("\n=== City distribution (top 15) ===")
for v, n in Counter(r.get("City__c") or "(null)" for r in rows).most_common()[:15]:
    print(f"  {n:>4}  {v}")

print("\n=== Address_Type__c sanity check ===")
for v, n in Counter(r.get("Address_Type__c") or "(null)" for r in rows).most_common():
    print(f"  {n:>4}  {v}")

print("\n=== Building_Floor_Type / Build_Effort ===")
for v, n in Counter(r.get("Building_Floor_Type__c") or "(null)" for r in rows).most_common()[:8]:
    print(f"  {n:>4}  Building_Floor_Type={v}")

print("\n=== Top 20 by Active_Unit_Count ===")
for r in rows[:20]:
    print(f"  {(r.get('Name') or '')[:60]:60}  "
          f"units={int(r.get('Property_Unit_Count__c') or 0):>3}  "
          f"active={int(r.get('Active_Unit_Count__c') or 0):>3}  "
          f"deact={int(r.get('Deactive_Unit_Count__c') or 0):>3}  "
          f"city={(r.get('City__c') or '')[:18]:18}  "
          f"pri={r.get('Priority__c') or '-':<10}  "
          f"penpri={r.get('Penetration_Priority__c') or '-'}")

# Also check: would the OLD dashboard's Penetration_Priority filter catch these?
old_lit = [r for r in rows if r.get("Penetration_Priority__c") in ("Category 1", "All Active")]
print(f"\n=== Of these 81, how many pass the OLD dashboard's Penetration_Priority filter? ===")
print(f"  {len(old_lit)} (rest land in some other Penetration_Priority bucket)")
