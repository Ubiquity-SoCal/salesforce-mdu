"""
Rename Julian's 67 Business RT Opps to include unit numbers from their linked Property_Unit.

Pattern: {Property_Location.Name} - {Property_Unit.Unit__c}
Examples:
  '6910 PACIFIC ST OMAHA NE' (×14 dupes) → '6910 PACIFIC ST OMAHA NE - UNIT 200', '...UNIT 201', etc.
  '127 W JUANITA AVE MESA AZ 101' → '127 W JUANITA AVE MESA AZ - UNIT 101' (rebuilt for consistency)

Skips Opps that lack Property_Unit (no way to differentiate).

Usage:
  python rename_julian_opps_with_unit_2026-04-25.py --preview
  python rename_julian_opps_with_unit_2026-04-25.py --apply
"""
import sys, io, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()
APPLY = args.apply

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().isoformat(timespec='seconds')

# Find Julian's Business RT Opps linked to Property_Unit (the 67 from Phase 1 + Watauga = ~68)
# Filter to Julian + Business RT + has PU
opps = sf.query_all(
    "SELECT Id, Name, Property_Unit__c, Property_Unit__r.Name, Property_Unit__r.Unit__c, "
    "Property_Unit__r.Property_Location__r.Name, Owner.Name "
    "FROM Opportunity "
    "WHERE RecordType.DeveloperName='Business' "
    "AND Property_Unit__c != null "
    "AND Owner.Name IN ('Julian Harrell','Jamie Doyle')"
)['records']

print(f"Found {len(opps)} Business RT Opps linked to a Property_Unit")

# Identify which current Names are duplicated — those are the ones that need disambiguation.
# Names that are unique already (even if just an address or a tenant name) get left alone.
from collections import Counter
name_counts = Counter(o['Name'] for o in opps)
duplicate_names = {n for n, c in name_counts.items() if c > 1}
print(f"  Names that appear >1 time (need disambiguation): {len(duplicate_names)}")
for n in sorted(duplicate_names)[:10]:
    print(f"    {name_counts[n]}x  {n}")

planned = []
skipped = []
for o in opps:
    if o['Name'] not in duplicate_names:
        skipped.append((o, 'name is already unique — leaving meaningful name intact'))
        continue

    pu = o.get('Property_Unit__r') or {}
    pl = (pu.get('Property_Location__r') or {})
    pl_name = pl.get('Name')
    unit_id = pu.get('Unit__c')

    if not pl_name:
        skipped.append((o, 'no PL.Name'))
        continue
    # Build new name. Three cases:
    #   1. PU has explicit Unit__c → "{PL.Name} - {Unit__c}"
    #   2. PU.Name has "UNIT X" pattern → "{PL.Name} - UNIT X"
    #   3. Single-unit building (no unit identifier) → just "{PL.Name}" — PL.Name has the
    #      house number which differentiates from sibling addresses
    if unit_id:
        new_name = f"{pl_name} - {unit_id}"
    else:
        pu_name = pu.get('Name') or ''
        import re
        m = re.search(r'\bUNIT\s+(\S+)', pu_name, re.I)
        if m:
            new_name = f"{pl_name} - UNIT {m.group(1)}"
        else:
            # Single-unit building — use PL.Name (has the house number)
            new_name = pl_name

    if new_name == o['Name']:
        skipped.append((o, 'name already matches target'))
        continue

    planned.append((o['Id'], o['Name'], new_name))

print(f"\nPlanned renames: {len(planned)}")
print(f"Skipped: {len(skipped)}")

# Show samples
print("\nSample (first 15):")
for sf_id, old, new in planned[:15]:
    print(f"  {sf_id}  '{old[:45]}' → '{new[:55]}'")
if len(planned) > 15:
    print(f"  ...and {len(planned)-15} more")

# Check for new-name duplicates within the planned list
from collections import Counter

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

new_counts = Counter(p[2] for p in planned)
dups = [(n, c) for n, c in new_counts.items() if c > 1]
if dups:
    print(f"\n  ⚠ {len(dups)} new names would still be duplicate (multiple PUs share same Unit__c?):")
    for n, c in dups[:5]:
        print(f"    {c}x  {n}")

if not APPLY:
    print("\n[Preview only — re-run with --apply to update]")
    sys.exit(0)

# Apply
print(f"\nApplying {len(planned)} renames...")
audit_rows = []
updates = [{'Id': p[0], 'Name': p[2]} for p in planned]
results = sf.bulk.Opportunity.update(updates)
errors = []
for i, res in enumerate(results):
    p = planned[i]
    if res.get('success'):
        audit_rows.append({
            'SF_Id': p[0], 'Name': p[2], 'Field': 'Name',
            'Before': p[1], 'After': p[2],
            'Source': 'rename_julian_opps_with_unit_2026-04-25.py',
            'Timestamp': TS, 'Action': 'UPDATE',
            'Note': 'Append unit identifier to disambiguate duplicate names',
        })
    else:
        errors.append((p[0], p[1], res))

print(f"  ✓ Renamed: {len(audit_rows)}")
print(f"  ⚠ Errors:  {len(errors)}")
for eid, ename, err in errors[:5]:
    print(f"    {eid} ({ename[:30]}): {err}")

audit_path = AUDIT_DIR / f'julian_rename_unit_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"  ✓ Audit log: {audit_path}")
