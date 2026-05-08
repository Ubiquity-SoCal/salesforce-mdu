"""
Audit all Engaged-stage Opps (MDU + Business_ROE RTs).
For each, gather: owner, sales_status, projected close, child Agreements,
2026 activity (notes, tasks, events), and last modified.
"""
from simple_salesforce import Salesforce
from collections import defaultdict
from datetime import datetime
import json

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

BULK_DATES = {'2026-03-24', '2026-03-31', '2026-04-07', '2026-04-21', '2026-04-25', '2026-04-29'}

rts = sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SobjectType='Opportunity'")
rt_map = {r['DeveloperName']: r['Id'] for r in rts['records']}
target_rts = [rt_map['MDU'], rt_map['Business_ROE']]

opps_q = sf.query_all(f"""
    SELECT Id, Name, RecordType.DeveloperName, OwnerId, Owner.Name,
           Sales_Status__c, Projected_Close_Date__c, CloseDate,
           Next_Action__c, Next_Action_Date__c,
           Notes_Count__c, Agreement_Count__c,
           CreatedDate, LastModifiedDate,
           Property_Location__c, Property_Location__r.Name,
           Account.Name
    FROM Opportunity
    WHERE StageName = 'Engaged'
      AND RecordTypeId IN ('{target_rts[0]}','{target_rts[1]}')
    ORDER BY Owner.Name, Name
""")
opps = opps_q['records']
print(f"Engaged Opps: {len(opps)}")
ids = [o['Id'] for o in opps]
if not ids:
    raise SystemExit("No Engaged opps found.")

ids_str = "','".join(ids)

# Notes (ContentNote via ContentDocumentLink)
notes_by_opp = defaultdict(list)
cdl = sf.query_all(f"""
    SELECT LinkedEntityId, ContentDocumentId
    FROM ContentDocumentLink
    WHERE LinkedEntityId IN ('{ids_str}')
""")
doc_to_opps = defaultdict(list)
for r in cdl['records']:
    doc_to_opps[r['ContentDocumentId']].append(r['LinkedEntityId'])
if doc_to_opps:
    docs_str = "','".join(doc_to_opps.keys())
    cn = sf.query_all(f"""
        SELECT Id, ContentDocumentId, Title, CreatedDate
        FROM ContentVersion
        WHERE ContentDocumentId IN ('{docs_str}') AND IsLatest = TRUE
    """)
    for r in cn['records']:
        d = r['CreatedDate'][:10]
        for opp_id in doc_to_opps[r['ContentDocumentId']]:
            notes_by_opp[opp_id].append({'title': r['Title'], 'date': d})

# Tasks
tasks_by_opp = defaultdict(list)
tq = sf.query_all(f"""
    SELECT WhatId, Subject, ActivityDate, CreatedDate, Status
    FROM Task
    WHERE WhatId IN ('{ids_str}')
""")
for r in tq['records']:
    tasks_by_opp[r['WhatId']].append({
        'subject': r['Subject'],
        'activity_date': r['ActivityDate'],
        'created': r['CreatedDate'][:10],
        'status': r['Status'],
    })

# Events
events_by_opp = defaultdict(list)
eq = sf.query_all(f"""
    SELECT WhatId, Subject, ActivityDate, CreatedDate
    FROM Event
    WHERE WhatId IN ('{ids_str}')
""")
for r in eq['records']:
    events_by_opp[r['WhatId']].append({
        'subject': r['Subject'],
        'activity_date': r['ActivityDate'],
        'created': r['CreatedDate'][:10],
    })

# Agreements
agreements_by_opp = defaultdict(list)
aq = sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c,
           Signed_Date__c, IronClad_Stage__c, IronClad_Contract_Status__c,
           CreatedDate
    FROM Agreement__c
    WHERE Opportunity__c IN ('{ids_str}')
""")
for r in aq['records']:
    agreements_by_opp[r['Opportunity__c']].append({
        'name': r['Name'],
        'status': r['Status__c'],
        'type': r['Agreement_Type__c'],
        'signed': r['Signed_Date__c'],
        'ic_stage': r['IronClad_Stage__c'],
        'ic_status': r['IronClad_Contract_Status__c'],
    })

# Build report
print()
print("=" * 100)
for o in opps:
    notes = notes_by_opp[o['Id']]
    tasks = tasks_by_opp[o['Id']]
    events = events_by_opp[o['Id']]
    agreements = agreements_by_opp[o['Id']]

    notes_2026 = [n for n in notes if n['date'].startswith('2026') and n['date'] not in BULK_DATES]
    tasks_2026 = [t for t in tasks if t['created'].startswith('2026')]
    events_2026 = [e for e in events if e['created'].startswith('2026')]

    has_recent = bool(notes_2026 or tasks_2026 or events_2026)
    has_agreement = bool(agreements)
    last_note = max((n['date'] for n in notes), default=None)
    last_task = max((t['created'] for t in tasks), default=None)
    last_event = max((e['created'] for e in events), default=None)
    last_activity = max([d for d in [last_note, last_task, last_event] if d], default=None)

    flags = []
    if not has_recent:
        flags.append('NO 2026 ACTIVITY')
    if not o.get('Sales_Status__c'):
        flags.append('NO SALES_STATUS')
    if has_agreement:
        flags.append(f'HAS AGREEMENT ({len(agreements)})')
    if not o.get('Property_Location__c'):
        flags.append('NO PROPERTY_LOCATION')

    rt = (o.get('RecordType') or {}).get('DeveloperName')
    owner = (o.get('Owner') or {}).get('Name')
    pl = (o.get('Property_Location__r') or {}).get('Name')
    acct = (o.get('Account') or {}).get('Name')

    print(f"\n{o['Name']}  [{rt}]")
    print(f"  Id: {o['Id']}  Owner: {owner}")
    print(f"  Account: {acct}  Property_Location: {pl}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}  CloseDate: {o.get('CloseDate')}")
    print(f"  Next_Action: {o.get('Next_Action__c')} ({o.get('Next_Action_Date__c')})")
    print(f"  Notes total/2026 non-bulk: {len(notes)}/{len(notes_2026)}   Tasks: {len(tasks)}/{len(tasks_2026)}   Events: {len(events)}/{len(events_2026)}")
    print(f"  Last activity: {last_activity}   Created: {o['CreatedDate'][:10]}   LastMod: {o['LastModifiedDate'][:10]}")
    if agreements:
        for a in agreements:
            print(f"    Agreement: {a['name']}  Status={a['status']}  Type={a['type']}  Signed={a['signed']}  IC={a['ic_stage']}/{a['ic_status']}")
    if notes_2026:
        for n in notes_2026[-3:]:
            print(f"    Note 2026: {n['date']}  {n['title']}")
    if tasks_2026:
        for t in tasks_2026[-3:]:
            print(f"    Task 2026: {t['created']}  {t['subject']} ({t['status']})")
    if events_2026:
        for e in events_2026[-3:]:
            print(f"    Event 2026: {e['created']}  {e['subject']}")
    if flags:
        print(f"  >>> FLAGS: {', '.join(flags)}")
print()
