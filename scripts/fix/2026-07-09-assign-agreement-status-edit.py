"""
Assign the 'Agreement Status Edit' permission set to the MDU team.

Run AFTER deploying deploys/2026-07-09-agreement-status-editable/.

Grants Edit on Agreement__c.Status__c to every active user on the
'Standard User - Custom' profile so they can clear the Stale EMA/Bulk cleanup
tile themselves. Two validation rules constrain what they can actually do:
  Lock_Status_When_IronClad_Linked  -- no edits on IronClad-linked agreements
  Restrict_Status_Edits_Non_Admin   -- only Cancelled / Paused

Idempotent. Dry-run by default; pass --apply to write.
Reversible: delete the permission set, or unassign, to undo.

Creds come from api/Salesforce_Credentials.txt (gitignored). Do not hardcode.

Usage:
  python 2026-07-09-assign-agreement-status-edit.py           # preview
  python 2026-07-09-assign-agreement-status-edit.py --apply
"""
import os
import sys
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

APPLY = "--apply" in sys.argv
PS_NAME = "Agreement_Status_Edit"
PROFILE = "Standard User - Custom"

CRED_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "api",
                         "Salesforce_Credentials.txt")


def load_creds(path):
    creds = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if ":" in line:
                k, v = line.split(":", 1)
                creds[k.strip().lower()] = v.strip()
    missing = [k for k in ("username", "password", "security token") if k not in creds]
    if missing:
        print(f"[ERROR] {path} missing: {', '.join(missing)}")
        sys.exit(1)
    return creds


c = load_creds(CRED_PATH)
sf = Salesforce(username=c["username"], password=c["password"],
                security_token=c["security token"])

print(f"=== {'APPLY' if APPLY else 'DRY-RUN'} ===\n")

ps = sf.query(f"SELECT Id, Name FROM PermissionSet WHERE Name = '{PS_NAME}'")["records"]
if not ps:
    print(f"[ERROR] permission set '{PS_NAME}' not found. Deploy it first:")
    print("  cd deploys/2026-07-09-agreement-status-editable && sf project deploy start -x package.xml")
    sys.exit(1)
ps_id = ps[0]["Id"]
print(f"permission set {PS_NAME} = {ps_id}")

users = sf.query(f"SELECT Id, Name, Username FROM User "
                 f"WHERE IsActive = true AND Profile.Name = '{PROFILE}'")["records"]
print(f"active users on '{PROFILE}': {len(users)}")

assigned = {r["AssigneeId"] for r in sf.query(
    f"SELECT AssigneeId FROM PermissionSetAssignment WHERE PermissionSetId = '{ps_id}'"
)["records"]}
print(f"already assigned: {len(assigned)}\n")

todo = [u for u in users if u["Id"] not in assigned]
if not todo:
    print("nothing to do -- every active user on the profile already has it.")
    sys.exit(0)

ok = fail = 0
for u in todo:
    if not APPLY:
        print(f"  would assign  {u['Name']} ({u['Username']})")
        continue
    try:
        sf.PermissionSetAssignment.create({"AssigneeId": u["Id"], "PermissionSetId": ps_id})
        print(f"  assigned      {u['Name']} ({u['Username']})")
        ok += 1
    except Exception as e:
        print(f"  ! FAILED      {u['Name']}: {e}")
        fail += 1

print(f"\nto assign: {len(todo)}")
if APPLY:
    print(f"assigned ok={ok} fail={fail}")
    assert ok + fail == len(todo), "assignment counts do not sum"
else:
    print("dry-run -- nothing written. re-run with --apply")
