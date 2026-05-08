"""
Backfill Property_Unit__c.Opportunity__c (reverse link) so Unit-side formulas
showing Opp Stage can work.

Today: Opportunity.Property_Unit__c is populated for ~120 Opps (the unit-level
ones), but the corresponding Property_Unit__c.Opportunity__c lookup is empty —
so the cross-object formula `TEXT(Opportunity__r.StageName)` returns blank.

Strategy
========
For every Opp where Property_Unit__c is non-null:
  - Group by target Unit Id
  - When 1 Opp per Unit: set Unit.Opportunity__c = that Opp
  - When 2+ Opps per Unit: pick the most recently modified open one
    (StageName not in 'Closed Lost'/'Closed Won'); fall back to most recently
    modified period
  - Skip Units that already have Opportunity__c set (don't stomp)

Usage:
  python backfill_unit_opportunity_link_2026-04-27.py            # preview
  python backfill_unit_opportunity_link_2026-04-27.py --apply
"""
import sys, io, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

SCRIPT_NAME = 'backfill_unit_opportunity_link_2026-04-27.py'
TS = datetime.now().isoformat(timespec='seconds')
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs')

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

CLOSED_STAGES = {'Closed Lost', 'Closed Won'}

# Pull Opps with Property_Unit__c set
opps = sf.query_all("""
  SELECT Id, Name, StageName, Property_Unit__c, LastModifiedDate, RecordType.DeveloperName
  FROM Opportunity
  WHERE Property_Unit__c != null
""")['records']
print(f"Opps with Property_Unit__c populated: {len(opps)}")

# Pull current Unit state to avoid stomp
unit_ids_in_play = list({o['Property_Unit__c'] for o in opps if o.get('Property_Unit__c')})
ids_csv = "','".join(unit_ids_in_play)
units = sf.query_all(f"SELECT Id, Name, Opportunity__c FROM Property_Unit__c WHERE Id IN ('{ids_csv}')")['records']
unit_state = {u['Id']: u for u in units}
print(f"Distinct Units referenced: {len(unit_ids_in_play)}")

# Group Opps by Unit
opps_by_unit = defaultdict(list)
for o in opps:
    opps_by_unit[o['Property_Unit__c']].append(o)

# Pick best Opp per Unit
def pick_best(opp_list):
    open_opps = [o for o in opp_list if o['StageName'] not in CLOSED_STAGES]
    pool = open_opps if open_opps else opp_list
    return sorted(pool, key=lambda o: o.get('LastModifiedDate', ''), reverse=True)[0]

planned = []
already_filled = 0
for unit_id, opp_list in opps_by_unit.items():
    cur = unit_state.get(unit_id)
    if not cur:
        continue
    if cur.get('Opportunity__c'):
        already_filled += 1
        continue
    best = pick_best(opp_list)
    planned.append({
        'unit_id': unit_id,
        'unit_name': cur['Name'],
        'opp_id': best['Id'],
        'opp_name': best['Name'],
        'opp_stage': best['StageName'],
        'opp_count_on_unit': len(opp_list),
    })

print(f"\nUnits already linked to an Opp: {already_filled}")
print(f"Planned backfills:               {len(planned)}")

# Sample
print("\nFirst 12 planned backfills:")
for p in planned[:12]:
    multi = f"  [+{p['opp_count_on_unit']-1} more Opps]" if p['opp_count_on_unit'] > 1 else ''
    print(f"  {p['unit_name'][:50]:50s} <- {p['opp_name'][:50]:50s} ({p['opp_stage']}){multi}")

# Distribution
from collections import Counter
multi_dist = Counter(p['opp_count_on_unit'] for p in planned)
print(f"\nOpps-per-Unit count distribution among planned:")
for n, c in sorted(multi_dist.items()):
    print(f"  {c:4d} units have {n} Opp(s) (chose most-recent open)")

if not args.apply:
    print(f"\n[Preview only — re-run with --apply to update {len(planned)} Units]")
    sys.exit(0)

# Apply
print("\nApplying...")
audit_rows = []
batch = [{'Id': p['unit_id'], 'Opportunity__c': p['opp_id']} for p in planned]
for i in range(0, len(batch), 200):
    chunk = batch[i:i+200]
    plan_chunk = planned[i:i+200]
    print(f"  Batch {i//200 + 1}: {len(chunk)}")
    results = sf.bulk.Property_Unit__c.update(chunk)
    for j, res in enumerate(results):
        p = plan_chunk[j]
        if res.get('success'):
            audit_rows.append({
                'SF_Id': p['unit_id'], 'Name': p['unit_name'],
                'Field': 'Opportunity__c',
                'Before': '(null)', 'After': p['opp_id'],
                'Source': SCRIPT_NAME, 'Timestamp': TS, 'Action': 'FILL',
                'Note': f"Linked to Opp {p['opp_name']} ({p['opp_stage']}); chosen from {p['opp_count_on_unit']} candidate(s)",
            })
        else:
            print(f"    ⚠ FAIL {p['unit_name']}: {res.get('errors', res)}")

audit_path = AUDIT_DIR / f'unit_opportunity_link_{TS.replace(":","-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id','Name','Field','Before','After','Source','Timestamp','Action','Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f"\n✓ Audit log: {audit_path} ({len(audit_rows)} rows)")
