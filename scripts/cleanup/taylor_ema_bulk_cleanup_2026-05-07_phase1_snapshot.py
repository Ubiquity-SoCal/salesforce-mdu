"""Taylor Mauney 2026-05-04 review pass — Phase 1: snapshot + dry run.

Reads TM Notes from "Take 2 MDU Sales Review (Living) - TM updates 5.4.xlsx"
and produces a full pre-delete snapshot of every record we plan to mutate.
Mutates nothing. Phase 2 reads the resolved-targets JSON and executes.

Two action classes from Taylor's notes:
  (A) "Please delete any EMA or Bulk agreement listed" -> delete EMA/Bulk
      Agreement__c children on that Opp. Opp itself stays.
  (B) "Duplicate - delete" -> delete the entire Opp + all children.

Outputs (under SalesForce/audit_logs/2026-05-07_taylor_ema_bulk_cleanup/):
  phase1_resolved_targets.json   - Opp Ids + Agreement Ids Phase 2 will act on
  phase1_snapshot.json           - full field dump of every record to be deleted
  phase1_dryrun_audit.csv        - audit-trail rows in standard format
  phase1_match_report.txt        - matched / unmatched / no-op summary
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, date

import openpyxl
from simple_salesforce import Salesforce

# ---- config ---------------------------------------------------------------

XLSX_PATH = r'C:\Users\cass\Downloads\Take 2 MDU Sales Review (Living) - TM updates 5.4.xlsx'
AUDIT_DIR = r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\2026-05-07_taylor_ema_bulk_cleanup'
SOURCE_TAG = 'TM_review_2026-05-04'

EMA_BULK_TYPES = {'EMA', 'Bulk', 'NEMA', '2nd ISP MSA Addendum', 'MSA',
                  'EMA Addendum', 'Bulk Addendum'}

DELETE_EMA_BULK_NOTE = 'Please delete any EMA or Bulk agreement listed'
DELETE_OPP_NOTES = (
    'Duplicate - delete',
    'Duplicate opportunity with one owned by Melissa - can be deleted',
)

# xlsx Name -> SF Id overrides (when fuzzy match would fail).
# Resolved manually from diag scripts on 2026-05-07.
XLSX_NAME_OVERRIDE = {
    ('Killeen_MDU_Bradley Arms', 'Tanya Friese'): '006WR00000xuzoQYAQ',
    ('117 and 121 W Avenue A Apartments', 'Melissa Baker'): '006WR00000xwGf7YAE',
}

# Dupe -> Keeper map.  Contacts + files on dupes get re-pointed to keepers
# before the dupe is deleted, then cascade kills the rest.
DUPE_KEEPER = {
    '006WR00000xwHL3YAM': '006WR00000wkEboYAE',  # Killeen_MDU_The Bungalows -> The Bungalows (Melissa)
    '006WR00000xuzoQYAQ': '006WR00000wkCjuYAE',  # Killeen_MDU_Bradley Arms -> Bradley Arms (Melissa)
    '006WR00000xwGf7YAE': '006WR00000wk9RtYAI',  # Killeen_MDU_117-121_W_Avenue_A -> 117 and 121 E Avenue A Apartments
}

# Stage to revert all 97 EMA/Bulk-delete Opps to after agreement deletion.
# Per Cass 2026-05-05 they were bulk-moved PAL/ROE Complete -> Marketing/Bulk In Progress;
# without their EMA/Bulk records they belong back in PAL/ROE Complete.
STAGE_REVERT_TO = 'PAL/ROE Complete'

# ---- helpers --------------------------------------------------------------

def jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v

def record_to_dict(rec):
    return {k: jsonable(v) for k, v in rec.items() if k != 'attributes'}

# ---- read xlsx ------------------------------------------------------------

print('Reading xlsx...')
wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
ws = wb.active

delete_ab = []  # list[(opp_name, owner_name)]
delete_opp = []
for row in ws.iter_rows(min_row=2, values_only=True):
    name, stage, _sub, owner = row[0], row[1], row[2], row[3]
    note = row[20]
    if not note:
        continue
    note = str(note).strip()
    if note == DELETE_EMA_BULK_NOTE:
        delete_ab.append((name, owner, stage))
    elif note in DELETE_OPP_NOTES:
        delete_opp.append((name, owner, stage))
    else:
        print(f'  WARN unknown note: [{owner}] {name}: {note!r}')

print(f'  {len(delete_ab)} Opps flagged for EMA/Bulk Agreement deletion')
print(f'  {len(delete_opp)} Opps flagged for full Opp deletion')

# ---- SF connect -----------------------------------------------------------

print('\nConnecting to Salesforce...')
sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# ---- match xlsx rows to SF Opp Ids ----------------------------------------

all_target_names = list({n for n, _, _ in delete_ab + delete_opp})
override_ids = list(XLSX_NAME_OVERRIDE.values())
print(f'\nResolving {len(all_target_names)} Opp names + {len(override_ids)} overrides to SF Ids...')

# escape single quotes in names
def soql_quote_list(items):
    return ','.join("'" + s.replace("'", "\\'") + "'" for s in items)

opps_by_name = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name, StageName, RecordType.DeveloperName,
           CreatedDate, LastModifiedDate
    FROM Opportunity
    WHERE Name IN ({soql_quote_list(all_target_names)})
""")['records']

opps_by_id = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name, StageName, RecordType.DeveloperName,
           CreatedDate, LastModifiedDate
    FROM Opportunity
    WHERE Id IN ({soql_quote_list(override_ids)})
""")['records']
print(f'  By-name: {len(opps_by_name)}  By-id (overrides): {len(opps_by_id)}')

# Index by (name, owner) and by Id
by_name_owner = defaultdict(list)
by_id = {}
for o in opps_by_name + opps_by_id:
    owner_name = o['Owner']['Name'] if o.get('Owner') else None
    by_name_owner[(o['Name'], owner_name)].append(o)
    by_id[o['Id']] = o

def resolve(name, owner):
    if (name, owner) in XLSX_NAME_OVERRIDE:
        oid = XLSX_NAME_OVERRIDE[(name, owner)]
        return [by_id[oid]] if oid in by_id else []
    return by_name_owner.get((name, owner), [])

# resolve and collect issues
resolved_ab = []   # list[opp_record]
resolved_opp = []  # list[opp_record]
issues = []

for name, owner, stage in delete_ab:
    cands = resolve(name, owner)
    if len(cands) == 1:
        resolved_ab.append(cands[0])
    elif len(cands) == 0:
        issues.append(f'NO MATCH (delete-AB): [{owner}] {name}')
    else:
        issues.append(f'MULTIPLE MATCHES (delete-AB): [{owner}] {name} -> {[c["Id"] for c in cands]}')

for name, owner, stage in delete_opp:
    cands = resolve(name, owner)
    if len(cands) == 1:
        resolved_opp.append(cands[0])
    elif len(cands) == 0:
        issues.append(f'NO MATCH (delete-Opp): [{owner}] {name}')
    else:
        issues.append(f'MULTIPLE MATCHES (delete-Opp): [{owner}] {name} -> {[c["Id"] for c in cands]}')

print(f'  Resolved {len(resolved_ab)}/{len(delete_ab)} for EMA/Bulk delete')
print(f'  Resolved {len(resolved_opp)}/{len(delete_opp)} for full Opp delete')
if issues:
    print(f'  {len(issues)} issues — see match report')

# ---- pull Agreement children for the EMA/Bulk-delete Opps ----------------

resolved_ab_ids = [o['Id'] for o in resolved_ab]
agr_ema_bulk_by_opp = defaultdict(list)
no_op_opps = []  # Opps where Taylor said delete EMA/Bulk but none exist

if resolved_ab_ids:
    print(f'\nPulling Agreements for {len(resolved_ab_ids)} Opps...')
    # chunk because SOQL IN-list has a length limit
    chunk = 200
    all_agrs = []
    for i in range(0, len(resolved_ab_ids), chunk):
        batch = resolved_ab_ids[i:i+chunk]
        ids_str = "','".join(batch)
        rs = sf.query_all(f"""
            SELECT Id, Name, Opportunity__c, Opportunity__r.Name, Status__c,
                   Agreement_Type__c, Signed_Date__c, IronClad_ID__c,
                   IronClad_Stage__c, CreatedDate, LastModifiedDate, Notes__c
            FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
        """)['records']
        all_agrs.extend(rs)

    for a in all_agrs:
        if a.get('Agreement_Type__c') in EMA_BULK_TYPES:
            agr_ema_bulk_by_opp[a['Opportunity__c']].append(a)

    for opp in resolved_ab:
        if not agr_ema_bulk_by_opp.get(opp['Id']):
            no_op_opps.append(opp)

    print(f'  Found EMA/Bulk Agreement records on {len(agr_ema_bulk_by_opp)} Opps')
    print(f'  No-op Opps (no EMA/Bulk to delete): {len(no_op_opps)}')

agreements_to_delete = [a for agrs in agr_ema_bulk_by_opp.values() for a in agrs]
print(f'  Total Agreement records to delete: {len(agreements_to_delete)}')

# ---- pull full data for the 3 dupe Opps -----------------------------------

dupe_opp_full = []
if resolved_opp:
    print(f'\nPulling full record + children for {len(resolved_opp)} dupe Opps...')
    dupe_ids = [o['Id'] for o in resolved_opp]
    ids_str = "','".join(dupe_ids)

    full_opps = sf.query_all(f"""
        SELECT FIELDS(ALL) FROM Opportunity WHERE Id IN ('{ids_str}') LIMIT 200
    """)['records']

    child_agrs = sf.query_all(f"""
        SELECT FIELDS(ALL) FROM Agreement__c
        WHERE Opportunity__c IN ('{ids_str}') LIMIT 200
    """)['records']

    child_oppcontacts = sf.query_all(f"""
        SELECT FIELDS(ALL) FROM Opportunity_Contact__c
        WHERE Opportunity__c IN ('{ids_str}') LIMIT 200
    """)['records']

    notes = sf.query_all(f"""
        SELECT Id, Title, Body, ParentId, CreatedDate
        FROM Note WHERE ParentId IN ('{ids_str}') LIMIT 200
    """)['records']

    contentlinks = sf.query_all(f"""
        SELECT Id, ContentDocumentId, LinkedEntityId
        FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids_str}') LIMIT 200
    """)['records']

    by_id = {o['Id']: o for o in full_opps}
    agrs_by_opp = defaultdict(list)
    for a in child_agrs:
        agrs_by_opp[a['Opportunity__c']].append(a)
    contacts_by_opp = defaultdict(list)
    for c in child_oppcontacts:
        contacts_by_opp[c['Opportunity__c']].append(c)
    notes_by_opp = defaultdict(list)
    for n in notes:
        notes_by_opp[n['ParentId']].append(n)
    links_by_opp = defaultdict(list)
    for l in contentlinks:
        links_by_opp[l['LinkedEntityId']].append(l)

    for opp in resolved_opp:
        oid = opp['Id']
        full = by_id.get(oid, opp)
        dupe_opp_full.append({
            'opportunity': record_to_dict(full),
            'agreements': [record_to_dict(a) for a in agrs_by_opp.get(oid, [])],
            'opportunity_contacts': [record_to_dict(c) for c in contacts_by_opp.get(oid, [])],
            'notes': [record_to_dict(n) for n in notes_by_opp.get(oid, [])],
            'content_document_links': [record_to_dict(l) for l in links_by_opp.get(oid, [])],
        })

    for d in dupe_opp_full:
        nm = d['opportunity']['Name']
        print(f"  {nm} ({d['opportunity']['Id']}): {len(d['agreements'])} agr, "
              f"{len(d['opportunity_contacts'])} contact-junctions, "
              f"{len(d['notes'])} notes, {len(d['content_document_links'])} files")

# ---- build re-point plan (dupe -> keeper) ---------------------------------

repoint_plan = []

if dupe_opp_full:
    keeper_ids = [DUPE_KEEPER[d['opportunity']['Id']] for d in dupe_opp_full
                  if d['opportunity']['Id'] in DUPE_KEEPER]
    if keeper_ids:
        keeper_ids_str = "','".join(keeper_ids)
        keeper_contacts = sf.query_all(f"""
            SELECT Id, Opportunity__c, Contact__c, Contact__r.Name, Role__c
            FROM Opportunity_Contact__c WHERE Opportunity__c IN ('{keeper_ids_str}')
        """)['records']
        keeper_agrs = sf.query_all(f"""
            SELECT Id, Opportunity__c, Agreement_Type__c, Status__c
            FROM Agreement__c WHERE Opportunity__c IN ('{keeper_ids_str}')
        """)['records']
        keeper_agr_types_by_opp = defaultdict(set)
        for ka in keeper_agrs:
            keeper_agr_types_by_opp[ka['Opportunity__c']].add(ka.get('Agreement_Type__c'))

        # Resolve Contact names for dupe junctions (FIELDS(ALL) doesn't traverse)
        dupe_contact_ids = list({j['Contact__c'] for d in dupe_opp_full
                                  for j in d['opportunity_contacts'] if j.get('Contact__c')})
        contact_name_by_id = {}
        if dupe_contact_ids:
            cs = sf.query_all(f"""
                SELECT Id, Name FROM Contact
                WHERE Id IN ('{"','".join(dupe_contact_ids)}')
            """)['records']
            contact_name_by_id = {c['Id']: c['Name'] for c in cs}

        # Resolve ContentDocument titles for dupe links
        dupe_doc_ids = list({l['ContentDocumentId'] for d in dupe_opp_full
                              for l in d['content_document_links'] if l.get('ContentDocumentId')})
        doc_title_by_id = {}
        if dupe_doc_ids:
            ds = sf.query_all(f"""
                SELECT Id, Title FROM ContentDocument
                WHERE Id IN ('{"','".join(dupe_doc_ids)}')
            """)['records']
            doc_title_by_id = {d['Id']: d['Title'] for d in ds}
        keeper_links = sf.query_all(f"""
            SELECT Id, ContentDocumentId, LinkedEntityId
            FROM ContentDocumentLink WHERE LinkedEntityId IN ('{keeper_ids_str}')
        """)['records']

        keeper_contact_ids_by_opp = defaultdict(set)
        for kc in keeper_contacts:
            keeper_contact_ids_by_opp[kc['Opportunity__c']].add(kc['Contact__c'])
        keeper_doc_ids_by_opp = defaultdict(set)
        for kl in keeper_links:
            keeper_doc_ids_by_opp[kl['LinkedEntityId']].add(kl['ContentDocumentId'])

        print('\nBuilding re-point plan...')
        for d in dupe_opp_full:
            dupe_id = d['opportunity']['Id']
            keeper_id = DUPE_KEEPER.get(dupe_id)
            if not keeper_id:
                continue
            existing_contacts = keeper_contact_ids_by_opp[keeper_id]
            existing_docs = keeper_doc_ids_by_opp[keeper_id]
            existing_agr_types = keeper_agr_types_by_opp[keeper_id]

            # Junctions to re-parent: those whose Contact__c is NOT already on keeper
            junctions_to_reparent = []
            junctions_to_drop = []
            for j in d['opportunity_contacts']:
                if j.get('Contact__c') in existing_contacts:
                    junctions_to_drop.append(j)
                else:
                    junctions_to_reparent.append(j)

            # File links to create: those whose ContentDocumentId is NOT already on keeper
            links_to_create = []
            links_to_drop = []
            for l in d['content_document_links']:
                if l.get('ContentDocumentId') in existing_docs:
                    links_to_drop.append(l)
                else:
                    links_to_create.append(l)

            # Agreement records to re-parent: those with Agreement_Type__c
            # that the keeper doesn't already have AND that look durable
            # (Status=Completed and a Signed_Date).  Cascade-delete the rest.
            agrs_to_reparent = []
            agrs_to_drop = []
            for a in d['agreements']:
                atype = a.get('Agreement_Type__c')
                durable = (a.get('Status__c') == 'Completed' and a.get('Signed_Date__c'))
                if atype and atype not in existing_agr_types and durable:
                    agrs_to_reparent.append(a)
                else:
                    agrs_to_drop.append(a)

            repoint_plan.append({
                'dupe_opp_id': dupe_id,
                'dupe_opp_name': d['opportunity']['Name'],
                'keeper_opp_id': keeper_id,
                'reparent_junctions': [
                    {'Id': j['Id'], 'Contact__c': j['Contact__c'],
                     'Contact_Name': contact_name_by_id.get(j.get('Contact__c')),
                     'Role__c': j.get('Role__c')}
                    for j in junctions_to_reparent
                ],
                'drop_junctions': [
                    {'Id': j['Id'], 'Contact__c': j['Contact__c'],
                     'Contact_Name': contact_name_by_id.get(j.get('Contact__c')),
                     'reason': 'Contact already on keeper'}
                    for j in junctions_to_drop
                ],
                'create_doc_links': [
                    {'ContentDocumentId': l['ContentDocumentId'],
                     'Title': doc_title_by_id.get(l['ContentDocumentId'])}
                    for l in links_to_create
                ],
                'drop_doc_links': [
                    {'ContentDocumentId': l['ContentDocumentId'],
                     'Title': doc_title_by_id.get(l['ContentDocumentId']),
                     'reason': 'Document already linked to keeper'}
                    for l in links_to_drop
                ],
                'reparent_agreements': [
                    {'Id': a['Id'], 'Name': a['Name'],
                     'Agreement_Type__c': a.get('Agreement_Type__c'),
                     'Status__c': a.get('Status__c'),
                     'Signed_Date__c': a.get('Signed_Date__c')}
                    for a in agrs_to_reparent
                ],
                'drop_agreements': [
                    {'Id': a['Id'], 'Name': a['Name'],
                     'Agreement_Type__c': a.get('Agreement_Type__c'),
                     'Status__c': a.get('Status__c'),
                     'reason': 'type already on keeper or not durable (no Signed_Date)'}
                    for a in agrs_to_drop
                ],
            })

            print(f"  {d['opportunity']['Name']} -> keeper {keeper_id}")
            print(f"    re-parent {len(junctions_to_reparent)} contact junction(s), "
                  f"drop-as-dupe {len(junctions_to_drop)}")
            print(f"    create {len(links_to_create)} file link(s), "
                  f"drop-as-dupe {len(links_to_drop)}")
            print(f"    re-parent {len(agrs_to_reparent)} agreement(s), "
                  f"cascade-delete {len(agrs_to_drop)}")

# ---- write outputs --------------------------------------------------------

os.makedirs(AUDIT_DIR, exist_ok=True)

# resolved-targets — Phase 2 reads this
resolved_targets = {
    'generated_at': datetime.now().isoformat(),
    'source': SOURCE_TAG,
    'agreements_to_delete': [
        {
            'Id': a['Id'],
            'Name': a['Name'],
            'Opportunity__c': a['Opportunity__c'],
            'Opportunity_Name': a['Opportunity__r']['Name'] if a.get('Opportunity__r') else None,
            'Agreement_Type__c': a.get('Agreement_Type__c'),
            'Status__c': a.get('Status__c'),
        }
        for a in agreements_to_delete
    ],
    'opportunities_to_delete': [
        {
            'Id': d['opportunity']['Id'],
            'Name': d['opportunity']['Name'],
            'StageName': d['opportunity'].get('StageName'),
            'keeper_id': DUPE_KEEPER.get(d['opportunity']['Id']),
            'child_agreement_ids': [a['Id'] for a in d['agreements']],
            'child_oppcontact_ids': [c['Id'] for c in d['opportunity_contacts']],
        }
        for d in dupe_opp_full
    ],
    'repoint_plan': repoint_plan,
    'opportunities_to_revert_stage': [
        {
            'Id': o['Id'],
            'Name': o['Name'],
            'CurrentStage': o['StageName'],
            'NewStage': STAGE_REVERT_TO,
        }
        for o in resolved_ab if o['StageName'] != STAGE_REVERT_TO
    ],
    'no_op_opps': [{'Id': o['Id'], 'Name': o['Name']} for o in no_op_opps],
    'unresolved_issues': issues,
}

with open(os.path.join(AUDIT_DIR, 'phase1_resolved_targets.json'), 'w', encoding='utf-8') as f:
    json.dump(resolved_targets, f, indent=2)

# full snapshot — what we'd need to reconstruct
snapshot = {
    'generated_at': datetime.now().isoformat(),
    'source': SOURCE_TAG,
    'agreements': [record_to_dict(a) for a in agreements_to_delete],
    'opportunities_full': dupe_opp_full,
}
with open(os.path.join(AUDIT_DIR, 'phase1_snapshot.json'), 'w', encoding='utf-8') as f:
    json.dump(snapshot, f, indent=2, default=jsonable)

# audit CSV — standard format
audit_rows = []
ts = datetime.now().isoformat()
for a in agreements_to_delete:
    audit_rows.append({
        'SF_Id': a['Id'],
        'Name': a['Name'],
        'Object': 'Agreement__c',
        'Field': '*record*',
        'Before': json.dumps(record_to_dict(a), default=jsonable),
        'After': '(would be deleted)',
        'Source': SOURCE_TAG,
        'Action': 'DryRun-Delete',
        'Timestamp': ts,
    })
for d in dupe_opp_full:
    audit_rows.append({
        'SF_Id': d['opportunity']['Id'],
        'Name': d['opportunity']['Name'],
        'Object': 'Opportunity',
        'Field': '*record*',
        'Before': json.dumps(d['opportunity'], default=jsonable),
        'After': '(would be deleted)',
        'Source': SOURCE_TAG,
        'Action': 'DryRun-Delete',
        'Timestamp': ts,
    })

with open(os.path.join(AUDIT_DIR, 'phase1_dryrun_audit.csv'), 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Object', 'Field', 'Before', 'After', 'Source', 'Action', 'Timestamp'])
    w.writeheader()
    w.writerows(audit_rows)

# match report — human-readable
report_lines = [
    f'Phase 1 dry-run summary  ({datetime.now().isoformat()})',
    '',
    f'Source xlsx: {XLSX_PATH}',
    f'Source tag:  {SOURCE_TAG}',
    '',
    '== Resolution ==',
    f'  Opps flagged for EMA/Bulk delete:  {len(delete_ab)}',
    f'  Opps resolved to SF:               {len(resolved_ab)}',
    f'  Opps flagged for full Opp delete:  {len(delete_opp)}',
    f'  Opps resolved to SF:               {len(resolved_opp)}',
    '',
    '== Mutations Phase 2 will perform ==',
    f'  Agreement__c records to delete:    {len(agreements_to_delete)}',
    f'  Opportunity records to delete:     {len(dupe_opp_full)}',
    f'  Opps to revert to PAL/ROE Complete: {len(resolved_targets["opportunities_to_revert_stage"])}',
    f'  Junctions to re-parent:            {sum(len(p["reparent_junctions"]) for p in repoint_plan)}',
    f'  ContentDocumentLinks to create:    {sum(len(p["create_doc_links"]) for p in repoint_plan)}',
    f'  Agreements to re-parent:           {sum(len(p["reparent_agreements"]) for p in repoint_plan)}',
    f'  No-op Opps (no EMA/Bulk to delete, will be skipped): {len(no_op_opps)}',
    '',
    '== Unresolved issues ==',
]
if issues:
    report_lines.extend('  ' + s for s in issues)
else:
    report_lines.append('  (none)')

report_lines += ['', '== Per-stage breakdown of Opps in delete-AB scope ==']
stage_counts = defaultdict(int)
for o in resolved_ab:
    stage_counts[o['StageName']] += 1
for s, c in sorted(stage_counts.items(), key=lambda x: -x[1]):
    report_lines.append(f'  {s}: {c}')

report_lines += ['', '== Re-point plan (dupe -> keeper) ==']
if repoint_plan:
    for p in repoint_plan:
        report_lines.append(f"  {p['dupe_opp_name']} ({p['dupe_opp_id']}) -> keeper {p['keeper_opp_id']}")
        for j in p['reparent_junctions']:
            report_lines.append(f"    re-parent contact junction: {j['Contact_Name'] or '(unnamed)'} ({j.get('Role__c') or 'no role'})")
        for j in p['drop_junctions']:
            report_lines.append(f"    drop dup junction (already on keeper): {j['Contact_Name'] or '(unnamed)'}")
        for l in p['create_doc_links']:
            report_lines.append(f"    create doc link to keeper: {l['Title'] or '(untitled)'} [{l['ContentDocumentId']}]")
        for l in p['drop_doc_links']:
            report_lines.append(f"    drop dup doc link (already on keeper): {l['Title'] or '(untitled)'} [{l['ContentDocumentId']}]")
        for a in p['reparent_agreements']:
            report_lines.append(f"    re-parent agreement: {a['Name']} ({a['Agreement_Type__c']}, signed {a.get('Signed_Date__c')})")
        for a in p['drop_agreements']:
            report_lines.append(f"    cascade-delete agreement: {a['Name']} ({a['Agreement_Type__c']}, {a['reason']})")
else:
    report_lines.append('  (none)')

report_lines += ['', '== Stage revert (post Agreement-delete) ==',
                 f'  Reverting all 97 Opps from Marketing/Bulk In Progress -> {STAGE_REVERT_TO}']

report_lines += ['', '== No-op Opps (Taylor flagged but no EMA/Bulk Agreement found) ==']
if no_op_opps:
    for o in no_op_opps:
        report_lines.append(f"  {o['Name']} ({o['Id']}) — owner: {o['Owner']['Name']}, stage: {o['StageName']}")
else:
    report_lines.append('  (none)')

with open(os.path.join(AUDIT_DIR, 'phase1_match_report.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(report_lines))

print('\n' + '=' * 60)
print(f'Phase 1 complete. Audit folder: {AUDIT_DIR}')
print('=' * 60)
print('\n'.join(report_lines[3:]))
