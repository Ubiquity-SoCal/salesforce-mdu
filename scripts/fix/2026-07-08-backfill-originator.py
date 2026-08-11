"""One-time backfill: set Opportunity.Originator__c = current OwnerId for existing opps.

Snapshot of who originated each opp, frozen from here on (reassigning Owner will NOT
change Originator). Only User-owned opps are set; queue-owned and already-populated ones
are skipped. New opps stay blank (no auto-populate, per Koa 2026-07-08).

Writes a rollback CSV (every Id set was previously blank -> revert = clear) and an audit
log row per change, per the standard SF batch-change audit pattern. Uses the Bulk API.

    python 2026-07-08-backfill-originator.py            # dry run (counts only)
    python 2026-07-08-backfill-originator.py --apply     # write

Target org: fun-power-747 (PRODUCTION).
"""
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "output"
AUDIT = OUT / "audit_logs"
APPLY = "--apply" in sys.argv
SOURCE = "2026-07-08-backfill-originator.py"

creds = {}
for line in open(ROOT / "api" / "Salesforce_Credentials.txt", encoding="utf-8"):
    if ":" in line:
        k, v = line.split(":", 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds["Username"], password=creds["Password"],
                security_token=creds["Security Token"])

# Every open+closed opp that has no Originator yet. Owner.Type tells User vs Queue.
rows = sf.query_all("SELECT Id, Name, OwnerId FROM Opportunity WHERE Originator__c = null")["records"]
user_owned = [r for r in rows if r["OwnerId"].startswith("005")]
queue_owned = [r for r in rows if not r["OwnerId"].startswith("005")]
print(f"Opps with blank Originator: {len(rows)}")
print(f"  User-owned (will set):    {len(user_owned)}")
print(f"  Queue-owned (skipped):    {len(queue_owned)}")

if not APPLY:
    print("\nDry run. Re-run with --apply to write.")
    sys.exit(0)

OUT.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%dT%H%M%S")
now = datetime.now().isoformat(timespec="seconds")
snap = OUT / f"2026-07-08-originator-backfill-rollback-{ts}.csv"
audit = AUDIT / f"2026-07-08-originator-backfill-{ts}.csv"
with open(snap, "w", newline="", encoding="utf-8") as sf_f, \
     open(audit, "w", newline="", encoding="utf-8") as au_f:
    sw = csv.writer(sf_f); sw.writerow(["SF_Id", "Name", "Originator__c_before"])  # all blank; revert = set null
    aw = csv.writer(au_f); aw.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
    for r in user_owned:
        sw.writerow([r["Id"], r["Name"], "(null)"])
        aw.writerow([r["Id"], r["Name"], "Originator__c", "(null)", r["OwnerId"], SOURCE, now, "backfill"])

payload = [{"Id": r["Id"], "Originator__c": r["OwnerId"]} for r in user_owned]
CHUNK = 5000
done = 0
for i in range(0, len(payload), CHUNK):
    batch = payload[i:i + CHUNK]
    res = sf.bulk.Opportunity.update(batch)
    fails = [x for x in res if not x.get("success")]
    done += len(batch) - len(fails)
    if fails:
        print(f"  batch {i//CHUNK+1}: {len(fails)} failures, e.g. {fails[0]}")
    else:
        print(f"  batch {i//CHUNK+1}: {len(batch)} ok")
print(f"\nBackfilled {done}/{len(user_owned)} opps.\n  rollback -> {snap}\n  audit    -> {audit}")
