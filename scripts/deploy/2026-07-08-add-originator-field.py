"""Create Opportunity.Originator__c (Lookup -> User) and mirror its FLS from the existing
RE_Assigned__c field, so Originator has the exact same visibility as the RE column in the
MDU tracker.

Originator captures who ORIGINATED the opp. It is backfilled once to the current Owner
(separate script) and then frozen: reassigning Owner does NOT change Originator. New opps
start blank until someone fills it in (no auto-populate flow, per Koa 2026-07-08).

Idempotent: skips the field deploy if it already exists; FLS inserts skip dups.
Target org: fun-power-747 (PRODUCTION).
"""
import requests
from _md_deploy import connect, deploy

sf = connect()
base = f"https://{sf.sf_instance}"
hdr = {"Authorization": f"Bearer {sf.session_id}"}

FIELD = "Originator__c"
MIRROR_FROM = "RE_Assigned__c"  # existing Lookup(User) on Opportunity; clone its FLS

FIELD_XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
             '    <fields>\n'
             f'        <fullName>{FIELD}</fullName>\n'
             '        <label>Originator</label>\n'
             '        <type>Lookup</type>\n'
             '        <referenceTo>User</referenceTo>\n'
             '        <relationshipLabel>Opportunities (Originator)</relationshipLabel>\n'
             '        <relationshipName>Opportunities_Originator</relationshipName>\n'
             '        <required>false</required>\n'
             '        <deleteConstraint>SetNull</deleteConstraint>\n'
             '        <trackHistory>false</trackHistory>\n'
             '    </fields>\n'
             '</CustomObject>')

# --- 1: deploy the field (skip if present) ---
have = {f["name"] for f in sf.Opportunity.describe()["fields"]}
if FIELD in have:
    print(f"{FIELD} already exists; skipping field deploy.")
else:
    files = {"objects/Opportunity.object": FIELD_XML}
    members = [(f"Opportunity.{FIELD}", "CustomField")]
    if not deploy(sf, files, members, "originator-field"):
        raise SystemExit("field deploy failed")
    print(f"Deployed {FIELD}.")

# --- 2: mirror FLS from RE_Assigned__c to Originator__c ---
src = sf.query(f"SELECT ParentId, PermissionsRead, PermissionsEdit FROM FieldPermissions "
               f"WHERE SobjectType='Opportunity' AND Field='Opportunity.{MIRROR_FROM}'")["records"]
print(f"{MIRROR_FROM} FLS rows to mirror: {len(src)}")

existing = set()
for r in sf.query(f"SELECT ParentId FROM FieldPermissions WHERE SobjectType='Opportunity' "
                  f"AND Field='Opportunity.{FIELD}'")["records"]:
    existing.add(r["ParentId"])

created = 0
for r in src:
    pid = r["ParentId"]
    if pid in existing:
        continue
    body = {"ParentId": pid, "SobjectType": "Opportunity", "Field": f"Opportunity.{FIELD}",
            "PermissionsRead": True, "PermissionsEdit": bool(r["PermissionsEdit"])}
    resp = requests.post(f"{base}/services/data/v59.0/sobjects/FieldPermissions", headers=hdr, json=body)
    if resp.status_code in (200, 201):
        created += 1
    elif resp.status_code != 400:  # 400 = dup / not permitted on that parent, skip
        print(f"  FLS parent {pid}: {resp.status_code} {resp.text[:120]}")
print(f"FLS rows created for {FIELD}: {created}")

# --- 3: verify ---
sf2 = connect()
ok = FIELD in {f["name"] for f in sf2.Opportunity.describe()["fields"]}
fls = len(sf2.query(f"SELECT Id FROM FieldPermissions WHERE SobjectType='Opportunity' "
                    f"AND Field='Opportunity.{FIELD}' AND PermissionsRead=true")["records"])
print(f"VERIFY: {FIELD} present={ok} | FLS-read rows={fls}")
assert ok, "field missing after deploy"
