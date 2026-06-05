import sys
import csv
import json
from pathlib import Path
from simple_salesforce import Salesforce
from datetime import datetime, timezone

# Force unbuffered output so SSE receives lines immediately
sys.stdout.reconfigure(line_buffering=True)

# Connect to both orgs
print("[INFO] Connecting to main Salesforce org...")
sf_main = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)

print("[INFO] Connecting to SiteTracker org...")
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='Hawaiian84',
    security_token='fe2pen6ceQeqGhWXhBeOIjqP'
)

# Step 1: Pull all MDU Fiber records from SiteTracker
# Cancelled is INCLUDED (filter removed 2026-05-26) so the SF mirror covers
# cancelled builds too, which lets the link pass match Opps whose ST projects
# were cancelled. Downstream consumers must check Site_Status__c if they want
# active-only views.
print("[INFO] Pulling MDU Fiber data from SiteTracker...")
query = """SELECT Id, Name,
    Project__r.sitetracker__Site__r.Name,
    Project__r.sitetracker__Site__r.Monday_com_name__c,
    Project__r.sitetracker__Site__r.sitetracker__City__c,
    Project__r.sitetracker__Site__r.sitetracker__State__c,
    Project__r.sitetracker__Site__r.sitetracker__Site_Status__c,
    Project__r.sitetracker__Site__r.MDU_Site_Category__c,
    MDU_Build_Status__c,
    MDU_Activation_F__c,
    MDU_Activation_A__c,
    Premise_Access_License_PAL_A__c
    FROM MDU_Fiber__c
    WHERE Project__r.sitetracker__Site__r.sitetracker__Site_Type__c = 'MDU'
    AND MDU_Build_Status__c != null
    ORDER BY Name"""

st_records = []
result = sf_st.query(query)
st_records.extend(result['records'])
while not result['done']:
    result = sf_st.query_more(result['nextRecordsUrl'], True)
    st_records.extend(result['records'])

print(f"[INFO] Pulled {len(st_records)} MDU Fiber records from SiteTracker")

# Step 2: Build records for upsert
now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
to_upsert = []

for r in st_records:
    site = (r.get('Project__r') or {}).get('sitetracker__Site__r') or {}
    monday_name = site.get('Monday_com_name__c') or ''
    site_name = site.get('Name') or ''

    record = {
        'Name': r['Name'],
        'Site_Name__c': site_name,
        'Monday_Name__c': monday_name or site_name,
        'City__c': site.get('sitetracker__City__c'),
        'State__c': site.get('sitetracker__State__c'),
        'Site_Status__c': site.get('sitetracker__Site_Status__c'),
        'Build_Status__c': r.get('MDU_Build_Status__c'),
        'PAL_Signed_Date__c': r.get('Premise_Access_License_PAL_A__c'),
        'Activation_Forecast__c': r.get('MDU_Activation_F__c'),
        'Activation_Actual__c': r.get('MDU_Activation_A__c'),
        'MDU_Category__c': site.get('MDU_Site_Category__c'),
        'SiteTracker_Record_Id__c': r['Id'],
        'Last_Synced__c': now_str,
    }
    to_upsert.append(record)

print(f"[INFO] Total to upsert: {len(to_upsert)}")

# Step 3: Upsert into main org using SiteTracker_Record_Id__c as external ID
# Does NOT touch Opportunity__c — that link is managed manually in SF
print("[INFO] Upserting into main Salesforce org...")
total = len(to_upsert)
created_count = 0
updated_count = 0
error_count = 0

for i, rec in enumerate(to_upsert):
    st_id = rec.pop('SiteTracker_Record_Id__c')
    try:
        result = sf_main.SiteTracker_Project__c.upsert(
            f"SiteTracker_Record_Id__c/{st_id}", rec
        )
        if isinstance(result, int):
            updated_count += 1
        else:
            created_count += 1
    except Exception as e:
        error_count += 1
        print(f"[ERROR] {rec.get('Name', 'unknown')} - {e}")

    if (i + 1) % 25 == 0 or (i + 1) == total:
        print(f"[PROGRESS] {i + 1}/{total}")

if error_count > 0:
    print(f"[ERROR] Completed with {error_count} errors. {created_count} added, {updated_count} updated, {error_count} failed")
else:
    print(f"[SUCCESS] Done! {created_count} added, {updated_count} updated, 0 errors")

# ---------------------------------------------------------------------------
# Step 4: Prune orphaned mirror rows
#
# An orphan = a SiteTracker_Project__c whose SiteTracker_Record_Id__c no longer
# exists in the SiteTracker org at all (hard-deleted / merged). The upsert above
# never removes rows, so without this step deleted SiteTracker records linger as
# stale mirrors and can hold false Opportunity links (the P-005799 case).
#
# We diff against the UNFILTERED MDU_Fiber__c id set (not the active-sync filter)
# so records that are merely Cancelled / missing build status are NOT pruned --
# they still exist in SiteTracker, they just fall out of the active sync. Only
# true deletes are removed.
#
# Safety: skip the prune if the live id set comes back empty, or if the orphan
# count is implausibly large. Guards against a partial / failed SiteTracker query
# making every mirror row look orphaned and nuking the whole table.
# ---------------------------------------------------------------------------
print("[INFO] Prune step: checking for orphaned mirror rows...")

PRUNE_ABORT_COUNT = 100        # never auto-delete more than this in one run
PRUNE_ABORT_FRACTION = 0.25    # ...or more than 25% of the mirror

# Full, unfiltered set of live SiteTracker record ids (15-char normalized)
live_ids = set()
_r = sf_st.query("SELECT Id FROM MDU_Fiber__c")
live_ids.update(x['Id'][:15] for x in _r['records'])
while not _r['done']:
    _r = sf_st.query_more(_r['nextRecordsUrl'], True)
    live_ids.update(x['Id'][:15] for x in _r['records'])
print(f"[INFO]   {len(live_ids)} live MDU_Fiber__c ids in SiteTracker")

# All mirror rows
mirror = []
_r = sf_main.query(
    "SELECT Id, Name, Site_Name__c, City__c, State__c, Site_Status__c, "
    "Build_Status__c, Last_Synced__c, SiteTracker_Record_Id__c, "
    "Opportunity__c, Opportunity__r.Name, Opportunity__r.StageName "
    "FROM SiteTracker_Project__c"
)
mirror.extend(_r['records'])
while not _r['done']:
    _r = sf_main.query_more(_r['nextRecordsUrl'], True)
    mirror.extend(_r['records'])

orphans = [m for m in mirror
           if m.get('SiteTracker_Record_Id__c')
           and m['SiteTracker_Record_Id__c'][:15] not in live_ids]

if not live_ids:
    print("[WARN]   SiteTracker returned 0 live ids; skipping prune (safety).")
elif len(orphans) > PRUNE_ABORT_COUNT or len(orphans) > len(mirror) * PRUNE_ABORT_FRACTION:
    print(f"[WARN]   {len(orphans)} orphans exceeds safety cap "
          f"(>{PRUNE_ABORT_COUNT} or >{int(PRUNE_ABORT_FRACTION * 100)}% of {len(mirror)}); "
          f"skipping prune. Investigate before deleting.")
elif not orphans:
    print("[INFO]   No orphans. Mirror is clean.")
else:
    # Rollback snapshot + permanent append-only ledger (relative to repo root)
    base = Path(__file__).resolve().parents[1] / "data" / "output"
    (base / "audit_logs").mkdir(parents=True, exist_ok=True)
    ledger = base / "sitetracker-mirror-removal-log.csv"
    snap = base / "audit_logs" / f"{datetime.now():%Y-%m-%d_%H%M%S}-sync-prune-snapshot.json"
    snap.write_text(
        json.dumps([{k: v for k, v in m.items() if k != 'attributes'} for m in orphans],
                   indent=2, default=str),
        encoding='utf-8',
    )

    cols = ['removed_at', 'st_proj_id', 'name', 'site_name', 'city', 'state',
            'site_status', 'build_status', 'last_synced', 'st_record_id',
            'opportunity_id', 'opportunity_name', 'opportunity_stage',
            'reason', 'source_script']
    new_ledger = not ledger.exists()
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    reason = 'Source MDU_Fiber__c deleted/merged in SiteTracker; orphaned mirror pruned by daily sync.'
    pruned = 0
    with ledger.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new_ledger:
            w.writeheader()
        for m in orphans:
            opp = m.get('Opportunity__r') or {}
            try:
                sf_main.SiteTracker_Project__c.delete(m['Id'])
                w.writerow({
                    'removed_at': stamp, 'st_proj_id': m['Id'], 'name': m.get('Name'),
                    'site_name': m.get('Site_Name__c'), 'city': m.get('City__c'),
                    'state': m.get('State__c'), 'site_status': m.get('Site_Status__c'),
                    'build_status': m.get('Build_Status__c'),
                    'last_synced': m.get('Last_Synced__c'),
                    'st_record_id': m.get('SiteTracker_Record_Id__c'),
                    'opportunity_id': m.get('Opportunity__c'),
                    'opportunity_name': opp.get('Name'),
                    'opportunity_stage': opp.get('StageName'),
                    'reason': reason, 'source_script': 'scripts/sync_sitetracker.py',
                })
                pruned += 1
                print(f"[PRUNE]  removed {m.get('Name')} "
                      f"({(m.get('Site_Name__c') or '')[:40]}) link={opp.get('Name') or '-'}")
            except Exception as e:
                print(f"[ERROR]  prune {m.get('Name')}: {type(e).__name__}: {str(e)[:120]}")
    print(f"[INFO]   pruned {pruned} orphan(s). Ledger: {ledger}")
