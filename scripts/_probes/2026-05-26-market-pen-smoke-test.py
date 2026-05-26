"""Smoke test for the Market Penetration tab. Mirrors the dashboard's
Q-A and Q-C queries with full pagination, then aggregates client-side
the same way the dashboard's renderMarketPen helper does.

If the dashboard's rendered numbers ever differ from this probe's output,
the render path has a bug. Probe and dashboard must agree.
"""
from collections import defaultdict
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)

# Mirror Q-A (no Hold filter — current dashboard state)
QA = """
SELECT Id, Property_Unit_Count__c, Active_Unit_Count__c, Deactive_Unit_Count__c, State__c, Lit__c
FROM Property_Location__c
WHERE Address_Type__c='Business' AND Import_Delete_Property__c=false
"""
qa = sf.query_all(QA)["records"]

# Mirror Q-C
QC = """
SELECT Id, Property_Location__r.Property_Unit_Count__c, Property_Location__r.State__c
FROM Agreement__c
WHERE Status__c='Completed'
  AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
  AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
  AND Property_Location__c != null
  AND Property_Location__r.Address_Type__c='Business'
  AND Property_Location__r.Import_Delete_Property__c=false
  AND Property_Location__r.Lit__c = false
"""
qc = sf.query_all(QC)["records"]

singles = [r for r in qa if (r.get("Property_Unit_Count__c") or 0) == 1]
multis = [r for r in qa if (r.get("Property_Unit_Count__c") or 0) > 1]
lit_singles = [r for r in singles if r.get("Lit__c") is True]
lit_multis = [r for r in multis if r.get("Lit__c") is True]
units_in_lit = sum((r.get("Property_Unit_Count__c") or 0) for r in lit_multis)
active_in_lit = sum((r.get("Active_Unit_Count__c") or 0) for r in lit_multis)

print("================================================================")
print(" MARKET PENETRATION TAB — Smoke Test (mirrors dashboard queries)")
print("================================================================")
print(f"Q-A returned: {len(qa)} Business PLs (full pagination)")
print(f"Q-C returned: {len(qc)} ROE-not-lit agreements")

print("\n=== Section 1: Single-Unit Buildings ===")
sp = (len(lit_singles) / len(singles) * 100) if singles else 0
print(f"  Total: {len(singles)}  Lit: {len(lit_singles)}  Penetration: {sp:.1f}%")
print("  By state:")
bys = defaultdict(lambda: {"total": 0, "lit": 0})
for r in singles:
    s = r.get("State__c") or "(none)"
    bys[s]["total"] += 1
    if r.get("Lit__c") is True:
        bys[s]["lit"] += 1
for s in sorted(bys):
    row = bys[s]
    pct = (row["lit"] / row["total"] * 100) if row["total"] else 0
    print(f"    {s:>6}  total={row['total']:>5}  lit={row['lit']:>4}  pen={pct:>5.1f}%")

print("\n=== Section 2: Multi-Unit Buildings ===")
dp = (active_in_lit / units_in_lit * 100) if units_in_lit else 0
print(f"  Total: {len(multis)}  Lit: {len(lit_multis)}  "
      f"Units in Lit: {int(units_in_lit)}  Active: {int(active_in_lit)}  "
      f"Door-Weighted: {dp:.1f}%")
print("  By state:")
bym = defaultdict(lambda: {"total": 0, "lit": 0, "units": 0, "active": 0})
for r in multis:
    s = r.get("State__c") or "(none)"
    bym[s]["total"] += 1
    if r.get("Lit__c") is True:
        bym[s]["lit"] += 1
        bym[s]["units"] += (r.get("Property_Unit_Count__c") or 0)
        bym[s]["active"] += (r.get("Active_Unit_Count__c") or 0)
for s in sorted(bym):
    row = bym[s]
    pct = (row["active"] / row["units"] * 100) if row["units"] else 0
    print(f"    {s:>6}  bldgs={row['total']:>5}  lit={row['lit']:>4}  "
          f"units_in_lit={int(row['units']):>5}  active={int(row['active']):>4}  door={pct:>5.1f}%")

print("\n=== Section 3: ROE Completed but Not Yet Lit ===")
s3_single = sum(1 for r in qc if ((r.get("Property_Location__r") or {}).get("Property_Unit_Count__c") or 0) == 1)
s3_multi = sum(1 for r in qc if ((r.get("Property_Location__r") or {}).get("Property_Unit_Count__c") or 0) > 1)
print(f"  Total: {len(qc)}  Single-Unit: {s3_single}  Multi-Unit: {s3_multi}")
