"""Taylor Mauney 2026-05-04 review pass — Phase 2: execute.

Reads phase1_resolved_targets.json and executes mutations one step at a time.
Each step requires explicit --step <name> and a typed "yes" confirmation.

Steps (run in this order):
  repoint         Re-parent contact junctions + create ContentDocumentLinks on keepers
  agreements      Hard-delete 187 EMA/Bulk Agreement__c records
  opps            Hard-delete 3 dupe Opportunity records (after repoint)
  stage_revert    Bulk-update 97 Opps from Marketing/Bulk In Progress -> PAL/ROE Complete

Each step writes an audit CSV to:
  SalesForce/audit_logs/2026-05-07_taylor_ema_bulk_cleanup/phase2_<step>_<timestamp>.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# ---- config ---------------------------------------------------------------

AUDIT_DIR = r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\2026-05-07_taylor_ema_bulk_cleanup'
TARGETS_PATH = os.path.join(AUDIT_DIR, 'phase1_resolved_targets.json')
SOURCE_TAG = 'TM_review_2026-05-04'

VALID_STEPS = ('repoint', 'agreements', 'opps', 'stage_revert')

# ---- helpers --------------------------------------------------------------

def confirm(prompt: str) -> bool:
    print(f'\n{prompt}')
    print('Type exactly "yes" to proceed (anything else aborts):')
    return input('> ').strip() == 'yes'

def open_audit(step: str) -> tuple[csv.DictWriter, object]:
    ts = datetime.now().strftime('%Y%m%dT%H%M%S')
    path = os.path.join(AUDIT_DIR, f'phase2_{step}_{ts}.csv')
    f = open(path, 'w', encoding='utf-8', newline='')
    w = csv.DictWriter(f, fieldnames=[
        'SF_Id', 'Name', 'Object', 'Field', 'Before', 'After',
        'Source', 'Action', 'Result', 'Error', 'Timestamp',
    ])
    w.writeheader()
    print(f'  Audit -> {path}')
    return w, f

def now_iso() -> str:
    return datetime.now().isoformat()

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ---- step: repoint --------------------------------------------------------

def step_repoint(sf: Salesforce, targets: dict):
    """Path B: Opportunity__c FK is master-detail without reparenting on both
    Opportunity_Contact__c and Agreement__c, so we cannot update().  Instead:

      - Junctions: create new Opportunity_Contact__c on keeper with the same
        (Contact__c, Role__c).  Old junction cascade-deletes with the dupe Opp.
      - Agreements: create cloned Agreement__c on keeper copying Type/Status/
        Signed_Date/Notes.  Old agreement cascade-deletes with the dupe Opp.
        Clone gets a new auto-number Name.
      - CDLs: query keeper's existing links and skip any already present
        (idempotent re-runs).
    """
    plan = targets['repoint_plan']

    # Pre-fetch keeper current state for idempotency
    keeper_ids = list({p['keeper_opp_id'] for p in plan})
    keeper_ids_str = "','".join(keeper_ids)
    existing_keeper_contacts = sf.query_all(f"""
        SELECT Opportunity__c, Contact__c FROM Opportunity_Contact__c
        WHERE Opportunity__c IN ('{keeper_ids_str}')
    """)['records']
    keeper_contact_set = {(c['Opportunity__c'], c['Contact__c']) for c in existing_keeper_contacts}

    existing_keeper_links = sf.query_all(f"""
        SELECT ContentDocumentId, LinkedEntityId FROM ContentDocumentLink
        WHERE LinkedEntityId IN ('{keeper_ids_str}')
    """)['records']
    keeper_link_set = {(l['LinkedEntityId'], l['ContentDocumentId']) for l in existing_keeper_links}

    existing_keeper_agrs = sf.query_all(f"""
        SELECT Opportunity__c, Agreement_Type__c FROM Agreement__c
        WHERE Opportunity__c IN ('{keeper_ids_str}')
    """)['records']
    keeper_agr_type_set = {(a['Opportunity__c'], a.get('Agreement_Type__c'))
                           for a in existing_keeper_agrs}

    # Plan accounting after idempotency filter
    todo_junctions = []
    todo_links = []
    todo_agrs = []
    for p in plan:
        kid = p['keeper_opp_id']
        for j in p['reparent_junctions']:
            cid = j.get('Contact__c')
            if (kid, cid) not in keeper_contact_set:
                todo_junctions.append((p, j))
        for l in p['create_doc_links']:
            if (kid, l['ContentDocumentId']) not in keeper_link_set:
                todo_links.append((p, l))
        for a in p.get('reparent_agreements', []):
            atype = a.get('Agreement_Type__c')
            if (kid, atype) not in keeper_agr_type_set:
                todo_agrs.append((p, a))

    skipped_j = sum(len(p['reparent_junctions']) for p in plan) - len(todo_junctions)
    skipped_l = sum(len(p['create_doc_links']) for p in plan) - len(todo_links)
    skipped_a = sum(len(p.get('reparent_agreements', [])) for p in plan) - len(todo_agrs)

    print(f'\nIdempotency check vs current keeper state:')
    print(f'  junctions to create:      {len(todo_junctions)} (skipping {skipped_j} already on keeper)')
    print(f'  CDLs to create:           {len(todo_links)} (skipping {skipped_l} already on keeper)')
    print(f'  agreements to clone:      {len(todo_agrs)} (skipping {skipped_a} type already on keeper)')

    if not (todo_junctions or todo_links or todo_agrs):
        print('\nNothing to do.  Repoint already complete.')
        return

    if not confirm(f'STEP repoint (clone strategy): create {len(todo_junctions)} junction(s), '
                   f'{len(todo_links)} CDL(s), {len(todo_agrs)} Agreement clone(s).  Proceed?'):
        print('Aborted.')
        return

    # We need full Agreement source data to clone.  Re-fetch minimal required fields.
    agr_src_by_id = {}
    if todo_agrs:
        ids = list({a['Id'] for _, a in todo_agrs})
        rs = sf.query_all(f"""
            SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
                   IronClad_ID__c, IronClad_Stage__c, Notes__c
            FROM Agreement__c WHERE Id IN ('{"','".join(ids)}')
        """)['records']
        agr_src_by_id = {a['Id']: a for a in rs}

    w, f = open_audit('repoint')
    try:
        # Junction clones
        for p, j in todo_junctions:
            keeper_id = p['keeper_opp_id']
            dupe_id = p['dupe_opp_id']
            cname = j.get('Contact_Name') or '(unnamed)'
            payload = {'Opportunity__c': keeper_id, 'Contact__c': j['Contact__c']}
            if j.get('Role__c'):
                payload['Role__c'] = j['Role__c']
            try:
                res = sf.Opportunity_Contact__c.create(payload)
                new_id = res.get('id')
                w.writerow({
                    'SF_Id': new_id or '',
                    'Name': cname,
                    'Object': 'Opportunity_Contact__c',
                    'Field': '*record*',
                    'Before': f'(was on dupe {dupe_id} as {j["Id"]})',
                    'After': f'(new junction on keeper {keeper_id})',
                    'Source': SOURCE_TAG,
                    'Action': 'Clone',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  cloned junction {new_id} ({cname}, {j.get("Role__c")}) on keeper {keeper_id}')
            except Exception as e:
                w.writerow({
                    'SF_Id': '', 'Name': cname,
                    'Object': 'Opportunity_Contact__c', 'Field': '*record*',
                    'Before': f'(was on dupe {dupe_id})', 'After': '',
                    'Source': SOURCE_TAG, 'Action': 'Clone',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL junction clone {cname}: {e}')

        # Agreement clones
        for p, a_plan in todo_agrs:
            keeper_id = p['keeper_opp_id']
            dupe_id = p['dupe_opp_id']
            src = agr_src_by_id.get(a_plan['Id'])
            if not src:
                print(f'  SKIP agreement {a_plan["Name"]}: source data not found')
                continue
            payload = {
                'Opportunity__c': keeper_id,
                'Agreement_Type__c': src.get('Agreement_Type__c'),
                'Status__c': src.get('Status__c'),
            }
            if src.get('Signed_Date__c'):
                payload['Signed_Date__c'] = src['Signed_Date__c']
            if src.get('Notes__c'):
                payload['Notes__c'] = src['Notes__c']
            # Provenance breadcrumb so it's clear in the keeper how this got there
            provenance = (f'[Cloned from {src["Name"]} ({src["Id"]}) on dupe Opp {dupe_id} '
                          f'during 2026-05-07 Taylor cleanup]')
            payload['Notes__c'] = ((src.get('Notes__c') or '') + '\n' + provenance).strip()
            try:
                res = sf.Agreement__c.create(payload)
                new_id = res.get('id')
                w.writerow({
                    'SF_Id': new_id or '',
                    'Name': f'(clone of {src["Name"]})',
                    'Object': 'Agreement__c',
                    'Field': '*record*',
                    'Before': json.dumps({
                        'src_id': src['Id'], 'src_name': src['Name'],
                        'dupe_opp': dupe_id,
                        'Agreement_Type__c': src.get('Agreement_Type__c'),
                        'Status__c': src.get('Status__c'),
                        'Signed_Date__c': src.get('Signed_Date__c'),
                    }),
                    'After': f'(new Agreement on keeper {keeper_id})',
                    'Source': SOURCE_TAG,
                    'Action': 'Clone',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  cloned agreement {src["Name"]} -> new Id {new_id} '
                      f'({src.get("Agreement_Type__c")}) on keeper {keeper_id}')
            except Exception as e:
                w.writerow({
                    'SF_Id': '', 'Name': f'(clone of {src["Name"]})',
                    'Object': 'Agreement__c', 'Field': '*record*',
                    'Before': src['Id'], 'After': '',
                    'Source': SOURCE_TAG, 'Action': 'Clone',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL agreement clone {src["Name"]}: {e}')

        # ContentDocumentLink creates (skipping already-linked)
        for p, l in todo_links:
            keeper_id = p['keeper_opp_id']
            dupe_id = p['dupe_opp_id']
            cdid = l['ContentDocumentId']
            title = l.get('Title') or '(untitled)'
            try:
                res = sf.ContentDocumentLink.create({
                    'ContentDocumentId': cdid,
                    'LinkedEntityId': keeper_id,
                    'ShareType': 'V',
                    'Visibility': 'AllUsers',
                })
                new_id = res.get('id')
                w.writerow({
                    'SF_Id': new_id or '',
                    'Name': title,
                    'Object': 'ContentDocumentLink',
                    'Field': 'LinkedEntityId',
                    'Before': dupe_id,
                    'After': keeper_id,
                    'Source': SOURCE_TAG,
                    'Action': 'Create',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  created CDL {new_id} for "{title}" on keeper {keeper_id}')
            except Exception as e:
                w.writerow({
                    'SF_Id': '', 'Name': title,
                    'Object': 'ContentDocumentLink', 'Field': 'LinkedEntityId',
                    'Before': dupe_id, 'After': keeper_id,
                    'Source': SOURCE_TAG, 'Action': 'Create',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL CDL "{title}": {e}')
    finally:
        f.close()
    print('repoint step complete.')

# ---- step: agreements -----------------------------------------------------

def step_agreements(sf: Salesforce, targets: dict):
    agrs = targets['agreements_to_delete']
    if not confirm(f'STEP agreements: hard-delete {len(agrs)} Agreement__c record(s).  Proceed?'):
        print('Aborted.')
        return

    w, f = open_audit('agreements')
    try:
        # Delete one-by-one for stability + audit precision.
        for a in agrs:
            aid = a['Id']
            try:
                sf.Agreement__c.delete(aid)
                w.writerow({
                    'SF_Id': aid,
                    'Name': a['Name'],
                    'Object': 'Agreement__c',
                    'Field': '*record*',
                    'Before': json.dumps({k: a.get(k) for k in
                        ('Name', 'Opportunity__c', 'Opportunity_Name',
                         'Agreement_Type__c', 'Status__c')}),
                    'After': 'deleted',
                    'Source': SOURCE_TAG,
                    'Action': 'Delete',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  deleted {a["Name"]} ({aid}) [{a.get("Agreement_Type__c")}/{a.get("Status__c")}]')
            except Exception as e:
                w.writerow({
                    'SF_Id': aid, 'Name': a['Name'],
                    'Object': 'Agreement__c', 'Field': '*record*',
                    'Before': '', 'After': '',
                    'Source': SOURCE_TAG, 'Action': 'Delete',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL {a["Name"]} ({aid}): {e}')
    finally:
        f.close()
    print('agreements step complete.')

# ---- step: opps -----------------------------------------------------------

def step_opps(sf: Salesforce, targets: dict):
    opps = targets['opportunities_to_delete']
    if not confirm(f'STEP opps: hard-delete {len(opps)} Opportunity record(s).  Proceed?'):
        print('Aborted.')
        return

    w, f = open_audit('opps')
    try:
        for o in opps:
            oid = o['Id']
            try:
                sf.Opportunity.delete(oid)
                w.writerow({
                    'SF_Id': oid,
                    'Name': o['Name'],
                    'Object': 'Opportunity',
                    'Field': '*record*',
                    'Before': json.dumps({k: o.get(k) for k in
                        ('Name', 'StageName', 'keeper_id',
                         'child_agreement_ids', 'child_oppcontact_ids')}),
                    'After': 'deleted',
                    'Source': SOURCE_TAG,
                    'Action': 'Delete',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  deleted Opp {o["Name"]} ({oid})')
            except Exception as e:
                w.writerow({
                    'SF_Id': oid, 'Name': o['Name'],
                    'Object': 'Opportunity', 'Field': '*record*',
                    'Before': '', 'After': '',
                    'Source': SOURCE_TAG, 'Action': 'Delete',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL Opp {o["Name"]} ({oid}): {e}')
    finally:
        f.close()
    print('opps step complete.')

# ---- step: stage_revert ---------------------------------------------------

def step_stage_revert(sf: Salesforce, targets: dict):
    moves = targets['opportunities_to_revert_stage']
    if not confirm(f'STEP stage_revert: update {len(moves)} Opportunity StageName.  Proceed?'):
        print('Aborted.')
        return

    w, f = open_audit('stage_revert')
    try:
        for o in moves:
            oid = o['Id']
            try:
                sf.Opportunity.update(oid, {'StageName': o['NewStage']})
                w.writerow({
                    'SF_Id': oid,
                    'Name': o['Name'],
                    'Object': 'Opportunity',
                    'Field': 'StageName',
                    'Before': o['CurrentStage'],
                    'After': o['NewStage'],
                    'Source': SOURCE_TAG,
                    'Action': 'Update',
                    'Result': 'OK',
                    'Error': '',
                    'Timestamp': now_iso(),
                })
                print(f'  {o["Name"]}: {o["CurrentStage"]} -> {o["NewStage"]}')
            except Exception as e:
                w.writerow({
                    'SF_Id': oid, 'Name': o['Name'],
                    'Object': 'Opportunity', 'Field': 'StageName',
                    'Before': o['CurrentStage'], 'After': o['NewStage'],
                    'Source': SOURCE_TAG, 'Action': 'Update',
                    'Result': 'FAIL', 'Error': str(e),
                    'Timestamp': now_iso(),
                })
                print(f'  FAIL {o["Name"]}: {e}')
    finally:
        f.close()
    print('stage_revert step complete.')

# ---- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--step', required=True, choices=VALID_STEPS,
                    help='Which mutation step to run')
    args = ap.parse_args()

    if not os.path.exists(TARGETS_PATH):
        print(f'ERROR: {TARGETS_PATH} not found. Run Phase 1 first.')
        sys.exit(1)

    with open(TARGETS_PATH, encoding='utf-8') as f:
        targets = json.load(f)

    print(f'Loaded targets generated at {targets.get("generated_at")}')
    print(f'Connecting to Salesforce...')
    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )

    {
        'repoint': step_repoint,
        'agreements': step_agreements,
        'opps': step_opps,
        'stage_revert': step_stage_revert,
    }[args.step](sf, targets)

if __name__ == '__main__':
    main()
