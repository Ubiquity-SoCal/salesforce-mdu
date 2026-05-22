"""
Read-only probe for the "Signed PALs" report request.
Goal: map each target-Excel column to a real SF field, and determine how
SiteTracker_Project__c relates to Opportunity (decides report-type feasibility).

Target Excel columns:
  Name, Overall Project Status, Units, Address, Category, MDU/SFU/MHP,
  Build Type, ISP/SAQ/Ubiquity Lead?, Prospective ISP(s), Confirmed ISP(s),
  State, PAL Signed Date, Activation Date, Status
"""
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)
print(f"Connected: {sf.sf_instance}\n")


def dump_fields(obj, keywords):
    d = getattr(sf, obj).describe()
    flds = d["fields"]
    print(f"\n===== {obj}  ({len(flds)} fields) =====")
    for f in flds:
        label = (f["label"] or "").lower()
        name = (f["name"] or "").lower()
        if any(k in label or k in name for k in keywords):
            ref = ""
            if f["type"] == "reference":
                ref = " -> " + ",".join(f["referenceTo"]) + f" (rel:{f['relationshipName']})"
            print(f"  {f['name']:<34} | {f['label']:<32} | {f['type']}{ref}")
    return d


# Opportunity: hunt for every Excel column
opp_kw = ["unit", "address", "categor", "mdu", "sfu", "mhp", "build", "isp",
          "saq", "lead", "state", "activation", "status", "stage", "project",
          "signed", "pal", "roe", "street", "city"]
opp = dump_fields("Opportunity", opp_kw)

# Agreement__c: signed date + type + status
agr_kw = ["sign", "type", "status", "date", "opportunity", "property", "ironclad"]
dump_fields("Agreement__c", agr_kw)

# SiteTracker_Project__c: build status + activation + how it links up
st_kw = ["build", "status", "activation", "mdu", "opportunity", "property",
         "project", "phase", "stage", "date", "address"]
dump_fields("SiteTracker_Project__c", st_kw)

# Relationship: child relationships hanging off Opportunity
print("\n\n===== Opportunity child relationships =====")
for cr in opp["childRelationships"]:
    if cr.get("childSObject") in (
        "Agreement__c", "SiteTracker_Project__c", "Property_Unit__c",
        "Opportunity_Contact__c", "Lit_Fiber__c",
    ) or "site" in (cr.get("childSObject") or "").lower():
        print(f"  child={cr['childSObject']:<26} via field={cr.get('field')}  relName={cr.get('relationshipName')}")

# Does SiteTracker_Project__c point at Opportunity directly, or only via Property_Location?
print("\n===== SiteTracker_Project__c reference fields =====")
std = sf.SiteTracker_Project__c.describe()
for f in std["fields"]:
    if f["type"] == "reference":
        print(f"  {f['name']:<34} -> {','.join(f['referenceTo'])} (rel:{f['relationshipName']})")
