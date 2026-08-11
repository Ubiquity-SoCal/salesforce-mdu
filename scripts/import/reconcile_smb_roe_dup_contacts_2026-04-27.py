"""
Reconcile the 14 Contact dup failures + 1 invalid-email failure from
parse_smb_roe_owners_2026-04-27.py.

Strategy
========
1. Read the planned Contacts + junctions from the JSON plan dumped by the
   parser via `--dump-plan`.
2. Pull all Contacts from SF + existing junctions on the 245 Business_ROE Opps.
3. For each planned junction whose Contact didn't get inserted (because SF dup
   rules rejected it), find the existing matching Contact in SF by Email or
   LastName+Phone, then create the junction pointing at that existing Contact.

Usage:
  # First, dump the plan from the parser:
  python parse_smb_roe_owners_2026-04-27.py --dump-plan audit_logs/_smb_roe_plan.json

  # Then run this:
  python reconcile_smb_roe_dup_contacts_2026-04-27.py            # preview
  python reconcile_smb_roe_dup_contacts_2026-04-27.py --apply    # writes junctions
"""
import sys, io, re, csv, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
ap.add_argument('--plan', default=r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\_smb_roe_plan.json')
args = ap.parse_args()
APPLY = args.apply

SCRIPT_NAME = 'reconcile_smb_roe_dup_contacts_2026-04-27.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# Load planned state from JSON
plan_path = Path(args.plan)
plan = json.loads(plan_path.read_text(encoding='utf-8'))
new_contacts = plan['new_contacts']
junctions = plan['junctions']

print(f"\n[Recon] Replanned: {len(new_contacts)} contacts, {len(junctions)} junctions")

# Pull all Contacts from SF to match by email or lastname+phone
print("[SF] Pulling all Contacts (for dup matching)")
all_ct = sf.query_all("SELECT Id, FirstName, LastName, Phone, Email, AccountId FROM Contact")['records']
print(f"  Pulled {len(all_ct)} Contacts")

ct_by_email = {}
ct_by_lname_phone = {}
for c in all_ct:
    if c.get('Email'):
        ct_by_email[c['Email'].lower()] = c
    if c.get('LastName') and c.get('Phone'):
        # Normalize phone for matching
        digits = re.sub(r'\D', '', c['Phone'])
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        if len(digits) == 10:
            ct_by_lname_phone[(c['LastName'].lower(), digits)] = c

# Pull existing junctions on the 245 Opps
print("[SF] Pulling existing Opportunity_Contact__c junctions on Business_ROE Opps")
existing_juncs = sf.query_all("""
  SELECT Opportunity__c, Contact__c, Role__c
  FROM Opportunity_Contact__c
  WHERE Opportunity__r.RecordType.DeveloperName='Business_ROE'
""")['records']
existing_keys = {(j['Opportunity__c'], j['Contact__c']) for j in existing_juncs}
print(f"  Existing junctions: {len(existing_juncs)}")

# Resolve each planned junction Contact to an Id in SF (either matched-existing or skipped)
# new_contacts dict: key -> {FirstName, LastName, Phone, Email, _acct_ref, _role}
ct_key_to_existing_id = {}
unresolved_keys = []
for k, c in new_contacts.items():
    em = (c.get('Email') or '').lower().strip().rstrip(',.;-')
    found = None
    if em and em in ct_by_email:
        found = ct_by_email[em]
    elif c.get('LastName') and c.get('Phone'):
        digits = re.sub(r'\D', '', c['Phone'])
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        match_key = (c['LastName'].lower(), digits)
        if match_key in ct_by_lname_phone:
            found = ct_by_lname_phone[match_key]
    if found:
        ct_key_to_existing_id[k] = found['Id']
    else:
        unresolved_keys.append(k)

print(f"\n  Contact keys resolved to SF Id:        {len(ct_key_to_existing_id)}")
print(f"  Contact keys with NO SF match:          {len(unresolved_keys)}")

# Build missing-junction list
missing_juncs = []
for j in junctions:
    cid = ct_key_to_existing_id.get(j['_contact_key'])
    if not cid:
        continue
    if (j['Opportunity__c'], cid) in existing_keys:
        continue  # already there
    missing_juncs.append({
        'Opportunity__c': j['Opportunity__c'],
        'Contact__c': cid,
        'Role__c': j['Role__c'],
    })

print(f"\n  Junctions to create (missing):         {len(missing_juncs)}")

if not missing_juncs:
    print("\n  Nothing to do; all junctions already in SF.")
    sys.exit(0)

# Show samples
print("\n  Sample missing junctions (first 10):")
for j in missing_juncs[:10]:
    # Get a label
    print(f"    Opp={j['Opportunity__c']}  Contact={j['Contact__c']}  Role={j['Role__c']}")

if not APPLY:
    print(f"\n[Preview only — re-run with --apply to insert {len(missing_juncs)} junctions]")
    sys.exit(0)

# Apply
print("\n[Apply] Inserting missing junctions")
audit_rows = []
for i in range(0, len(missing_juncs), 200):
    batch = missing_juncs[i:i+200]
    print(f"  Batch {i//200 + 1}: {len(batch)} ...")
    results = sf.bulk.Opportunity_Contact__c.insert(batch)
    for j, res in enumerate(results):
        rec = batch[j]
        if res.get('success'):
            audit_rows.append({
                'SF_Id': res['id'], 'Name': '(junction)', 'Field': '(created)',
                'Before': '', 'After': f"Opp={rec['Opportunity__c']} Contact={rec['Contact__c']} Role={rec['Role__c']}",
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'CREATE',
                'Note': 'reconcile dup-rejected Contacts -> existing Contacts',
            })
        else:
            print(f"    ⚠ FAILED: {rec} -- {res.get('errors', res)}")

audit_path = AUDIT_DIR / f'smb_roe_dup_recon_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\n✓ Done. Audit log: {audit_path} ({len(audit_rows)} rows)")
