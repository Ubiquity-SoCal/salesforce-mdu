import sys
import argparse
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


parser = argparse.ArgumentParser()
parser.add_argument('--dry-run', action='store_true', help='Preview matches without updating Salesforce')
args = parser.parse_args()

# Force unbuffered output so SSE receives lines immediately
sys.stdout.reconfigure(line_buffering=True)

# Connect to main Salesforce org
print("[INFO] Connecting to Salesforce...")
sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

# Step 1: Get all SiteTracker projects that aren't linked to an Opportunity
print("[INFO] Pulling unlinked SiteTracker projects...")
unlinked = sf.query("""
    SELECT Id, Name, Monday_Name__c, SiteTracker_Record_Id__c
    FROM SiteTracker_Project__c
    WHERE Opportunity__c = null
""")
unlinked_records = unlinked['records']
print(f"[INFO] Found {len(unlinked_records)} unlinked SiteTracker projects")

if not unlinked_records:
    print("[SUCCESS] All SiteTracker projects are already linked. Nothing to do.")
    sys.exit(0)

# Step 2: Get all Opportunities with Agreement_Name__c or Name for matching
print("[INFO] Pulling Opportunities for matching...")
opps = sf.query("""
    SELECT Id, Name, Agreement_Name__c
    FROM Opportunity
""")
opp_records = opps['records']
while not opps['done']:
    opps = sf.query_more(opps['nextRecordsUrl'], True)
    opp_records.extend(opps['records'])
print(f"[INFO] Loaded {len(opp_records)} Opportunities")

# Build lookup maps — Agreement_Name__c first, then Opp Name as fallback
by_agreement_name = {}
by_opp_name = {}
for opp in opp_records:
    if opp.get('Agreement_Name__c'):
        by_agreement_name[opp['Agreement_Name__c'].strip()] = opp['Id']
    if opp.get('Name'):
        by_opp_name[opp['Name'].strip()] = opp['Id']

# Step 3: Match and link
linked_count = 0
no_match_count = 0
error_count = 0
no_match_names = []

for st in unlinked_records:
    monday_name = (st.get('Monday_Name__c') or '').strip()
    if not monday_name:
        no_match_count += 1
        no_match_names.append(f"  {st['Name']} (no Monday_Name__c)")
        continue

    # Try Agreement_Name__c first (exact), then case-insensitive, then Opp Name fallback
    opp_id = by_agreement_name.get(monday_name)
    if not opp_id:
        # Case-insensitive fallback on Agreement_Name__c
        for key, val in by_agreement_name.items():
            if key.lower() == monday_name.lower():
                opp_id = val
                break
    if not opp_id:
        opp_id = by_opp_name.get(monday_name)

    if not opp_id:
        no_match_count += 1
        no_match_names.append(f"  {st['Name']} — {monday_name}")
        continue

    if args.dry_run:
        match_type = 'Agreement_Name' if by_agreement_name.get(monday_name) else 'Opp Name'
        linked_count += 1
        print(f"[WOULD LINK] {st['Name']} -> {monday_name} (matched via {match_type})")
    else:
        try:
            # Link ST project -> Opportunity
            sf.SiteTracker_Project__c.update(st['Id'], {'Opportunity__c': opp_id})
            # Link Opportunity -> ST project (so In_SiteTracker__c formula evaluates true)
            st_record_id = st.get('SiteTracker_Record_Id__c') or st['Name']
            sf.Opportunity.update(opp_id, {'SiteTracker_Project_ID__c': st_record_id})
            linked_count += 1
            print(f"[LINKED] {st['Name']} -> {monday_name}")
        except Exception as e:
            error_count += 1
            print(f"[ERROR] {st['Name']} -- {e}")

# Summary
print()
print(f"[SUMMARY] Linked: {linked_count}, No match: {no_match_count}, Errors: {error_count}")
if no_match_names:
    print(f"[INFO] Unmatched SiteTracker projects ({len(no_match_names)}):")
    for name in no_match_names:
        print(name)
