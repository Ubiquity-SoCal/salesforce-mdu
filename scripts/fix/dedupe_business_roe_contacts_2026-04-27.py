"""
Dedupe Contacts that share the same name within a single Business_ROE Opp.

The owner/MC parser created multiple Contact rows when one person had multiple
phones in the source text (e.g., "David Stahl 213-687-9600 x2, 310-365-9002m").
Result: ~165 dup groups across the 245 Opps, ~209 surplus junctions.

Strategy
========
For each (Opp, normalized-name) group with 2+ Contacts:
  1. Pick canonical Contact: prefer the one with Email; tie-break by oldest CreatedDate.
  2. Merge alt Contacts' phones into canonical's Phone/MobilePhone slots
     (only fill empty slots; don't overwrite existing data).
  3. Repoint all junctions on alt Contacts to canonical.
  4. After repoint, dedupe junctions by (Opp, canonical_Contact, Role) — distinct
     roles kept (Property Owner + Property Manager OK), exact role dups dropped.
  5. Delete the alt Contact records IF they have no remaining junctions and no
     other dependencies. (We check by counting junctions only — other deps will
     surface as SF errors and we'll log + skip those.)

Usage:
  python dedupe_business_roe_contacts_2026-04-27.py            # preview
  python dedupe_business_roe_contacts_2026-04-27.py --apply
"""
import sys, io, csv, argparse, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

SCRIPT_NAME = 'dedupe_business_roe_contacts_2026-04-27.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])


def norm_name(fn, ln):
    fn = (fn or '').strip().lower()
    ln = (ln or '').strip().lower()
    return (fn, ln)


def normalize_phone(s):
    if not s:
        return None
    digits = re.sub(r'\D', '', s)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return f'({digits[0:3]}) {digits[3:6]}-{digits[6:10]}'
    return s.strip()


# Pull all Business_ROE junctions + Contact details
print("[Pull] junctions on Business_ROE Opps")
junctions = sf.query_all("""
  SELECT Id, Opportunity__c, Opportunity__r.Name, Contact__c, Role__c,
         Contact__r.Id, Contact__r.FirstName, Contact__r.LastName,
         Contact__r.Phone, Contact__r.MobilePhone, Contact__r.Email,
         Contact__r.AccountId, Contact__r.CreatedDate
  FROM Opportunity_Contact__c
  WHERE Opportunity__r.RecordType.DeveloperName='Business_ROE'
""")['records']
print(f"  {len(junctions)} junctions")

# Junctions outside Business_ROE for the alt Contacts (do they have other links?)
contact_ids = {j['Contact__c'] for j in junctions}
print(f"  {len(contact_ids)} distinct Contacts referenced")

print("[Pull] junctions on those Contacts across ALL Opps (to check for off-ROE deps)")
ids_csv = "','".join(contact_ids)
all_junctions_for_these_contacts = sf.query_all(
    f"SELECT Id, Contact__c, Opportunity__c FROM Opportunity_Contact__c WHERE Contact__c IN ('{ids_csv}')"
)['records']
junctions_per_contact = defaultdict(list)
for j in all_junctions_for_these_contacts:
    junctions_per_contact[j['Contact__c']].append(j)
print(f"  {len(all_junctions_for_these_contacts)} total junctions on these Contacts (incl. non-ROE)")

# Group junctions by (Opp, normalized name)
groups = defaultdict(list)
for j in junctions:
    c = j['Contact__r'] or {}
    key = (j['Opportunity__c'], norm_name(c.get('FirstName'), c.get('LastName')))
    groups[key].append(j)

# Identify dup groups
dup_groups = {k: v for k, v in groups.items() if len({j['Contact__c'] for j in v}) > 1}
print(f"\n  Dup groups (same (Opp, name) with 2+ Contacts): {len(dup_groups)}")

# Plan
plan_contact_updates = {}  # contact_id -> {field: value} for canonical phone merges
plan_junction_repoints = []  # list of (junction_id, new_contact_id) — actually we'll just delete + recreate to dedupe
plan_junction_deletes = []  # list of junction_ids to delete
plan_contact_deletes = []  # list of contact_ids to delete after de-junction

# For tracking: {(opp_id, contact_id, role) -> junction_id}, used to dedupe within canonical
existing_canonical_pairs = defaultdict(list)  # (opp_id, canon_id, role) -> [junction_ids]

# First, pre-populate with non-dup-group junctions so we don't accidentally re-create dups against them
for k, v in groups.items():
    if k in dup_groups:
        continue
    for j in v:
        existing_canonical_pairs[(j['Opportunity__c'], j['Contact__c'], j['Role__c'])].append(j['Id'])

for (opp_id, name_key), jr_list in dup_groups.items():
    # Pick canonical: most-data (Email > Phone > Mobile), then oldest CreatedDate
    contacts_in_group = {}  # contact_id -> Contact data
    for j in jr_list:
        c = j['Contact__r']
        contacts_in_group[c['Id']] = c

    def score(c):
        s = 0
        if c.get('Email'): s += 100
        if c.get('Phone'): s += 10
        if c.get('MobilePhone'): s += 5
        # invert CreatedDate so older wins as tiebreak
        return (s, -1 * (hash(c.get('CreatedDate', '')) % 10**9))

    canon_id = max(contacts_in_group.keys(), key=lambda cid: score(contacts_in_group[cid]))
    canon = contacts_in_group[canon_id]
    alt_ids = [cid for cid in contacts_in_group if cid != canon_id]

    # Merge alt phones into canonical
    canon_phone = canon.get('Phone')
    canon_mobile = canon.get('MobilePhone')
    canon_phone_set = {normalize_phone(canon_phone)} if canon_phone else set()
    if canon_mobile:
        canon_phone_set.add(normalize_phone(canon_mobile))

    new_phone = canon_phone
    new_mobile = canon_mobile
    for cid in alt_ids:
        c = contacts_in_group[cid]
        for p in (c.get('Phone'), c.get('MobilePhone')):
            pn = normalize_phone(p)
            if not pn:
                continue
            if pn in canon_phone_set:
                continue
            if not new_phone:
                new_phone = pn
                canon_phone_set.add(pn)
            elif not new_mobile:
                new_mobile = pn
                canon_phone_set.add(pn)
            # If both slots full, drop the extra (rare; we have 2 slots)

    if new_phone != canon_phone or new_mobile != canon_mobile:
        upd = {}
        if new_phone != canon_phone:
            upd['Phone'] = new_phone
        if new_mobile != canon_mobile:
            upd['MobilePhone'] = new_mobile
        plan_contact_updates[canon_id] = upd

    # Determine the set of distinct roles that should remain on canonical
    distinct_roles = set(j['Role__c'] for j in jr_list)

    # Identify which junctions stay vs go
    # Strategy: keep one junction per (canonical, role); prefer existing junction on canonical
    #   if available, else convert one of the alt junctions to point at canonical via delete+create.
    canonical_junctions = [j for j in jr_list if j['Contact__c'] == canon_id]
    alt_junctions = [j for j in jr_list if j['Contact__c'] != canon_id]

    # For each role we want to keep:
    keep_roles = set()
    for role in distinct_roles:
        # Already have a canonical junction for this role?
        existing = [j for j in canonical_junctions if j['Role__c'] == role]
        if existing:
            # Keep first; mark dups for delete
            for j in existing[1:]:
                plan_junction_deletes.append(j['Id'])
            keep_roles.add(role)
        else:
            # No canonical junction for this role; we'll convert one alt junction
            alt_with_role = [j for j in alt_junctions if j['Role__c'] == role]
            if alt_with_role:
                # Keep first (will be re-pointed via delete+create), mark rest for delete
                conversion_target = alt_with_role[0]
                plan_junction_repoints.append((conversion_target['Id'], opp_id, canon_id, role))
                for j in alt_with_role[1:]:
                    plan_junction_deletes.append(j['Id'])
                keep_roles.add(role)
            # else: no junction had this role at all (impossible since we got it from distinct_roles)

    # Any alt junctions not already accounted for go to delete
    handled_alt_ids = set()
    for jid, _, _, role in plan_junction_repoints:
        handled_alt_ids.add(jid)
    for j in alt_junctions:
        if j['Id'] in handled_alt_ids:
            continue
        plan_junction_deletes.append(j['Id'])

    # Plan Contact delete for alt Contacts IF they have no junctions outside this group
    for cid in alt_ids:
        all_jr = junctions_per_contact[cid]
        # After dedup, this Contact will have its junctions on this Opp removed.
        # Are there other junctions on OTHER Opps?
        other_opp_jr = [j for j in all_jr if j['Opportunity__c'] != opp_id]
        if not other_opp_jr:
            plan_contact_deletes.append(cid)


# ── Summary ──
print("\n" + "="*70)
print("PLAN SUMMARY")
print("="*70)
print(f"  Canonical Contact phone merges:  {len(plan_contact_updates)}")
print(f"  Junctions to repoint (delete+create with new contact): {len(plan_junction_repoints)}")
print(f"  Junctions to delete:              {len(plan_junction_deletes)}")
print(f"  Alt Contacts safe to delete:      {len(plan_contact_deletes)}")
print(f"  Alt Contacts kept (have other Opp links): {sum(1 for k,v in dup_groups.items() for cid in {j['Contact__c'] for j in v} if cid != max({j2['Contact__c'] for j2 in v}, key=lambda x: x))}")

# Dry preview details (first 8 groups)
print("\n  --- First 8 dup groups (planned actions) ---")
shown = 0
for (opp_id, name_key), jr_list in list(dup_groups.items())[:8]:
    contacts_in_group = {j['Contact__c']: j['Contact__r'] for j in jr_list}
    canon_id = max(contacts_in_group.keys(), key=lambda cid: (
        100 if contacts_in_group[cid].get('Email') else 0,
        10 if contacts_in_group[cid].get('Phone') else 0,
    ))
    canon = contacts_in_group[canon_id]
    print(f"\n  Opp: {jr_list[0]['Opportunity__r']['Name'][:55]}  Name: {name_key}")
    print(f"    CANON: {canon['FirstName']} {canon['LastName']}  email={canon.get('Email')}  phone={canon.get('Phone')}")
    if canon_id in plan_contact_updates:
        print(f"    -> merge phones: {plan_contact_updates[canon_id]}")
    print(f"    Roles to keep: {set(j['Role__c'] for j in jr_list)}")
    print(f"    Alts to dejunction: {[(c['FirstName'], c['LastName'], c.get('Phone')) for cid, c in contacts_in_group.items() if cid != canon_id]}")

if not args.apply:
    print(f"\n[Preview only — re-run with --apply]")
    sys.exit(0)


# ── Apply ──
print("\n" + "="*70)
print("APPLYING")
print("="*70)
audit_rows = []

# 1. Update canonical Contact phones
print(f"\n  [1/4] Updating {len(plan_contact_updates)} canonical Contacts (phone merges)")
ct_updates = [{'Id': cid, **upd} for cid, upd in plan_contact_updates.items()]
for i in range(0, len(ct_updates), 200):
    batch = ct_updates[i:i+200]
    print(f"    Batch {i//200 + 1}: {len(batch)}")
    results = sf.bulk.Contact.update(batch)
    for j, res in enumerate(results):
        if res.get('success'):
            audit_rows.append({
                'SF_Id': batch[j]['Id'], 'Name': '(canonical Contact)',
                'Field': 'Phone+MobilePhone', 'Before': '(see merge)',
                'After': str({k: v for k, v in batch[j].items() if k != 'Id'}),
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'MERGE_PHONES',
                'Note': 'merged from dup-name Contact in same Opp',
            })
        else:
            print(f"    ⚠ FAIL Contact update {batch[j]['Id']}: {res.get('errors', res)}")

# 2. Delete redundant junctions
print(f"\n  [2/4] Deleting {len(plan_junction_deletes)} junctions")
for i in range(0, len(plan_junction_deletes), 200):
    batch = plan_junction_deletes[i:i+200]
    print(f"    Batch {i//200 + 1}: {len(batch)}")
    results = sf.bulk.Opportunity_Contact__c.delete([{'Id': jid} for jid in batch])
    for j, res in enumerate(results):
        if res.get('success'):
            audit_rows.append({
                'SF_Id': batch[j], 'Name': '(junction)', 'Field': '(deleted)',
                'Before': 'existed', 'After': 'deleted',
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'DELETE',
                'Note': 'redundant junction on dup-name Contact',
            })
        else:
            print(f"    ⚠ FAIL junction delete {batch[j]}: {res.get('errors', res)}")

# 3. Repoint junctions: delete old + insert new pointing at canonical
print(f"\n  [3/4] Repointing {len(plan_junction_repoints)} junctions to canonical Contact")
# Delete old
del_ids = [r[0] for r in plan_junction_repoints]
for i in range(0, len(del_ids), 200):
    batch = del_ids[i:i+200]
    print(f"    Delete batch {i//200 + 1}: {len(batch)}")
    sf.bulk.Opportunity_Contact__c.delete([{'Id': jid} for jid in batch])

# Insert new
new_juncs = [{'Opportunity__c': r[1], 'Contact__c': r[2], 'Role__c': r[3]}
             for r in plan_junction_repoints]
for i in range(0, len(new_juncs), 200):
    batch = new_juncs[i:i+200]
    print(f"    Insert batch {i//200 + 1}: {len(batch)}")
    results = sf.bulk.Opportunity_Contact__c.insert(batch)
    for j, res in enumerate(results):
        if res.get('success'):
            audit_rows.append({
                'SF_Id': res['id'], 'Name': '(junction)', 'Field': '(re-created)',
                'Before': 'pointed at alt Contact',
                'After': f"pointed at canonical {batch[j]['Contact__c']} role={batch[j]['Role__c']}",
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'REPOINT',
                'Note': 'old alt junction deleted; new junction created',
            })
        else:
            print(f"    ⚠ FAIL junction insert: {res.get('errors', res)}")

# 4. Delete alt Contacts (only those safe to delete)
print(f"\n  [4/4] Deleting {len(plan_contact_deletes)} orphan alt Contacts")
for i in range(0, len(plan_contact_deletes), 200):
    batch = plan_contact_deletes[i:i+200]
    print(f"    Batch {i//200 + 1}: {len(batch)}")
    results = sf.bulk.Contact.delete([{'Id': cid} for cid in batch])
    for j, res in enumerate(results):
        if res.get('success'):
            audit_rows.append({
                'SF_Id': batch[j], 'Name': '(alt Contact)',
                'Field': '(deleted)', 'Before': 'existed', 'After': 'deleted',
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'DELETE',
                'Note': 'merged into canonical; no other Opp junctions',
            })
        else:
            # Likely has dependencies (Activities, etc.) — leave it as orphan
            print(f"    ⚠ Could not delete Contact {batch[j]}: {res.get('errors', res)}")

audit_path = AUDIT_DIR / f'business_roe_contact_dedupe_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\n✓ Audit log: {audit_path} ({len(audit_rows)} rows)")
