"""Audit MDU RT Opps in On Hold stage.
Per methodology: Hold_Reason__c required (validation rule). Verify hold isn't stale.
Group by Hold_Reason. Flag legacy records missing Hold_Reason. Flag stale (no recent activity)."""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter
from datetime import datetime, timezone

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']

# Detect Hold_Reason field name
desc = sf.Opportunity.describe()
opp_fields = {f['name'] for f in desc['fields']}
hold_reason_fld = next((f for f in ('Hold_Reason__c','OnHoldReason__c','Hold_Reason_c__c') if f in opp_fields), None)
on_hold_date_fld = next((f for f in ('Off_Hold_Date__c','On_Hold_Date__c','OnHold_Date__c') if f in opp_fields), None)

select_fields = ['Id','Name','OwnerId','Owner.Name','Sales_Status__c',
                 'Projected_Close_Date__c','CloseDate','Next_Action__c','Next_Action_Date__c',
                 'Notes_Count__c','Agreement_Count__c','CreatedDate','LastModifiedDate']
if hold_reason_fld:
    select_fields.append(hold_reason_fld)
if on_hold_date_fld:
    select_fields.append(on_hold_date_fld)

opps = sf.query_all(f"""
    SELECT {','.join(select_fields)}
    FROM Opportunity
    WHERE StageName = 'On Hold' AND RecordTypeId = '{rt}'
    ORDER BY Owner.Name, Name
""")['records']
print(f"MDU On Hold Opps: {len(opps)}")
print(f"Hold reason field: {hold_reason_fld}")
print(f"Off-hold date field: {on_hold_date_fld}")

ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)

# Pull most recent Note title for each Opp
note_by_opp = defaultdict(list)
try:
    cdl = sf.query_all(f"""
        SELECT LinkedEntityId, ContentDocumentId, ContentDocument.Title,
               ContentDocument.LatestPublishedVersion.LastModifiedDate,
               ContentDocument.LatestPublishedVersion.FileType
        FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids_str}')
    """)
    for r in cdl['records']:
        note_by_opp[r['LinkedEntityId']].append({
            'Title': r['ContentDocument']['Title'],
            'LastModified': r['ContentDocument']['LatestPublishedVersion']['LastModifiedDate'],
            'FileType': r['ContentDocument']['LatestPublishedVersion']['FileType'],
        })
except Exception as e:
    print(f"Note pull skipped: {e}")

# Pull most recent Tasks/Events
last_activity_by_opp = {}
try:
    tasks = sf.query_all(f"""
        SELECT WhatId, MAX(LastModifiedDate) lastMod
        FROM Task
        WHERE WhatId IN ('{ids_str}')
        GROUP BY WhatId
    """)
    for r in tasks['records']:
        last_activity_by_opp[r['WhatId']] = r['lastMod']
except Exception as e:
    print(f"Task aggregate skipped: {e}")

# 3-signal stays the same; for On Hold we adapt: a populated Hold_Reason is the *required* signal
# "Stale" = no Note OR Task in 2025-2026 + no Next_Action + no Projected_Close_Date

OWNERS_INACTIVE = {'Chuck McNeely'}
THIS_YEAR = 2026
PRIOR_YEAR = 2025

def parse_iso(s):
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None

def is_recent(iso_str):
    d = parse_iso(iso_str)
    if not d: return False
    return d.year >= PRIOR_YEAR

reason_counts = Counter()
owner_counts = Counter()
no_reason = []
stale = []        # has reason but no signal + no recent activity
inactive_owner = []
all_holds = []

for o in opps:
    owner = o['Owner']['Name']
    owner_counts[owner] += 1
    reason = o.get(hold_reason_fld) if hold_reason_fld else None
    reason_counts[reason or '(blank)'] += 1

    notes = note_by_opp.get(o['Id'], [])
    last_note = max((n['LastModified'] for n in notes), default=None)
    last_task = last_activity_by_opp.get(o['Id'])
    last_act = max((d for d in (last_note, last_task, o.get('LastModifiedDate')) if d), default=None)

    has_signal = bool(o.get('Next_Action__c') or o.get('Projected_Close_Date__c'))
    has_recent_activity = is_recent(last_note) or is_recent(last_task)

    bucket = 'clean'
    if not reason:
        bucket = 'no_reason'
        no_reason.append((o, last_act, notes))
    elif not has_signal and not has_recent_activity:
        bucket = 'stale'
        stale.append((o, reason, last_act, notes))
    if owner in OWNERS_INACTIVE:
        inactive_owner.append((o, reason, last_act))

    all_holds.append({
        'Id': o['Id'], 'Name': o['Name'], 'Owner': owner,
        'Reason': reason, 'Last_Activity': last_act, 'Bucket': bucket,
        'Next_Action': o.get('Next_Action__c'),
        'Projected': o.get('Projected_Close_Date__c'),
    })

print()
print(f"Owner distribution:")
for owner, n in owner_counts.most_common():
    print(f"  {owner}: {n}")

print()
print(f"Hold_Reason distribution:")
for reason, n in reason_counts.most_common():
    print(f"  {reason!r}: {n}")

print()
print(f"NO Hold_Reason: {len(no_reason)}")
print(f"STALE (has reason, no signal, no 2025/2026 activity): {len(stale)}")
print(f"Owned by inactive (Chuck McNeely): {len(inactive_owner)}")

print()
print("=" * 100)
print(f"NO HOLD REASON — {len(no_reason)}")
print("=" * 100)
for o, last_act, notes in no_reason[:50]:
    print(f"  {o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}  LastAct={last_act}  Notes={len(notes)}")
if len(no_reason) > 50:
    print(f"  ... ({len(no_reason)-50} more)")

print()
print("=" * 100)
print(f"STALE HOLDS BY REASON — {len(stale)}")
print("=" * 100)
stale_by_reason = defaultdict(list)
for o, reason, last_act, notes in stale:
    stale_by_reason[reason].append((o, last_act, notes))
for reason, items in sorted(stale_by_reason.items(), key=lambda x: -len(x[1])):
    print(f"\n{reason} — {len(items)}")
    by_owner = defaultdict(list)
    for o, last_act, notes in items:
        by_owner[o['Owner']['Name']].append((o, last_act))
    for owner, sub in sorted(by_owner.items(), key=lambda x: -len(x[1])):
        print(f"  [{owner}] {len(sub)}")

print()
print("=" * 100)
print(f"INACTIVE OWNER (Chuck McNeely) — {len(inactive_owner)}")
print("=" * 100)
for o, reason, last_act in inactive_owner[:50]:
    print(f"  {o['Name']}  Reason={reason!r}  LastAct={last_act}  Id={o['Id']}")

# Save full audit CSV
import csv

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

with open('audit_logs/stage_audit_on_hold_2026-05-04.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['Id','Name','Owner','Reason','Last_Activity','Bucket','Next_Action','Projected'])
    w.writeheader()
    for r in all_holds:
        w.writerow(r)
print()
print(f"Saved CSV: audit_logs/stage_audit_on_hold_2026-05-04.csv ({len(all_holds)} rows)")
