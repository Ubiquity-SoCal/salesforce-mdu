"""Add Next_Action__c to Opps discussed in the 6/03 Weekly MDU Meeting that were
BLANK. Only writes if the field is still empty (no overwrite). Audit-logged.

Source: tl;dv "Weekly MDU Meeting" 2026-06-03 (notes_6-03_weekly-mdu.json).
"""
import sys, io, os, csv
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

creds = {}
with open(r'C:\Users\cass\Work_Projects\SalesForce\api\Salesforce_Credentials.txt', encoding='utf-8') as f:
    for line in f:
        if ':' in line:
            k, v = line.split(':', 1)
            creds[k.strip().lower()] = v.strip()
sf = Salesforce(username=creds['username'], password=creds['password'],
                security_token=creds['security token'])

SOURCE = "6/03 Weekly MDU Meeting (tl;dv)"
# (exact Name, owner first name, note text) -- scoped to the two unclaimed, still-blank
# Aki properties; the rest were live-edited on the call or owners said they'd update them.
TARGETS = [
    ("Royal Gardens", "Bill",
     "Same landlord (Aki, TX) as Pioneer Crossing; has PAL in hand, very interested. Bill following up with Aki within 30 days. Aki has 19 properties, only 2 in footprint."),
    ("Pioneer Crossing Apartments", "Bill",
     "Same landlord (Aki, TX) as Royal Gardens; PAL in hand. Bill following up with Aki within 30 days."),
]

recs = sf.query_all("""
    SELECT Id, Name, Owner.Name, Next_Action__c
    FROM Opportunity WHERE IsClosed = false
""")['records']

def find(name, owner_first):
    hits = [r for r in recs
            if (r['Name'] or '') == name
            and (r.get('Owner') or {}).get('Name', '').startswith(owner_first)]
    return hits

audit_dir = r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs'
os.makedirs(audit_dir, exist_ok=True)
audit_path = os.path.join(audit_dir, '2026-06-03_meeting_next_actions.csv')
ts = datetime.now().isoformat(timespec='seconds')

rows, written, skipped = [], 0, 0
for name, owner_first, note in TARGETS:
    hits = find(name, owner_first)
    if len(hits) != 1:
        print(f"SKIP (matched {len(hits)}): {name} [{owner_first}]")
        skipped += 1
        continue
    r = hits[0]
    before = (r.get('Next_Action__c') or '').strip()
    if before:
        print(f"SKIP (already has note): {name} -> {before[:50]}")
        skipped += 1
        continue
    sf.Opportunity.update(r['Id'], {'Next_Action__c': note})
    written += 1
    print(f"WROTE: {name} ({owner_first})")
    rows.append({'SF_Id': r['Id'], 'Name': name, 'Field': 'Next_Action__c',
                 'Before': before, 'After': note, 'Source': SOURCE,
                 'Timestamp': ts, 'Action': 'update'})

if rows:
    new_file = not os.path.exists(audit_path)
    with open(audit_path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before',
                                          'After', 'Source', 'Timestamp', 'Action'])
        if new_file:
            w.writeheader()
        w.writerows(rows)

print(f"\nwritten={written}  skipped={skipped}  audit={audit_path if rows else '(none)'}")
