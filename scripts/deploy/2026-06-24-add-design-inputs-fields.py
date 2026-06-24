"""Add the 'Design Inputs Received' + 'Ready for Engineering' columns Taylor asked
for (2026-06-23) to the MDU Agreements Milestone Tracker pipeline. Fast-follow of the
2026-06-18 milestone-fields work — same mirror -> surface -> report path.

Taylor: "Design Inputs Received (A) ... it would tell the team if we are still pending
the items from the sales team to officially hand over the project to engineering."
The matching SiteTracker MDU_Fiber__c fields (found via probe):
  Desktop_Design_Inputs_A__c   "Desktop Design Inputs and Floor Plan (A)"  (50% populated)
  Ready_for_Engineering__c     "Ready for Engineering?"  (boolean, 207 true)

This script (additive, no record mutation here):
  1. Mirror SiteTracker_Project__c:
       Desktop_Design_Inputs_A__c   (Date)
       Ready_for_Engineering__c     (Checkbox)
  2. Opportunity (surfaced from mirror by surface_to_opportunity.py):
       ST_Design_Inputs_Received__c (Date)
       ST_Ready_for_Engineering__c  (Checkbox)
  3. FLS read on the 2 Opp fields for System Administrator + Standard User - Custom
     (same profiles that already see the other ST_* milestone fields).

The sync (sync_sitetracker.py) + surface (surface_to_opportunity.py) FIELD_MAP edits
that actually populate these live in the Automation repo and are handled separately.
"""
import requests
from _md_deploy import connect, deploy

sf = connect()
base = f"https://{sf.sf_instance}"
hdr = {"Authorization": f"Bearer {sf.session_id}"}

# ── 1 + 2: metadata fields (granular CustomField members, no object headers) ──
MIRROR = "SiteTracker_Project__c"
MIRROR_FIELDS = [  # (api, label, xml-type-block)
    ("Desktop_Design_Inputs_A__c", "Desktop Design Inputs and Floor Plan (A)", "<type>Date</type>"),
    ("Ready_for_Engineering__c", "Ready for Engineering?",
     "<type>Checkbox</type><defaultValue>false</defaultValue>"),
]
OPP_FIELDS = [
    ("ST_Design_Inputs_Received__c", "ST Design Inputs Received (A)", "<type>Date</type>"),
    ("ST_Ready_for_Engineering__c", "ST Ready for Engineering",
     "<type>Checkbox</type><defaultValue>false</defaultValue>"),
]


def field_frag(api, label, typeblock):
    return (f"    <fields>\n        <fullName>{api}</fullName>\n"
            f"        <label>{label}</label>\n        {typeblock}\n    </fields>\n")


def object_xml(fields):
    body = "".join(field_frag(*f) for f in fields)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            f'{body}</CustomObject>')


mirror_have = {f["name"] for f in getattr(sf, MIRROR).describe()["fields"]}
opp_have = {f["name"] for f in sf.Opportunity.describe()["fields"]}
mirror_todo = [f for f in MIRROR_FIELDS if f[0] not in mirror_have]
opp_todo = [f for f in OPP_FIELDS if f[0] not in opp_have]
print(f"Mirror fields to create: {[f[0] for f in mirror_todo] or 'none'}")
print(f"Opp fields to create:    {[f[0] for f in opp_todo] or 'none'}")

files, members = {}, []
if mirror_todo:
    files[f"objects/{MIRROR}.object"] = object_xml(mirror_todo)
    members += [(f"{MIRROR}.{f[0]}", "CustomField") for f in mirror_todo]
if opp_todo:
    files["objects/Opportunity.object"] = object_xml(opp_todo)
    members += [(f"Opportunity.{f[0]}", "CustomField") for f in opp_todo]

if members:
    if not deploy(sf, files, members, "design-inputs-fields"):
        raise SystemExit("field deploy failed")
else:
    print("All fields already exist; skipping field deploy.")

# ── 3: FLS read on the 2 Opp fields (FieldPermissions REST, idempotent) ──
opp_field_names = [f[0] for f in OPP_FIELDS]
ps = sf.query("SELECT Id, Profile.Name FROM PermissionSet WHERE IsOwnedByProfile=true "
              "AND Profile.Name IN ('System Administrator','Standard User - Custom')")["records"]
permsets = {r["Profile"]["Name"]: r["Id"] for r in ps}
print("Target perm sets:", permsets)

have = set()
inlist = ",".join("'Opportunity.%s'" % n for n in opp_field_names)
for r in sf.query("SELECT ParentId, Field FROM FieldPermissions WHERE SobjectType='Opportunity' "
                  f"AND Field IN ({inlist})")["records"]:
    have.add((r["ParentId"], r["Field"]))

created = 0
for n in opp_field_names:
    for pname, pid in permsets.items():
        if (pid, f"Opportunity.{n}") in have:
            continue
        body = {"ParentId": pid, "SobjectType": "Opportunity",
                "Field": f"Opportunity.{n}", "PermissionsRead": True, "PermissionsEdit": False}
        r = requests.post(f"{base}/services/data/v63.0/sobjects/FieldPermissions", headers=hdr, json=body)
        print(f"  FLS {pname:24} {n:32} -> {r.status_code}")
        if r.status_code in (200, 201):
            created += 1
        elif r.status_code != 400:  # 400 = already exists / dup, fine
            print("     ", r.text[:200])
print(f"FLS rows created: {created}")

# ── verify presence ──
sf2 = connect()
mok = {f["name"] for f in getattr(sf2, MIRROR).describe()["fields"]}
ook = {f["name"] for f in sf2.Opportunity.describe()["fields"]}
for f in MIRROR_FIELDS:
    print(f"  mirror {f[0]:32} present={f[0] in mok}")
for f in OPP_FIELDS:
    print(f"  opp    {f[0]:32} present={f[0] in ook}")
assert all(f[0] in mok for f in MIRROR_FIELDS) and all(f[0] in ook for f in OPP_FIELDS), \
    "a field is missing after deploy"
print("OK: all 4 fields present.")
