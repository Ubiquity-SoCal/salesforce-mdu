"""
Read-only probe #2 for the Signed PALs report.
Decides report-type strategy by checking real data:
  1. Relationship nature (master-detail vs lookup) for Agreement->Opp and ST->Opp
     -> tells us if native roll-up summaries onto Opportunity are possible.
  2. Population overlap: signed-PAL Opps vs SiteTracker projects vs Build_Status/Activation.
     -> tells us if "Opp with SiteTracker" inner join would drop the not-building population.
  3. Picklist values for ambiguous Excel columns (MDU/SFU/MHP, Lead, Status).
"""
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
print(f"Connected: {sf.sf_instance}\n")

# ---- 1. relationship nature ----
print("===== Relationship nature (master-detail vs lookup) =====")
for obj, fld in [("Agreement__c", "Opportunity__c"), ("SiteTracker_Project__c", "Opportunity__c")]:
    d = getattr(sf, obj).describe()
    f = next(x for x in d["fields"] if x["name"] == fld)
    kind = "MASTER-DETAIL" if f.get("cascadeDelete") else "lookup"
    print(f"  {obj}.{fld}: {kind}  (cascadeDelete={f.get('cascadeDelete')}, "
          f"relationshipOrder={f.get('relationshipOrder')}, writeReqMasterRead={f.get('writeRequiresMasterRead')})")

# ---- 2. population overlap ----
print("\n===== Population: signed PALs =====")
def c(q):
    return sf.query(q)["records"][0]["c"]

pal_agr = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null")
roe_agr = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Agreement_Type__c='ROE' AND Signed_Date__c!=null")
print(f"  Agreement PAL signed: {pal_agr}   ROE signed: {roe_agr}")

opp_signed_pal = c("SELECT COUNT(Id) c FROM Opportunity WHERE Id IN "
                   "(SELECT Opportunity__c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null)")
print(f"  distinct Opps w/ signed PAL agreement: {opp_signed_pal}")

# of those Opps, how many have a SiteTracker project at all / with build status / with activation
opp_w_st = c("SELECT COUNT(Id) c FROM Opportunity WHERE Id IN "
             "(SELECT Opportunity__c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null) "
             "AND Id IN (SELECT Opportunity__c FROM SiteTracker_Project__c)")
print(f"     ...of which have >=1 SiteTracker project:        {opp_w_st}")

st_total = c("SELECT COUNT(Id) c FROM SiteTracker_Project__c")
st_build = c("SELECT COUNT(Id) c FROM SiteTracker_Project__c WHERE Build_Status__c!=null")
st_act   = c("SELECT COUNT(Id) c FROM SiteTracker_Project__c WHERE Activation_Actual__c!=null")
st_pal   = c("SELECT COUNT(Id) c FROM SiteTracker_Project__c WHERE PAL_Signed_Date__c!=null")
st_opp   = c("SELECT COUNT(Id) c FROM SiteTracker_Project__c WHERE Opportunity__c!=null")
print(f"  SiteTracker projects total={st_total}  linked-to-Opp={st_opp}  "
      f"Build_Status!=null={st_build}  Activation_Actual!=null={st_act}  PAL_Signed_Date!=null={st_pal}")

# agreement signed date vs sitetracker PAL signed date agreement (sample where both exist)
print("\n===== PAL date source agreement (sample, both present) =====")
rows = sf.query_all(
    "SELECT Opportunity__r.Name, PAL_Signed_Date__c, Opportunity__c FROM SiteTracker_Project__c "
    "WHERE PAL_Signed_Date__c!=null AND Opportunity__c!=null LIMIT 200"
)["records"]
agr_map = {}
for r in sf.query_all("SELECT Opportunity__c, Signed_Date__c FROM Agreement__c "
                      "WHERE Agreement_Type__c='PAL' AND Signed_Date__c!=null")["records"]:
    agr_map.setdefault(r["Opportunity__c"], r["Signed_Date__c"])
match=mismatch=only_st=0
for r in rows:
    a = agr_map.get(r["Opportunity__c"])
    if a is None: only_st+=1
    elif a == r["PAL_Signed_Date__c"]: match+=1
    else: mismatch+=1
print(f"  sampled ST PAL dates: match-with-agreement={match}  mismatch={mismatch}  ST-only(no agr)={only_st}")

# ---- 3. picklist values for ambiguous columns ----
print("\n===== Picklist values (ambiguous Excel columns) =====")
oppd = sf.Opportunity.describe()
for name in ["LeadSource", "Type", "MDU_Categorization__c", "Property_Category__c",
             "Substatus__c", "Sales_Status__c", "StageName"]:
    f = next((x for x in oppd["fields"] if x["name"] == name), None)
    if not f:
        print(f"  {name}: (not found)"); continue
    vals = [p["label"] for p in f["picklistValues"] if p["active"]]
    print(f"  {name} ({f['label']}): {vals[:25]}")

# Sub_Bucket formula column distinct values via data
print("\n  Sub_Bucket__c (Stage Status) distinct values in data:")
for r in sf.query_all("SELECT Sub_Bucket__c v, COUNT(Id) c FROM Opportunity WHERE Sub_Bucket__c!=null GROUP BY Sub_Bucket__c ORDER BY COUNT(Id) DESC")["records"][:20]:
    print(f"    {r['c']:>4}  {r['v']!r}")

# Is there any MDU/SFU/MHP property-type field anywhere on Opp? scan labels+names
print("\n  Opp fields mentioning property-type tokens (mdu/sfu/mhp/dwelling/property type):")
for f in oppd["fields"]:
    blob = (f["label"]+" "+f["name"]).lower()
    if any(t in blob for t in ["sfu","mhp","dwelling","propertytype","property_type","prop type"]):
        print(f"    {f['name']} | {f['label']} | {f['type']}")
