"""
Fix: FLS-stripped report filters on the MDU Cleanup Dashboard.

Root cause: 'Standard User - Custom' profile (Rosemarie Shortino) lacks Read on 4
read-only formula/rollup Opportunity fields that are used as report filters. Salesforce
silently drops those filters for her, so 4 of the 8 dashboard reports return incomplete
results with no error.

Fix: dedicated permission set 'MDU Cleanup Report Access' granting Read on the 4 fields,
assigned to Rose. Scoped + reversible (delete the perm set / unassign to undo).

Idempotent. Dry-run by default; pass --apply to write.

Usage:
  python 2026-07-02-mdu-cleanup-report-fls.py            # preview
  python 2026-07-02-mdu-cleanup-report-fls.py --apply
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


APPLY = '--apply' in sys.argv

sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])

PS_NAME  = 'MDU_Cleanup_Report_Access'
PS_LABEL = 'MDU Cleanup Report Access'
PS_DESC  = ('Read on the read-only formula/rollup Opportunity fields used as filters on the '
            'MDU Cleanup Dashboard reports, so filters are not FLS-stripped for non-admins. '
            'Created 2026-07-02.')
# Assign to every active user on the affected profile (Rose + Tanya both hit this;
# the other 12 on the profile will too). Reversible: delete the perm set to undo all.
ASSIGN_ALL_ON_PROFILE = 'Standard User - Custom'
FIELDS = [
    'Opportunity.Agreements_Signed_Missing_IC__c',
    'Opportunity.Agreements_Sign_Missing_IC__c',
    'Opportunity.Agreement_Count__c',
    'Opportunity.Active_EMA_Bulk_Count__c',
]

mode = 'APPLY' if APPLY else 'DRY-RUN'
print(f"=== {mode} ===\n")

# 1. Perm set (find or create) -------------------------------------------------
rows = sf.query(f"SELECT Id, Name, Label FROM PermissionSet WHERE Name = '{PS_NAME}'")['records']
if rows:
    ps_id = rows[0]['Id']
    print(f"Perm set exists: {rows[0]['Label']} ({ps_id})")
else:
    print(f"Perm set '{PS_LABEL}' MISSING -> will create")
    ps_id = None
    if APPLY:
        res = sf.PermissionSet.create({'Name': PS_NAME, 'Label': PS_LABEL, 'Description': PS_DESC})
        ps_id = res['id']
        print(f"  created: {ps_id}")

# 2. Field permissions (find or create per field) ------------------------------
existing = set()
if ps_id:
    q = ("SELECT Field, PermissionsRead FROM FieldPermissions "
         f"WHERE ParentId = '{ps_id}'")
    existing = {r['Field'] for r in sf.query_all(q)['records'] if r['PermissionsRead']}

print("\nField grants:")
for fld in FIELDS:
    if fld in existing:
        print(f"  [skip] already granted: {fld}")
        continue
    print(f"  [add ] Read -> {fld}")
    if APPLY and ps_id:
        sf.FieldPermissions.create({
            'ParentId': ps_id,
            'SobjectType': fld.split('.')[0],
            'Field': fld,
            'PermissionsRead': True,
            'PermissionsEdit': False,   # formula/rollup fields are not editable
        })

# 3. Assign users --------------------------------------------------------------
members = sf.query_all(
    "SELECT Id, Name FROM User "
    f"WHERE IsActive = true AND Profile.Name = '{ASSIGN_ALL_ON_PROFILE}' ORDER BY Name")['records']
print(f"\nAssignments ({len(members)} active users on '{ASSIGN_ALL_ON_PROFILE}'):")
already = set()
if ps_id:
    already = {r['AssigneeId'] for r in sf.query_all(
        f"SELECT AssigneeId FROM PermissionSetAssignment WHERE PermissionSetId = '{ps_id}'")['records']}
for u in members:
    uid, uname = u['Id'], u['Name']
    if uid in already:
        print(f"  {uname}: already assigned")
        continue
    print(f"  {uname}: will assign")
    if APPLY and ps_id:
        sf.PermissionSetAssignment.create({'PermissionSetId': ps_id, 'AssigneeId': uid})
        print("    assigned")

# 4. Verify --------------------------------------------------------------------
if APPLY and ps_id:
    print("\n=== VERIFY ===")
    q = f"SELECT Field, PermissionsRead FROM FieldPermissions WHERE ParentId = '{ps_id}' ORDER BY Field"
    for r in sf.query_all(q)['records']:
        print(f"  grant: {r['Field']}  read={r['PermissionsRead']}")
    a = sf.query("SELECT Assignee.Name FROM PermissionSetAssignment "
                 f"WHERE PermissionSetId = '{ps_id}'")['records']
    print("  assignees:", ", ".join(x['Assignee']['Name'] for x in a) or "(none)")

print(f"\nDone ({mode}).")
