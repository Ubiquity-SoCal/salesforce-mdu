"""
Create permission set 'MDU_Business_Cleanup_ModifyAll' with Modify All Records
on the cleanup-relevant objects, then assign to all active reps except Julian.

Purpose: enable team collaboration on data cleanup. Without this, reps can't
edit records owned by peers or by inactive placeholder users (Chuck, etc.).
"""
import argparse, csv, sys, requests
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.apply and not args.dry_run:
    print('Specify --dry-run or --apply'); sys.exit(1)

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

PERMSET_API_NAME = 'MDU_Business_Cleanup_ModifyAll'
PERMSET_LABEL = 'MDU/Business Cleanup: Modify All'
PERMSET_DESCRIPTION = (
    'Grants Modify All Records on Opportunity, Account, Contact, Agreement, '
    'Property_Location, Property_Unit. Enables team collaboration on data '
    'cleanup (editing peer-owned + inactive-user-owned records). Created 2026-04-30.'
)

OBJECTS = [
    'Opportunity', 'Account', 'Contact',
    'Agreement__c', 'Property_Location__c', 'Property_Unit__c',
]

# Active reps to assign (by Name -> User Id)
ASSIGN_USERS = [
    ('Bill Holick', '005WR00000DEU6oYAH'),
    ('Brett Spivey', '005WR00000Ewjj3YAB'),
    ('Justin Barry', '005WR0000030RCzYAM'),
    ('Melissa Baker', '005WR000003CD6DYAW'),
    ('Niraj Patel', '005WR000008V4VoYAK'),
    ('Rosemarie Shortino', '005WR0000030R9lYAE'),
    ('Tanya Friese', '005WR0000030R1hYAE'),
]

# Verify the permset doesn't already exist
exist = sf.query(f"SELECT Id, Name FROM PermissionSet WHERE Name='{PERMSET_API_NAME}'")
if exist['totalSize']:
    print(f"Permission set '{PERMSET_API_NAME}' already exists: {exist['records'][0]['Id']}")
    print('Stopping. If you want to recreate, delete it manually first.')
    sys.exit(1)

# Show plan
print(f"Permission Set to create: {PERMSET_API_NAME}")
print(f"  Label: {PERMSET_LABEL}")
print(f"  Object permissions (Modify All): {', '.join(OBJECTS)}")
print(f"\nUsers to assign ({len(ASSIGN_USERS)}):")
for name, uid in ASSIGN_USERS:
    print(f"  - {name}  ({uid})")

if args.dry_run:
    print('\nDry run. Re-run with --apply to execute.')
    sys.exit(0)

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'cleanup_modify_all_permset_{ts}.csv'

with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Object_Or_Action', 'Id', 'Name', 'Source', 'Timestamp', 'Action'])

    # 1. Create the permission set itself
    ps_resp = sf.PermissionSet.create({
        'Name': PERMSET_API_NAME,
        'Label': PERMSET_LABEL,
        'Description': PERMSET_DESCRIPTION,
    })
    permset_id = ps_resp['id']
    print(f"\nCreated PermissionSet {permset_id}")
    w.writerow(['PermissionSet', permset_id, PERMSET_API_NAME, 'create_cleanup_modify_all_permset.py', ts, 'CREATED'])

    # 2. Add ObjectPermissions for each object (Modify All implies View All, Edit, Read, etc.)
    for obj in OBJECTS:
        op_resp = sf.ObjectPermissions.create({
            'ParentId': permset_id,
            'SobjectType': obj,
            'PermissionsRead': True,
            'PermissionsCreate': True,
            'PermissionsEdit': True,
            'PermissionsDelete': True,
            'PermissionsViewAllRecords': True,
            'PermissionsModifyAllRecords': True,
        })
        print(f"  + ObjectPermission on {obj}: {op_resp['id']}")
        w.writerow(['ObjectPermission', op_resp['id'], obj, 'create_cleanup_modify_all_permset.py', ts, 'GRANTED_MODIFY_ALL'])

    # 3. Assign permset to each user
    for name, uid in ASSIGN_USERS:
        try:
            psa = sf.PermissionSetAssignment.create({
                'PermissionSetId': permset_id,
                'AssigneeId': uid,
            })
            print(f"  + Assigned to {name}: {psa['id']}")
            w.writerow(['PermissionSetAssignment', psa['id'], name, 'create_cleanup_modify_all_permset.py', ts, 'ASSIGNED'])
        except Exception as e:
            print(f"  FAIL assign to {name}: {e}")

print(f"\nDone. Audit log: {audit_path}")
print("Tell users to log out and back in to pick up the new permissions.")
