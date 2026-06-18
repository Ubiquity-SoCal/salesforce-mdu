"""Add 6 SiteTracker milestone Date fields to Opportunity, surfaced from
SiteTracker_Project__c (lookup, so no rollup possible — sync-populated like the
existing ST_Build_Status__c / ST_Activation_Actual__c). For Niraj's MDU Agreements
Milestone Tracker. FLS read granted on the same 2 profiles that already see
ST_Activation_Actual__c: System Administrator + Standard User - Custom.

Fields (Opp <- SiteTracker_Project__c source):
  ST_Design_Phase_Complete__c          <- Design_Phase_Complete_A__c
  ST_Construction_Start_Forecast__c    <- MDU_Construction_Start_F__c
  ST_Construction_Start_Actual__c      <- MDU_Construction_Start_A__c
  ST_Construction_Complete_Forecast__c <- MDU_Construction_Complete_F__c
  ST_Construction_Complete_Actual__c   <- MDU_Construction_Complete_A__c
  ST_Activation_Forecast__c            <- Activation_Forecast__c
"""
import requests
from _md_deploy import connect, deploy

sf = connect()
base = f"https://{sf.sf_instance}"
hdr = {"Authorization": f"Bearer {sf.session_id}"}

FIELDS = [
    ("ST_Design_Phase_Complete__c", "ST Design Phase Complete (A)"),
    ("ST_Construction_Start_Forecast__c", "ST MDU Construction Start (F)"),
    ("ST_Construction_Start_Actual__c", "ST MDU Construction Start (A)"),
    ("ST_Construction_Complete_Forecast__c", "ST MDU Construction Complete (F)"),
    ("ST_Construction_Complete_Actual__c", "ST MDU Construction Complete (A)"),
    ("ST_Activation_Forecast__c", "ST MDU Activation (F)"),
]

existing = {f["name"] for f in sf.Opportunity.describe()["fields"]}
todo = [(n, l) for n, l in FIELDS if n not in existing]
print(f"{len(todo)} of {len(FIELDS)} fields to create; {len(FIELDS)-len(todo)} already exist")

if todo:
    field_xml = "".join(
        f"""<fields>
        <fullName>{n}</fullName>
        <externalId>false</externalId>
        <label>{l}</label>
        <required>false</required>
        <trackTrending>false</trackTrending>
        <type>Date</type>
    </fields>""" for n, l in todo)
    obj = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">'
           f"{field_xml}</CustomObject>")
    members = [(f"Opportunity.{n}", "CustomField") for n, _ in todo]
    if not deploy(sf, {"objects/Opportunity.object": obj}, members, "st-milestone-fields"):
        raise SystemExit("field deploy failed")

# FLS via FieldPermissions inserts (read-only) on the 2 profiles' owned perm sets.
ps = sf.query("SELECT Id, Profile.Name FROM PermissionSet WHERE IsOwnedByProfile=true "
              "AND Profile.Name IN ('System Administrator','Standard User - Custom')")["records"]
permsets = {r["Profile"]["Name"]: r["Id"] for r in ps}
print("Target perm sets:", permsets)

# Existing FLS to avoid dup-insert errors
have = set()
for r in sf.query("SELECT ParentId, Field FROM FieldPermissions WHERE SobjectType='Opportunity' "
                  "AND Field IN (" + ",".join("'Opportunity.%s'" % n for n, _ in FIELDS) + ")")["records"]:
    have.add((r["ParentId"], r["Field"]))

created = 0
for n, _ in FIELDS:
    for pname, pid in permsets.items():
        key = (pid, f"Opportunity.{n}")
        if key in have:
            continue
        body = {"ParentId": pid, "SobjectType": "Opportunity",
                "Field": f"Opportunity.{n}", "PermissionsRead": True, "PermissionsEdit": False}
        r = requests.post(f"{base}/services/data/v63.0/sobjects/FieldPermissions", headers=hdr, json=body)
        print(f"  FLS {pname:24} {n:38} -> {r.status_code}")
        if r.status_code in (200, 201):
            created += 1
        else:
            print("     ", r.text[:200])
print(f"FLS rows created: {created}")
