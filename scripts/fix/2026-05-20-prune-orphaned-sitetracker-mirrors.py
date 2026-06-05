"""
Prune orphaned SiteTracker_Project__c mirror rows from the MAIN org.

An orphan = mirror row whose SiteTracker_Record_Id__c no longer exists in the
SiteTracker org. The sync is upsert-only (never prunes), so deleted/merged
SiteTracker records leave stale mirror rows that can hold false Opportunity
links (the P-005799 case).

Safety:
  - Re-verifies orphan status LIVE at run time (re-pulls both orgs).
  - Writes a full-field rollback snapshot before any delete.
  - Appends every removed row to a permanent running ledger so there is always
    a record of what was removed and when.
  - Dry-run by default; --execute to push.

Deleting the child SiteTracker_Project__c row also removes its Opportunity
lookup (the Opp itself is untouched, it just loses the phantom related-list row).

Usage:
  python 2026-05-20-prune-orphaned-sitetracker-mirrors.py            # dry-run
  python 2026-05-20-prune-orphaned-sitetracker-mirrors.py --execute  # delete
"""
import sys
import csv
import json
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

EXECUTE = '--execute' in sys.argv
SOURCE_LABEL = 'fix/2026-05-20-prune-orphaned-sitetracker-mirrors.py'
REASON = 'Source MDU_Fiber__c record deleted/merged in SiteTracker; orphaned mirror pruned.'

OUT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output")
LEDGER = OUT / "sitetracker-mirror-removal-log.csv"            # permanent running log
SNAP = OUT / "audit_logs" / f"{datetime.now():%Y-%m-%d}-prune-orphaned-st-mirrors-snapshot.json"

LEDGER_COLS = [
    'removed_at', 'st_proj_id', 'name', 'site_name', 'city', 'state',
    'site_status', 'build_status', 'last_synced', 'st_record_id',
    'opportunity_id', 'opportunity_name', 'opportunity_stage',
    'reason', 'source_script',
]

sf_main = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='Hawaiian84',
    security_token='fe2pen6ceQeqGhWXhBeOIjqP',
)


def query_all(sf, soql):
    res = sf.query(soql)
    recs = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        recs.extend(res['records'])
    return recs


print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

# 1. all mirror rows (full field state for snapshot)
mirror = query_all(sf_main,
    "SELECT Id, Name, Site_Name__c, Site_Status__c, Build_Status__c, "
    "Last_Synced__c, SiteTracker_Record_Id__c, Monday_Name__c, City__c, State__c, "
    "MDU_Category__c, PAL_Signed_Date__c, Activation_Forecast__c, Activation_Actual__c, "
    "Opportunity__c, Opportunity__r.Name, Opportunity__r.StageName "
    "FROM SiteTracker_Project__c")
print(f"[1] {len(mirror)} mirror rows in main org")

# 2. live SiteTracker ids by prefix -> object (generic)
prefixes = Counter(r['SiteTracker_Record_Id__c'][:3]
                   for r in mirror if r.get('SiteTracker_Record_Id__c'))
prefix_to_obj = {s['keyPrefix']: s['name']
                 for s in sf_st.describe()['sobjects'] if s.get('keyPrefix') in prefixes}
live_ids = set()
verifiable_prefixes = set()
for prefix, obj in prefix_to_obj.items():
    ids = query_all(sf_st, f"SELECT Id FROM {obj}")
    for x in ids:
        live_ids.add(x['Id'][:15])
    verifiable_prefixes.add(prefix)
    print(f"[2] {obj}: {len(ids)} live records")

# 3. orphans = has source id, prefix verifiable, source id absent from live set
orphans = []
for r in mirror:
    rid = r.get('SiteTracker_Record_Id__c')
    if not rid or rid[:3] not in verifiable_prefixes:
        continue
    if rid[:15] not in live_ids:
        orphans.append(r)
print(f"[3] {len(orphans)} orphaned mirror rows confirmed gone from SiteTracker\n")

linked = [r for r in orphans if r.get('Opportunity__c')]
print("Rows to delete:")
for r in sorted(orphans, key=lambda x: x.get('Last_Synced__c') or ''):
    opp = r.get('Opportunity__r') or {}
    tag = f"-> {opp.get('Name')} [{opp.get('StageName')}]" if r.get('Opportunity__c') else "(no link)"
    print(f"  {r['Name']:>10}  last_sync={str(r.get('Last_Synced__c'))[:10]}  "
          f"{(r.get('Site_Name__c') or '')[:36]:<36} {tag}")
print(f"\n  total: {len(orphans)}  ({len(linked)} drop an Opp link, {len(orphans)-len(linked)} unlinked)")

if not EXECUTE:
    print("\n[INFO] Dry-run. Re-run with --execute to snapshot, log, and delete.")
    sys.exit(0)

# 4. rollback snapshot (full field state)
SNAP.parent.mkdir(parents=True, exist_ok=True)
snap_payload = [{k: v for k, v in r.items() if k != 'attributes'} for r in orphans]
SNAP.write_text(json.dumps(snap_payload, indent=2, default=str), encoding='utf-8')
print(f"\n[SNAPSHOT] {SNAP}")

# 5. append to permanent ledger + delete
new_ledger = not LEDGER.exists()
stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
ok = fail = 0
with LEDGER.open('a', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
    if new_ledger:
        w.writeheader()
    for r in orphans:
        opp = r.get('Opportunity__r') or {}
        entry = {
            'removed_at': stamp,
            'st_proj_id': r['Id'],
            'name': r.get('Name'),
            'site_name': r.get('Site_Name__c'),
            'city': r.get('City__c'),
            'state': r.get('State__c'),
            'site_status': r.get('Site_Status__c'),
            'build_status': r.get('Build_Status__c'),
            'last_synced': r.get('Last_Synced__c'),
            'st_record_id': r.get('SiteTracker_Record_Id__c'),
            'opportunity_id': r.get('Opportunity__c'),
            'opportunity_name': opp.get('Name'),
            'opportunity_stage': opp.get('StageName'),
            'reason': REASON,
            'source_script': SOURCE_LABEL,
        }
        try:
            sf_main.SiteTracker_Project__c.delete(r['Id'])
            w.writerow(entry)
            ok += 1
            print(f"  [DELETED] {r['Name']} {r['Id']}")
        except Exception as e:
            fail += 1
            print(f"  [FAIL] {r['Name']} {r['Id']}: {type(e).__name__}: {str(e)[:120]}")

print(f"\n[RESULT] {ok} deleted, {fail} failed.")
print(f"[LEDGER] {LEDGER}")
