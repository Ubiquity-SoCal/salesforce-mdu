"""
Full audit of MDU RT Opps in Prospecting stage.
Classify each by: Note dates, Tasks/Events count, Projected Close Date, Next_Action__c.
Flag bulk-sync-only Opps that should revert to Prospects.
"""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter
import csv

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

# Bulk-import note dates (volume spikes confirmed in earlier histogram)
BULK_DATES = {'2026-03-24', '2026-03-31', '2026-04-07', '2026-04-21', '2026-04-25'}

# Get MDU RecordType Id
rt = sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")
MDU_RT = rt['records'][0]['Id']

opps_q = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name, Sales_Status__c, Projected_Close_Date__c,
           Next_Action__c, Next_Action_Date__c, CreatedDate, LastModifiedDate, Notes_Count__c
    FROM Opportunity
    WHERE StageName = 'Prospecting' AND RecordTypeId = '{MDU_RT}'
    ORDER BY Owner.Name, Name
""")
opps = opps_q['records']
print(f"MDU Prospecting Opps: {len(opps)}")
ids = [o['Id'] for o in opps]

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# Notes
note_dates_by_opp = defaultdict(list)
for chunk in chunked(ids, 100):
    in_clause = "','".join(chunk)
    cdl = sf.query_all(f"SELECT LinkedEntityId, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{in_clause}')")
    cd_to_opp = defaultdict(list)
    for r in cdl['records']:
        cd_to_opp[r['ContentDocumentId']].append(r['LinkedEntityId'])
    docs = list(cd_to_opp.keys())
    for dchunk in chunked(docs, 200):
        din = "','".join(dchunk)
        cv = sf.query_all(f"SELECT ContentDocumentId, CreatedDate, FileType FROM ContentVersion WHERE ContentDocumentId IN ('{din}') AND IsLatest = true")
        for v in cv['records']:
            if v['FileType'] != 'SNOTE':
                continue
            d = v['CreatedDate'][:10]
            for opp_id in cd_to_opp.get(v['ContentDocumentId'], []):
                note_dates_by_opp[opp_id].append(d)

# Tasks
task_count_by_opp = defaultdict(int)
for chunk in chunked(ids, 200):
    in_clause = "','".join(chunk)
    tasks = sf.query_all(f"SELECT WhatId FROM Task WHERE WhatId IN ('{in_clause}') AND CreatedDate >= 2026-01-01T00:00:00Z")
    for t in tasks['records']:
        task_count_by_opp[t['WhatId']] += 1

# Events
event_count_by_opp = defaultdict(int)
for chunk in chunked(ids, 200):
    in_clause = "','".join(chunk)
    events = sf.query_all(f"SELECT WhatId FROM Event WHERE WhatId IN ('{in_clause}') AND CreatedDate >= 2026-01-01T00:00:00Z")
    for e in events['records']:
        event_count_by_opp[e['WhatId']] += 1

# Classify
keep_reasons_by_opp = {}  # opp_id -> list of reasons
for o in opps:
    oid = o['Id']
    reasons = []
    note_dates = note_dates_by_opp.get(oid, [])
    real_dates = sorted({d for d in note_dates if d.startswith('2026') and d not in BULK_DATES})
    tasks = task_count_by_opp.get(oid, 0)
    events = event_count_by_opp.get(oid, 0)
    next_action = o.get('Next_Action__c') or ''
    close_date = o.get('Projected_Close_Date__c')

    if 'Ting Exclusive Priority' in next_action:
        reasons.append(f"Ting Exclusive Priority")
    if real_dates:
        reasons.append(f"real note dates: {','.join(real_dates)}")
    if tasks:
        reasons.append(f"{tasks} task(s) in 2026")
    if events:
        reasons.append(f"{events} event(s) in 2026")
    if close_date:
        reasons.append(f"close date: {close_date}")
    keep_reasons_by_opp[oid] = reasons

# Build per-owner summary
by_owner = defaultdict(lambda: {'keep': [], 'revert': []})
for o in opps:
    oid = o['Id']
    bucket = 'keep' if keep_reasons_by_opp[oid] else 'revert'
    by_owner[o['Owner']['Name']][bucket].append(o)

print(f"\n=== Summary by Owner ===")
print(f"{'Owner':30s} {'Keep':>6s} {'Revert':>8s} {'Total':>7s}")
for owner, buckets in sorted(by_owner.items()):
    k = len(buckets['keep'])
    r = len(buckets['revert'])
    print(f"{owner:30s} {k:6d} {r:8d} {k+r:7d}")

total_keep = sum(len(b['keep']) for b in by_owner.values())
total_revert = sum(len(b['revert']) for b in by_owner.values())
print(f"\nTotal keep: {total_keep}")
print(f"Total revert: {total_revert}")

# Detail: list all KEEP records with reasons
print(f"\n=== KEEP records (real signal exists) ===")
for o in opps:
    if not keep_reasons_by_opp[o['Id']]:
        continue
    reasons = '; '.join(keep_reasons_by_opp[o['Id']])
    print(f"  [{o['Owner']['Name'][:20]:20s}] {o['Name'][:50]:50s} -> {reasons}")

# Write CSV for full review
with open('mdu_prospecting_audit.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Verdict', 'Owner', 'Opp_Id', 'Opp_Name', 'Sales_Status', 'Next_Action', 'Close_Date',
                'Note_Dates', 'Real_Note_Dates', 'Tasks_2026', 'Events_2026', 'Keep_Reasons'])
    for o in opps:
        oid = o['Id']
        note_dates = sorted(set(note_dates_by_opp.get(oid, [])))
        real_dates = sorted({d for d in note_dates if d not in BULK_DATES})
        verdict = 'KEEP' if keep_reasons_by_opp[oid] else 'REVERT'
        w.writerow([
            verdict, o['Owner']['Name'], oid, o['Name'],
            o.get('Sales_Status__c') or '',
            o.get('Next_Action__c') or '',
            o.get('Projected_Close_Date__c') or '',
            ','.join(note_dates), ','.join(real_dates),
            task_count_by_opp.get(oid, 0), event_count_by_opp.get(oid, 0),
            '; '.join(keep_reasons_by_opp[oid]),
        ])

print(f"\nWrote mdu_prospecting_audit.csv")
