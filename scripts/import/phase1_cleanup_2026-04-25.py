"""
Phase 1 cleanup before Business_ROE RT deploy (2026-04-25)

Three operations, all on Opportunity records:

  Section 1: Migrate 4 MDU Opps from orphan stage 'Under Construction' to 'Under Contract'
  Section 2: Rename 67 'SMB ROE Project-' prefixed Opps to plain address naming
  Section 3: Backfill Property_Location__c on all 67 (from Property_Unit parent where linked,
             address-matched for the 6 Juanita Opps without Property_Unit)
             AND link the 6 Juanita Opps to specific Property_Unit by parsing unit number

Usage:
  python phase1_cleanup_2026-04-25.py --preview     (default — no writes)
  python phase1_cleanup_2026-04-25.py --apply       (executes writes + writes audit CSV)
"""
import sys, io, re, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true', help='Execute the changes (default is preview)')
args = ap.parse_args()
APPLY = args.apply

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().isoformat(timespec='seconds')
SCRIPT_NAME = 'phase1_cleanup_2026-04-25.py'
AUDIT_ROWS = []  # (sf_id, name, field, before, after, source, timestamp, action, note)


def log(sf_id, name, field, before, after, action, note=''):
    AUDIT_ROWS.append({
        'SF_Id': sf_id, 'Name': name, 'Field': field,
        'Before': before, 'After': after,
        'Source': SCRIPT_NAME, 'Timestamp': TS,
        'Action': action, 'Note': note,
    })


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: 4 MDU Under Construction → Under Contract
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("SECTION 1: Migrate 4 MDU Opps from 'Under Construction' to 'Under Contract'")
print("═" * 70)

s1_opps = sf.query_all(
    "SELECT Id, Name, StageName, Owner.Name "
    "FROM Opportunity "
    "WHERE StageName='Under Construction' AND RecordType.DeveloperName='MDU'"
)['records']

for o in s1_opps:
    print(f"  {o['Id']}  {o['Name']:50s}  owner={o['Owner']['Name']}  {o['StageName']} → Under Contract")

print(f"\n  Total: {len(s1_opps)} records to migrate")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: Rename 67 SMB ROE Project- Opps
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("SECTION 2: Rename 67 'SMB ROE Project-' prefixed Opps")
print("═" * 70)

s2_opps = sf.query_all(
    "SELECT Id, Name, Property_Unit__c, Property_Unit__r.Name, Property_Unit__r.Unit__c, "
    "Property_Unit__r.Property_Location__c, Property_Unit__r.Property_Location__r.Name, "
    "Property_Location__c "
    "FROM Opportunity WHERE Name LIKE 'SMB ROE Project%' ORDER BY Name"
)['records']

# Build rename plan: strip prefix
PREFIX = re.compile(r'^SMB ROE Project[-\s]+', re.IGNORECASE)
rename_plan = []
for o in s2_opps:
    new_name = PREFIX.sub('', o['Name']).strip()
    if new_name != o['Name']:
        rename_plan.append((o['Id'], o['Name'], new_name))

print(f"  Records to rename: {len(rename_plan)} (sample first 10):")
for sf_id, old, new in rename_plan[:10]:
    print(f"    {sf_id}  '{old[:50]}' → '{new[:50]}'")
if len(rename_plan) > 10:
    print(f"    ... and {len(rename_plan)-10} more")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3a: Backfill Property_Location on 67 Opps (from PU parent where linked)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("SECTION 3a: Backfill Property_Location__c on 67 Opps")
print("═" * 70)

pl_backfill = []  # list of (id, current_pl, new_pl_from_pu, opp_name)
juanita_no_pu = []  # opps without PU that need Juanita-style address+unit lookup

for o in s2_opps:
    current_pl = o.get('Property_Location__c')
    pu = o.get('Property_Unit__r')
    if pu and pu.get('Property_Location__c'):
        new_pl = pu['Property_Location__c']
        if current_pl != new_pl:
            pl_backfill.append((o['Id'], o['Name'], current_pl, new_pl, pu.get('Property_Location__r', {}).get('Name','')))
    elif not o.get('Property_Unit__c'):
        # No PU — needs Juanita-style address+unit lookup
        juanita_no_pu.append(o)

print(f"  Backfill from PU parent: {len(pl_backfill)} (sample first 5):")
for sf_id, name, before, after, plname in pl_backfill[:5]:
    print(f"    {sf_id}  {name[:35]:35s}  PL: {before or '(none)'} → {after} ({plname})")

print(f"\n  Without Property_Unit (need address+unit lookup): {len(juanita_no_pu)}")
for o in juanita_no_pu:
    print(f"    {o['Id']}  {o['Name']}")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3b: For records without PU, parse address+unit from Name
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("SECTION 3b: Lookup Property_Unit + Property_Location for 6 unlinked Opps")
print("═" * 70)

# Pattern: "SMB ROE Project- 127 W JUANITA AVE MESA AZ 101" → addr="127 W JUANITA AVE MESA AZ", unit="101"
# Edge case: "SMB ROE Project- 750 S MAIN ST KELLER TX" — no unit suffix, trailing TX is state code
US_STATES = {'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY',
             'LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND',
             'OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'}
pu_link_plan = []  # (opp_id, opp_name, pl_id, pl_name, pu_id, pu_name, unit_num)

for o in juanita_no_pu:
    stripped = PREFIX.sub('', o['Name']).strip()
    parts = stripped.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].upper() in US_STATES:
        # No unit suffix — full string is the address
        addr, unit_num = stripped, None
    elif len(parts) == 2 and parts[1]:
        addr, unit_num = parts[0].strip(), parts[1].strip()
    else:
        print(f"  ⚠ Cannot parse: {o['Name']}")
        continue

    # Find Property_Location matching this address (case-insensitive contains)
    pl_query = (
        f"SELECT Id, Name, Business_Base_Address__c, City__c, State__c "
        f"FROM Property_Location__c "
        f"WHERE Name = '{addr.replace(chr(39), chr(92)+chr(39))}' OR Business_Base_Address__c = '{addr.replace(chr(39), chr(92)+chr(39))}' "
        f"LIMIT 5"
    )
    pl_results = sf.query(pl_query)['records']

    if not pl_results:
        print(f"  ⚠ No Property_Location for '{addr}' (Opp: {o['Id']} '{o['Name']}')")
        continue
    if len(pl_results) > 1:
        print(f"  ⚠ Multiple Property_Locations for '{addr}': {[p['Id'] for p in pl_results]} — skipping {o['Id']}")
        continue

    pl = pl_results[0]
    pl_id = pl['Id']

    pu_id, pu_name, auto_linked = None, None, False
    if unit_num:
        # Find Property_Unit under this PL matching unit_num. Try "UNIT 101" and "101" formats
        pu_query = (
            f"SELECT Id, Name, Unit__c "
            f"FROM Property_Unit__c "
            f"WHERE Property_Location__c = '{pl_id}' "
            f"AND (Unit__c = 'UNIT {unit_num}' OR Unit__c = '{unit_num}' OR Name LIKE '%UNIT {unit_num}%' OR Name LIKE '% {unit_num} %' OR Name LIKE '% {unit_num}')"
        )
        pu_results = sf.query(pu_query)['records']
        if pu_results:
            exact = [p for p in pu_results if p.get('Unit__c') in (f'UNIT {unit_num}', unit_num)]
            match = exact[0] if exact else pu_results[0]
            pu_id = match['Id']
            pu_name = match.get('Name', '')

    if not pu_id:
        # No unit-specific match — fallback to first available unit under this PL.
        # Prefer literal Unit "1" / "UNIT 1" if it exists, else sort by Unit__c and take first.
        pu_results = sf.query(
            f"SELECT Id, Name, Unit__c FROM Property_Unit__c "
            f"WHERE Property_Location__c = '{pl_id}' ORDER BY Unit__c LIMIT 50"
        )['records']
        if pu_results:
            unit_one = [p for p in pu_results if p.get('Unit__c') in ('UNIT 1', '1', 'Unit 1')]
            match = unit_one[0] if unit_one else pu_results[0]
            pu_id = match['Id']
            pu_name = match.get('Name', '')
            auto_linked = True

    pu_link_plan.append((o['Id'], o['Name'], pl_id, pl['Name'], pu_id, pu_name, unit_num or '(no unit)', auto_linked))

print(f"\n  Lookup results:")
for opp_id, opp_name, pl_id, pl_name, pu_id, pu_name, unit_num, auto_linked in pu_link_plan:
    if pu_id and auto_linked:
        pu_status = f"PU={pu_id} ({pu_name})  [AUTO-LINKED — will stamp verify note]"
    elif pu_id:
        pu_status = f"PU={pu_id} ({pu_name})"
    else:
        pu_status = f"⚠ NO PU MATCH for unit '{unit_num}'"
    print(f"    {opp_id}  '{opp_name[:45]}'")
    print(f"      → PL={pl_id} ({pl_name})")
    print(f"      → {pu_status}")

# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("SUMMARY")
print("═" * 70)
print(f"  Section 1 — Stage migration:           {len(s1_opps)} records")
print(f"  Section 2 — Rename:                    {len(rename_plan)} records")
print(f"  Section 3a — PL backfill from PU:      {len(pl_backfill)} records")
print(f"  Section 3b — PL+PU lookup (Juanita):   {len(pu_link_plan)} records (some may lack PU match)")

if not APPLY:
    print("\n  Mode: PREVIEW — no writes. Re-run with --apply to execute.")
    sys.exit(0)

# ═══════════════════════════════════════════════════════════════════════
# APPLY MODE — execute changes
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("APPLYING CHANGES")
print("═" * 70)

# Section 1: Stage migration
print(f"\n[1] Migrating {len(s1_opps)} stage values...")
s1_updates = []
for o in s1_opps:
    s1_updates.append({'Id': o['Id'], 'StageName': 'Under Contract'})
    log(o['Id'], o['Name'], 'StageName', 'Under Construction', 'Under Contract', 'UPDATE',
        'Orphan stage cleanup pre-Phase 2 deploy')
if s1_updates:
    results = sf.bulk.Opportunity.update(s1_updates)
    errors = [(s1_updates[i]['Id'], r) for i, r in enumerate(results) if not r.get('success')]
    if errors:
        print(f"  ⚠ {len(errors)} errors:")
        for eid, err in errors[:5]:
            print(f"    {eid}: {err}")
    else:
        print(f"  ✓ {len(s1_updates)} stage migrations done")

# Section 2 + 3a + 3b combined: build per-Opp updates with Name + Property_Location + (Property_Unit if applicable)
print(f"\n[2] Renaming + backfilling {len(s2_opps)} Opps...")
combined_updates = {}  # Opp_Id → dict of fields to update

# Apply rename
for sf_id, old, new in rename_plan:
    combined_updates.setdefault(sf_id, {'Id': sf_id})['Name'] = new
    log(sf_id, old, 'Name', old, new, 'UPDATE', 'Drop SMB ROE Project- prefix')

# Apply PL backfill from PU parent
for sf_id, opp_name, before, after, plname in pl_backfill:
    combined_updates.setdefault(sf_id, {'Id': sf_id})['Property_Location__c'] = after
    log(sf_id, opp_name, 'Property_Location__c', before or '', after, 'UPDATE',
        f'Backfilled from Property_Unit parent ({plname})')

# Apply Juanita PL + PU lookup
auto_linked_opps = []  # opps needing the verify note stamped after the bulk update
for opp_id, opp_name, pl_id, pl_name, pu_id, pu_name, unit_num, auto_linked in pu_link_plan:
    combined_updates.setdefault(opp_id, {'Id': opp_id})['Property_Location__c'] = pl_id
    log(opp_id, opp_name, 'Property_Location__c', '', pl_id, 'UPDATE',
        f'Address-matched PL: {pl_name}')
    if pu_id:
        combined_updates[opp_id]['Property_Unit__c'] = pu_id
        note_suffix = ' (AUTO-LINKED — needs verification)' if auto_linked else ''
        log(opp_id, opp_name, 'Property_Unit__c', '', pu_id, 'UPDATE',
            f'{"Auto-linked first available PU" if auto_linked else "Address+unit matched PU"}: {pu_name}{note_suffix}')
        if auto_linked:
            auto_linked_opps.append((opp_id, opp_name, pu_name))

update_list = list(combined_updates.values())
if update_list:
    # Bulk in chunks of 200
    total_errors = 0
    for i in range(0, len(update_list), 200):
        chunk = update_list[i:i+200]
        results = sf.bulk.Opportunity.update(chunk)
        errors = [(chunk[j]['Id'], r) for j, r in enumerate(results) if not r.get('success')]
        total_errors += len(errors)
        if errors:
            for eid, err in errors[:5]:
                print(f"    ⚠ {eid}: {err}")
    print(f"  ✓ {len(update_list)-total_errors}/{len(update_list)} updates applied")

# Stamp verify-note ContentNotes on auto-linked Opps
if auto_linked_opps:
    print(f"\n[3] Stamping {len(auto_linked_opps)} verify-note ContentNotes on auto-linked Opps...")
    import base64 as _b64
    for opp_id, opp_name, pu_name in auto_linked_opps:
        body_html = (
            f'<p><b>AUTO-LINKED Property Unit</b></p>'
            f'<p>This Opportunity name had no unit number, so it was auto-linked to the first available '
            f'Property_Unit under the matched Property_Location during the 2026-04-25 cleanup.</p>'
            f'<p>Auto-linked unit: <b>{pu_name}</b></p>'
            f'<p>Please verify this is the correct unit and update Property_Unit if not.</p>'
        )
        try:
            note = sf.ContentNote.create({
                'Title': 'AUTO-LINKED Property Unit — Please Verify',
                'Content': _b64.b64encode(body_html.encode('utf-8')).decode('utf-8'),
            })
            note_id = note['id']
            cdid_q = sf.query(f"SELECT LatestPublishedVersion.ContentDocumentId FROM ContentNote WHERE Id='{note_id}'")
            cdid = cdid_q['records'][0]['LatestPublishedVersion']['ContentDocumentId']
            sf.ContentDocumentLink.create({
                'ContentDocumentId': cdid,
                'LinkedEntityId': opp_id,
                'ShareType': 'V',
                'Visibility': 'AllUsers',
            })
            log(opp_id, opp_name, '(ContentNote)', '', note_id, 'CREATE',
                f'Stamped verify note for auto-linked unit: {pu_name}')
            print(f"  ✓ Note stamped on {opp_id} ({opp_name[:40]})")
        except Exception as e:
            print(f"  ⚠ Failed to stamp note on {opp_id}: {e}")

# Write audit log
audit_path = AUDIT_DIR / f'phase1_cleanup_audit_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    writer.writeheader()
    writer.writerows(AUDIT_ROWS)
print(f"\n  ✓ Audit log: {audit_path}  ({len(AUDIT_ROWS)} rows)")
print("\nDone.")
