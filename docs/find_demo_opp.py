"""
Finds the best MDU Opportunity to use as a demo/training record.

Scoring criteria (a good demo record should have):
- Agreements (PAL + something else ideally)
- Notes (multiple)
- Opportunity Contacts (multiple roles)
- SiteTracker Project linked
- Property Location linked
- Stage somewhere interesting (Under Contract or Engaged, not just Closed Lost)
- City/State/Zip populated
- Agreement_Name populated

Outputs a top-10 ranked list with counts and links.
"""

from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)

print("Connected. Querying Opportunities...")

# Get MDU Opps with related counts
soql = """
SELECT Id, Name, StageName, Sales_Status__c,
       Property_City__c, Property_State__c, Property_Zip__c,
       Units__c, Property_Type__c,
       Agreement_Name__c, SiteTracker_Project_ID__c, SiteTracker_URL__c,
       Property_Location__c,
       Agreement_Count__c, Notes_Count__c,
       (SELECT Id FROM Agreements__r),
       (SELECT Id, Role__c FROM Opportunity_Contacts__r),
       Owner.Name
FROM Opportunity
WHERE RecordType.DeveloperName = 'MDU'
  AND SiteTracker_Project_ID__c != NULL
  AND Property_City__c != NULL
  AND Property_State__c != NULL
  AND Property_Zip__c != NULL
  AND Agreement_Name__c != NULL
  AND Notes_Count__c > 2
  AND Agreement_Count__c > 0
LIMIT 200
"""

result = sf.query_all(soql)
records = result["records"]
print(f"Found {len(records)} candidate Opps.\n")


def score(r):
    s = 0
    s += min(r.get("Agreement_Count__c") or 0, 5) * 4   # up to 20
    s += min(r.get("Notes_Count__c") or 0, 10) * 2       # up to 20
    oc = (r.get("Opportunity_Contacts__r") or {}).get("records", []) if r.get("Opportunity_Contacts__r") else []
    s += min(len(oc), 5) * 3                              # up to 15
    if r.get("SiteTracker_URL__c"):
        s += 5
    if r.get("Property_Location__c"):
        s += 5
    stage = r.get("StageName") or ""
    if stage in ("Under Contract", "Engaged", "Contract Negotiations", "ROE Secured"):
        s += 8
    elif stage == "Prospecting":
        s += 3
    if r.get("Property_Type__c"):
        s += 2
    if (r.get("Units__c") or 0) >= 25:
        s += 2
    return s


scored = sorted(records, key=score, reverse=True)
top = scored[:10]

print("=" * 100)
print(f"{'Score':<6} {'Name':<35} {'Stage':<22} {'City, ST':<22} {'Agr':<4} {'Notes':<6} {'Contacts':<8}")
print("=" * 100)
for r in top:
    oc_count = len((r.get("Opportunity_Contacts__r") or {}).get("records", []) if r.get("Opportunity_Contacts__r") else [])
    name = (r["Name"] or "")[:33]
    city = f"{(r.get('Property_City__c') or '')[:18]}, {r.get('Property_State__c') or ''}"
    print(f"{score(r):<6} {name:<35} {(r['StageName'] or '')[:20]:<22} {city:<22} "
          f"{int(r.get('Agreement_Count__c') or 0):<4} "
          f"{int(r.get('Notes_Count__c') or 0):<6} "
          f"{oc_count:<8}")

print()
print("Top pick details:")
print("-" * 100)
top1 = top[0]
print(f"Name:         {top1['Name']}")
print(f"Owner:        {top1.get('Owner', {}).get('Name', '')}")
print(f"Stage:        {top1['StageName']}  /  Sales Status: {top1.get('Sales_Status__c')}")
print(f"Property:     {top1.get('Property_City__c')}, {top1.get('Property_State__c')} {top1.get('Property_Zip__c')}")
print(f"Type:         {top1.get('Property_Type__c')}  /  Units: {top1.get('Units__c')}")
print(f"Agreement:    {top1.get('Agreement_Name__c')}")
print(f"ST Project:   {top1.get('SiteTracker_Project_ID__c')}")
print(f"Agr count:    {int(top1.get('Agreement_Count__c') or 0)}")
print(f"Notes count:  {int(top1.get('Notes_Count__c') or 0)}")
print(f"Lightning:    https://fun-power-747.lightning.force.com/lightning/r/Opportunity/{top1['Id']}/view")

print()
print("Next 3 alternates (in case top pick has issues):")
for r in top[1:4]:
    print(f"  - {r['Name']}  https://fun-power-747.lightning.force.com/lightning/r/Opportunity/{r['Id']}/view")
