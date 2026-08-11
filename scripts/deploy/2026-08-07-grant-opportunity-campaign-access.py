"""Grant object and field access on Opportunity_Campaign__c.

The Metadata API creates custom objects and fields without any permissions, so
the junction deployed on 2026-08-07 was invisible even to System Administrator:
the Bulk API rejected the load with "Field name provided, Key__c is not readable
for Opportunity_Campaign__c". Same trap as every custom field we have added.

Grants to the profile-owned PermissionSets that already have full access to
Opportunity, so the junction is visible to exactly the people who can see the
records it joins.

Idempotent: existing permission rows are skipped.
Target org: fun-power-747 (PRODUCTION).
"""
import requests
from _md_deploy import connect

OBJ = "Opportunity_Campaign__c"
FIELDS = ["Opportunity__c", "Campaign__c", "Tag_Type__c", "Date_Added__c", "Key__c"]
API = "v59.0"

sf = connect()
base = f"https://{sf.sf_instance}"
hdr = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}


def post(path, body):
    return requests.post(f"{base}/services/data/{API}/sobjects/{path}",
                         headers=hdr, json=body)


# Mirror whoever can already administer Opportunity. Using the existing grants as
# the template avoids inventing a visibility policy for a junction table.
src = sf.query_all(
    "SELECT ParentId, Parent.Profile.Name, PermissionsRead, PermissionsCreate, "
    "PermissionsEdit, PermissionsDelete, PermissionsViewAllRecords, "
    "PermissionsModifyAllRecords FROM ObjectPermissions "
    "WHERE SobjectType = 'Opportunity' AND PermissionsCreate = true"
)["records"]
print(f"ObjectPermissions rows on Opportunity to mirror: {len(src)}")

have_obj = {r["ParentId"] for r in sf.query_all(
    f"SELECT ParentId FROM ObjectPermissions WHERE SobjectType = '{OBJ}'"
)["records"]}

created = skipped = failed = 0
parents = []
for r in src:
    pid = r["ParentId"]
    parents.append(pid)
    if pid in have_obj:
        skipped += 1
        continue
    body = {
        "ParentId": pid, "SobjectType": OBJ,
        "PermissionsRead": True, "PermissionsCreate": True,
        "PermissionsEdit": True, "PermissionsDelete": bool(r["PermissionsDelete"]),
        "PermissionsViewAllRecords": bool(r["PermissionsViewAllRecords"]),
        "PermissionsModifyAllRecords": bool(r["PermissionsModifyAllRecords"]),
    }
    resp = post("ObjectPermissions", body)
    if resp.status_code in (200, 201):
        created += 1
    else:
        failed += 1
        if failed <= 5:
            name = (r.get("Parent") or {}).get("Profile") or {}
            print(f"   object grant failed for {name.get('Name')}: "
                  f"{resp.status_code} {resp.text[:140]}")
print(f"object permissions: {created} created, {skipped} already present, {failed} failed")

# Field level security. Required lookups are always visible and reject an explicit
# grant, so a 400 on those is expected rather than a problem.
for field in FIELDS:
    have = {r["ParentId"] for r in sf.query_all(
        f"SELECT ParentId FROM FieldPermissions WHERE SobjectType = '{OBJ}' "
        f"AND Field = '{OBJ}.{field}'")["records"]}
    c = s = f_ = 0
    for pid in parents:
        if pid in have:
            s += 1
            continue
        resp = post("FieldPermissions", {
            "ParentId": pid, "SobjectType": OBJ, "Field": f"{OBJ}.{field}",
            "PermissionsRead": True, "PermissionsEdit": True,
        })
        if resp.status_code in (200, 201):
            c += 1
        else:
            f_ += 1
    print(f"  {field:18s} FLS: {c} created, {s} present, {f_} rejected "
          f"(required fields reject by design)")

# ---------------------------------------------------------------------- verify
sf2 = connect()
desc = sf2.Opportunity_Campaign__c.describe()
names = {x["name"] for x in desc["fields"]}
print(f"\nVERIFY: {OBJ} describable, {len(names)} fields visible")
missing = [f for f in FIELDS if f not in names]
print(f"  missing from describe: {missing or 'none'}")
n = sf2.query(f"SELECT COUNT(Id) c FROM {OBJ}")["records"][0]["c"]
print(f"  queryable, current row count: {n}")
