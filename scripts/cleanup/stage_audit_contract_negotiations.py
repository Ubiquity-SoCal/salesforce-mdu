"""
Audit MDU RT Opps in Contract Negotiations stage.
Per restructure mapping: 'Pending Signature' RE Status -> Contract Negotiations.
So each should have at least one Agreement__c child in Pending Signature
or active IronClad workflow, plus a populated Next_Action__c.
"""
from simple_salesforce import Salesforce
from collections import defaultdict

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

BULK_DATES = {'2026-03-24', '2026-03-31', '2026-04-07', '2026-04-21', '2026-04-25', '2026-04-29'}

rts = sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SobjectType='Opportunity'")
rt_map = {r['DeveloperName']: r['Id'] for r in rts['records']}
MDU_RT = rt_map['MDU']

opps_q = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name,
           Sales_Status__c, Projected_Close_Date__c, CloseDate,
           Next_Action__c, Next_Action_Date__c,
           Notes_Count__c, Agreement_Count__c,
           CreatedDate, LastModifiedDate
    FROM Opportunity
    WHERE StageName = 'Contract Negotiations'
      AND RecordTypeId = '{MDU_RT}'
    ORDER BY Owner.Name, Name
""")
opps = opps_q['records']
print(f"MDU Contract Negotiations Opps: {len(opps)}")
ids = [o['Id'] for o in opps]
if not ids:
    raise SystemExit()
ids_str = "','".join(ids)

# Notes
notes_by_opp = defaultdict(list)
cdl = sf.query_all(f"SELECT LinkedEntityId, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids_str}')")
doc_to_opps = defaultdict(list)
for r in cdl['records']:
    doc_to_opps[r['ContentDocumentId']].append(r['LinkedEntityId'])
if doc_to_opps:
    docs_str = "','".join(doc_to_opps.keys())
    cn = sf.query_all(f"SELECT ContentDocumentId, Title, CreatedDate FROM ContentVersion WHERE ContentDocumentId IN ('{docs_str}') AND IsLatest = TRUE")
    for r in cn['records']:
        d = r['CreatedDate'][:10]
        for opp_id in doc_to_opps[r['ContentDocumentId']]:
            notes_by_opp[opp_id].append({'title': r['Title'], 'date': d})

# Tasks + Events
tasks_by_opp = defaultdict(list)
for r in sf.query_all(f"SELECT WhatId, Subject, CreatedDate, Status FROM Task WHERE WhatId IN ('{ids_str}')")['records']:
    tasks_by_opp[r['WhatId']].append({'subject': r['Subject'], 'created': r['CreatedDate'][:10], 'status': r['Status']})
events_by_opp = defaultdict(list)
for r in sf.query_all(f"SELECT WhatId, Subject, CreatedDate FROM Event WHERE WhatId IN ('{ids_str}')")['records']:
    events_by_opp[r['WhatId']].append({'subject': r['Subject'], 'created': r['CreatedDate'][:10]})

# Agreements
agreements_by_opp = defaultdict(list)
for r in sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c,
           Signed_Date__c, IronClad_Stage__c, IronClad_Contract_Status__c,
           IronClad_Id__c, CreatedDate
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
""")['records']:
    agreements_by_opp[r['Opportunity__c']].append(r)

# Build report
print()
print("=" * 100)
buckets = {'clean': [], 'auto': [], 'review': []}
for o in opps:
    notes = notes_by_opp[o['Id']]
    tasks = tasks_by_opp[o['Id']]
    events = events_by_opp[o['Id']]
    agreements = agreements_by_opp[o['Id']]

    has_next_action = bool(o.get('Next_Action__c'))
    has_pending_agr = any(a.get('Status__c') in ('Pending Signature', 'In Negotiation', 'Out for Signature', 'Drafting') for a in agreements)
    has_active_ic = any(a.get('IronClad_Stage__c') in ('Review', 'Sign', 'review', 'sign') for a in agreements)
    has_signed_agr = any(a.get('Status__c') in ('Signed', 'Active', 'Executed', 'Completed') for a in agreements)

    flags = []
    if not has_next_action:
        flags.append('NO Next_Action')
    if not agreements:
        flags.append('NO Agreement child')
    elif has_signed_agr and not has_pending_agr:
        flags.append('Has SIGNED agreement, no pending — may belong PAL/ROE Complete')
    elif not (has_pending_agr or has_active_ic):
        flags.append(f'Agreement(s) but none Pending Signature ({", ".join(set(a.get("Status__c") or "?" for a in agreements))})')

    notes_2026_nb = [n for n in notes if n['date'].startswith('2026') and n['date'] not in BULK_DATES]
    last_note = max((n['date'] for n in notes), default=None)
    last_task = max((t['created'] for t in tasks), default=None)
    last_event = max((e['created'] for e in events), default=None)
    last_activity = max([d for d in [last_note, last_task, last_event] if d], default=None)

    print(f"\n{o['Name']}")
    print(f"  Id: {o['Id']}  Owner: {o['Owner']['Name']}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}  CloseDate: {o.get('CloseDate')}")
    if o.get('Next_Action__c'):
        print(f"  Next_Action: {o['Next_Action__c']}  ({o.get('Next_Action_Date__c')})")
    else:
        print(f"  Next_Action: <empty>")
    print(f"  Notes total/2026 non-bulk: {len(notes)}/{len(notes_2026_nb)}   Tasks: {len(tasks)}   Events: {len(events)}   Last activity: {last_activity}")
    if agreements:
        for a in agreements:
            print(f"    Agr {a['Name']}  Status={a.get('Status__c')}  Type={a.get('Agreement_Type__c')}  Signed={a.get('Signed_Date__c')}  IC={a.get('IronClad_Stage__c')}/{a.get('IronClad_Contract_Status__c')}  IC_Id={a.get('IronClad_Id__c')}")
    if notes_2026_nb:
        for n in sorted(notes_2026_nb, key=lambda x: x['date'], reverse=True)[:3]:
            print(f"    Note {n['date']}: {n['title']}")
    if flags:
        print(f"  >>> FLAGS: {', '.join(flags)}")
    if 'NO Next_Action' in flags or 'NO Agreement child' in flags or any('SIGNED agreement' in f or 'belong PAL/ROE' in f for f in flags):
        buckets['review'].append(o)
    else:
        buckets['clean'].append(o)

print()
print(f"=== Summary: clean={len(buckets['clean'])}  review={len(buckets['review'])} ===")
