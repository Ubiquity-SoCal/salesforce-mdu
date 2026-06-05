"""
Find orphaned SiteTracker_Project__c mirror rows (READ-ONLY).

An orphan = a mirror row in the MAIN org whose SiteTracker_Record_Id__c no
longer exists in the SiteTracker org. The sync is upsert-only and never prunes,
so when SiteTracker deletes/merges a record its mirror lingers and can keep an
Opportunity falsely "linked" (this is the P-005799 case).

Method: pull all mirror rows, group their source IDs by key prefix -> object,
bulk-pull every live Id for those objects from SiteTracker, then diff.

Output: data/output/orphaned_sitetracker_mirrors_<date>.csv + console summary.
No writes to either org.
"""
import sys
import csv
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

OUT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output") / \
    f"orphaned_sitetracker_mirrors_{datetime.now():%Y-%m-%d}.csv"

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


# ---- 1. all mirror rows ----
print("[1] Pulling all SiteTracker_Project__c mirror rows (main org)...")
mirror = query_all(sf_main,
    "SELECT Id, Name, Site_Name__c, Site_Status__c, Build_Status__c, "
    "Last_Synced__c, SiteTracker_Record_Id__c, City__c, State__c, "
    "Opportunity__c, Opportunity__r.Name, Opportunity__r.StageName "
    "FROM SiteTracker_Project__c")
print(f"    {len(mirror)} mirror rows")

# ---- 2. map source-id prefixes -> SiteTracker objects ----
prefix_counts = Counter()
for r in mirror:
    rid = r.get('SiteTracker_Record_Id__c')
    if rid:
        prefix_counts[rid[:3]] += 1
print(f"[2] Source-id prefixes in mirror: {dict(prefix_counts)}")

prefix_to_obj = {}
for s in sf_st.describe()['sobjects']:
    if s.get('keyPrefix') in prefix_counts:
        prefix_to_obj[s['keyPrefix']] = s['name']
print(f"    prefix -> object: {prefix_to_obj}")

# ---- 3. bulk-pull live ids for each source object ----
live_ids = set()
unverifiable_prefixes = set()
for prefix, obj in prefix_to_obj.items():
    try:
        ids = query_all(sf_st, f"SELECT Id FROM {obj}")
        for x in ids:
            live_ids.add(x['Id'][:15])  # normalize to 15-char
        print(f"[3] {obj}: {len(ids)} live records")
    except Exception as e:
        unverifiable_prefixes.add(prefix)
        print(f"[3] {obj}: ERROR {type(e).__name__}: {str(e)[:100]}")
for p in prefix_counts:
    if p not in prefix_to_obj:
        unverifiable_prefixes.add(p)
        print(f"[3] prefix {p}: no object found in describe (unverifiable)")

# ---- 4. classify ----
def classify(r):
    rid = r.get('SiteTracker_Record_Id__c')
    if not rid:
        return 'NO_SOURCE_ID'
    if rid[:3] in unverifiable_prefixes:
        return 'UNVERIFIABLE'
    return 'LIVE' if rid[:15] in live_ids else 'ORPHAN'

rows = []
buckets = Counter()
orphan_linked = 0
for r in mirror:
    c = classify(r)
    buckets[c] += 1
    opp = r.get('Opportunity__r') or {}
    if c == 'ORPHAN' and r.get('Opportunity__c'):
        orphan_linked += 1
    rows.append({
        'classification': c,
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
    })

# ---- 5. report ----
print("\n=== Summary ===")
for k in ['LIVE', 'ORPHAN', 'NO_SOURCE_ID', 'UNVERIFIABLE']:
    if buckets.get(k):
        print(f"  {k:14s} {buckets[k]}")
print(f"  -> orphans that still hold an Opportunity link: {orphan_linked}")

print("\n=== ORPHANS linked to an Opportunity (the real problem) ===")
for r in sorted([x for x in rows if x['classification'] == 'ORPHAN' and x['opportunity_id']],
                key=lambda x: x['last_synced'] or ''):
    print(f"  {r['name']:>10}  last_sync={str(r['last_synced'])[:10]}  "
          f"{(r['site_name'] or '')[:34]:<34} -> {r['opportunity_name']} [{r['opportunity_stage']}]")

orphans_unlinked = [x for x in rows if x['classification'] == 'ORPHAN' and not x['opportunity_id']]
print(f"\n=== ORPHANS with no Opp link: {len(orphans_unlinked)} (cleanup-only, no false link) ===")

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"\n[OUT] {OUT}")
