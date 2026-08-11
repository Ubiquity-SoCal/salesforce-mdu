"""
Fix Status__c on the 16 Business_ROE Agreement__c records created by the
IronClad bulk linker on 2026-04-27.

The linker defaulted everything to 'Review' because its Status logic only
mapped IC.contract_status='active' or IC.stage='completed' to 'Completed'.
Better mapping based on the actual data:

  IC.contract_status = 'evergreen'  -> Completed   (active/ongoing contract)
  IC.contract_status = 'active'     -> Completed
  IC.stage = 'cancelled'             -> Cancelled
  IC.stage = 'completed'             -> Completed
  IC.stage = 'sign'                  -> Sign
  IC.stage = 'review'                -> Review (no change)
  otherwise                          -> Review (no change)

Usage:
  python fix_business_roe_agreement_status_2026-04-27.py            # preview
  python fix_business_roe_agreement_status_2026-04-27.py --apply
"""
import sys, io, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

SCRIPT_NAME = 'fix_business_roe_agreement_status_2026-04-27.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])


def derive_status(ic_contract, ic_stage, current):
    if ic_contract in ('evergreen', 'active'):
        return 'Completed'
    if ic_stage == 'completed':
        return 'Completed'
    if ic_stage == 'cancelled':
        return 'Cancelled'
    if ic_stage == 'sign':
        return 'Sign'
    return current  # leave alone


ag = sf.query_all("""
  SELECT Id, Name, Status__c, Opportunity__r.Name,
         IronClad_Record__r.Contract_Status__c,
         IronClad_Record__r.Stage_IC__c
  FROM Agreement__c
  WHERE Opportunity__r.RecordType.DeveloperName='Business_ROE'
""")['records']

planned = []
for a in ag:
    ic = a.get('IronClad_Record__r') or {}
    new_status = derive_status(ic.get('Contract_Status__c'), ic.get('Stage_IC__c'), a.get('Status__c'))
    if new_status and new_status != a.get('Status__c'):
        planned.append({
            'Id': a['Id'],
            'Opp': (a.get('Opportunity__r') or {}).get('Name'),
            'before': a.get('Status__c'),
            'after': new_status,
            'ic_contract': ic.get('Contract_Status__c'),
            'ic_stage': ic.get('Stage_IC__c'),
        })

print(f"Total Business_ROE Agreement__c records: {len(ag)}")
print(f"Planned Status updates:                  {len(planned)}")
print()
print(f"{'Before':10s} {'After':10s} {'IC contract':12s} {'IC stage':12s} Opp")
for p in planned:
    print(f"  {p['before']:10s} -> {p['after']:10s} {p['ic_contract'] or '(null)':12s} {p['ic_stage'] or '(null)':12s} {p['Opp']}")

if not args.apply:
    print(f"\n[Preview only — re-run with --apply to update {len(planned)} records]")
    sys.exit(0)

print("\nApplying...")
audit_rows = []
batch = [{'Id': p['Id'], 'Status__c': p['after']} for p in planned]
results = sf.bulk.Agreement__c.update(batch)
for j, res in enumerate(results):
    p = planned[j]
    if res.get('success'):
        audit_rows.append({
            'SF_Id': p['Id'], 'Name': p['Opp'], 'Field': 'Status__c',
            'Before': p['before'], 'After': p['after'],
            'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'UPDATE',
            'Note': f"IC.contract={p['ic_contract']} IC.stage={p['ic_stage']}",
        })
    else:
        print(f"  FAIL: {p['Opp']} — {res.get('errors', res)}")

audit_path = AUDIT_DIR / f'business_roe_agreement_status_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\n✓ Audit log: {audit_path} ({len(audit_rows)} rows)")
