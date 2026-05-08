"""
Check SiteTracker -> SF sync health:
  - Last_Synced__c freshness on SiteTracker_Project__c records
  - Count of records by sync age bucket
"""
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC'
)

print("[INFO] Querying SiteTracker_Project__c records...")
res = sf.query("""
    SELECT Id, Name, Last_Synced__c, Site_Status__c, Build_Status__c, Opportunity__c
    FROM SiteTracker_Project__c
""")
records = res['records']
while not res['done']:
    res = sf.query_more(res['nextRecordsUrl'], True)
    records.extend(res['records'])

print(f"[INFO] {len(records)} SiteTracker_Project__c records total")

now = datetime.now(timezone.utc)
buckets = Counter()
linked = 0
unlinked = 0
last_synced_max = None
last_synced_min = None

for r in records:
    if r.get('Opportunity__c'):
        linked += 1
    else:
        unlinked += 1
    ls = r.get('Last_Synced__c')
    if not ls:
        buckets['Never synced'] += 1
        continue
    dt = datetime.fromisoformat(ls.replace('Z', '+00:00'))
    age = now - dt
    if last_synced_max is None or dt > last_synced_max:
        last_synced_max = dt
    if last_synced_min is None or dt < last_synced_min:
        last_synced_min = dt
    if age <= timedelta(hours=26):
        buckets['<= 26h (healthy)'] += 1
    elif age <= timedelta(days=2):
        buckets['1-2 days'] += 1
    elif age <= timedelta(days=7):
        buckets['2-7 days'] += 1
    elif age <= timedelta(days=30):
        buckets['7-30 days'] += 1
    else:
        buckets['> 30 days (stale)'] += 1

print(f"\nLinked to Opp:     {linked}")
print(f"Unlinked:          {unlinked}")
print(f"Newest Last_Synced: {last_synced_max}")
print(f"Oldest Last_Synced: {last_synced_min}")
print()
print("Sync age buckets:")
order = ['<= 26h (healthy)', '1-2 days', '2-7 days', '7-30 days', '> 30 days (stale)', 'Never synced']
for k in order:
    if buckets.get(k):
        print(f"  {k:25s} {buckets[k]}")
