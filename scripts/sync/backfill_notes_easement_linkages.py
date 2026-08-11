"""
Retroactively add provenance Notes__c to the 12 IronClad easement Agreement__c records
created earlier today (2026-04-24) via link_ironclad_easements_2026-04-24.py.
"""
import sys, io, json, csv
from datetime import datetime
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
TS = datetime.now().isoformat(timespec='seconds')

with open(r'C:\Users\cass\Work_Projects\IronClad\link_results_2026-04-24.json') as f:
    lr = json.load(f)

audit_rows = []
for c in lr.get('created', []):
    # c has: counterparty, opp, sf_id (Agreement__c Id)
    note = (
        f"AUTO-LINKED via IronClad Easement Linker on 2026-04-24.\n"
        f"Match method: counterparty_name_manual_review  (confidence: HIGH — approved by Koa)\n"
        f"IronClad Counterparty: {c['counterparty']}\n"
        f"Matched SF Opp: {c['opp']}\n"
        f"Source: Easement Agreement from 4/24 IronClad import (88 new records); 12 MDU matches identified, all approved.\n"
        f"Recommendation: human review to confirm match quality."
    )
    try:
        sf.Agreement__c.update(c['sf_id'], {'Notes__c': note})
        audit_rows.append([c['sf_id'], c.get('opp','?'), 'Notes__c',
                           '(blank)', note[:120]+'...',
                           'backfill_notes_easement_linkages.py', TS, 'update'])
        print(f"  [OK]  {c['opp'][:40]:<40}  ({c['sf_id']})")
    except Exception as e:
        print(f"  [FAIL] {c['opp']}: {e}")

# Append to the easement linkage audit log
audit_path = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\ironclad_easement_linkages_2026-04-24.csv')
# Append rows
with audit_path.open('a', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    for row in audit_rows: w.writerow(row)
print(f"\nAppended {len(audit_rows)} note-backfill rows to {audit_path.name}")
