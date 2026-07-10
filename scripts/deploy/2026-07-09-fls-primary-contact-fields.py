"""
Grant FLS on the three new Opportunity fields by mirroring an existing, known-visible field.

Metadata API does NOT grant System Administrator FLS on new CustomFields, so they deploy
invisible (see memory: sf-customfield-fls-system-admin). Mirror the FieldPermissions of
Opportunity.Property_Category__c, which renders correctly today.

Usage:
    python 2026-07-09-fls-primary-contact-fields.py          # dry run
    python 2026-07-09-fls-primary-contact-fields.py --apply
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

TEMPLATE = "Opportunity.Property_Category__c"
NEW_FIELDS = [
    "Opportunity.Primary_Contact__c",
    "Opportunity.Primary_Contact_Role__c",
    "Opportunity.Contact_Count__c",
]
APPLY = "--apply" in sys.argv

sf = Salesforce(*creds())

tmpl = sf.query_all(
    "SELECT ParentId, Parent.Label, PermissionsRead, PermissionsEdit "
    f"FROM FieldPermissions WHERE SobjectType='Opportunity' AND Field='{TEMPLATE}' "
    "AND PermissionsRead=true"
)["records"]
print(f"{TEMPLATE} is readable on {len(tmpl)} permission parents:")
for t in tmpl:
    print(f"  {t['ParentId']}  read={t['PermissionsRead']} edit={t['PermissionsEdit']}  "
          f"{(t.get('Parent') or {}).get('Label')}")

existing = sf.query_all(
    "SELECT ParentId, Field FROM FieldPermissions WHERE SobjectType='Opportunity' "
    "AND Field IN ('" + "','".join(NEW_FIELDS) + "')"
)["records"]
have = {(e["ParentId"], e["Field"]) for e in existing}

todo = []
for f in NEW_FIELDS:
    for t in tmpl:
        if (t["ParentId"], f) in have:
            continue
        todo.append({
            "ParentId": t["ParentId"],
            "SobjectType": "Opportunity",
            "Field": f,
            "PermissionsRead": True,
            # Contact_Count / Role are system-maintained: read-only for everyone.
            # Primary_Contact mirrors the template's edit right.
            "PermissionsEdit": bool(t["PermissionsEdit"]) if f.endswith("Primary_Contact__c") else False,
        })

print(f"\nFieldPermissions to create: {len(todo)}")
if not APPLY:
    for r in todo[:6]:
        print("  ", r)
    print("\nDRY RUN. pass --apply to write.")
    sys.exit(0)

ok = err = 0
for r in todo:
    try:
        sf.FieldPermissions.create(r)
        ok += 1
    except Exception as e:
        err += 1
        print(f"  FAIL {r['Field']} on {r['ParentId']}: {str(e)[:120]}")
print(f"\ncreated={ok} failed={err}")

# verify
check = sf.query_all(
    "SELECT Field, COUNT(Id) c FROM FieldPermissions WHERE SobjectType='Opportunity' "
    "AND Field IN ('" + "','".join(NEW_FIELDS) + "') AND PermissionsRead=true "
    "GROUP BY Field"
)["records"]
print("\nVERIFY readable parents per field:")
for c in check:
    print(f"  {c['Field']:40s} {c['c']}")
