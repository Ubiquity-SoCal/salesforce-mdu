"""Clear Loss_Reason__c on the 73 Opportunities revived to Prospects on 2026-07-16.

Why this exists as a separate script: the main push
(2026-07-16-txne-onnet-stage-push.py) moved 73 rows Closed Lost -> Prospects and reported
"85 processed, 85 successful, 0 failed" - but Loss_Reason__c never cleared. Bulk API 2.0 IGNORES
an empty CSV value rather than nulling the field, so all 73 landed as OPEN opportunities still
carrying 'No Contact Info'. The job status was a lie by omission; only re-querying the records
caught it.

'#N/A' is the documented Bulk API null token but is not used here - a single-record REST update
with an empty value is verified working on this org (Riverside Villas, 006WR00000wk9SuYAI), so
this uses the method proven against the actual data rather than the one the docs recommend.

Idempotent: only touches rows that are Prospects AND still have a Loss_Reason__c.
"""

import json
import subprocess
import sys
import csv
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "data" / "output" / "audit_logs"
STAMP = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def sfq(q):
    p = subprocess.run(["sf", "data", "query", "--query", q, "--json"],
                       capture_output=True, text=True, shell=True)
    i = p.stdout.find("{")
    d = json.loads(p.stdout[i:])
    if d.get("status") != 0:
        raise SystemExit(f"query failed: {str(d)[:300]}")
    return d["result"]["records"]


def clear(rec_id):
    p = subprocess.run(["sf", "data", "update", "record", "--sobject", "Opportunity",
                        "--record-id", rec_id, "--values", "Loss_Reason__c=", "--json"],
                       capture_output=True, text=True, shell=True)
    i = p.stdout.find("{")
    if i < 0:
        return False, p.stdout[:120] + p.stderr[:120]
    d = json.loads(p.stdout[i:])
    return d.get("status") == 0, str(d.get("message", ""))[:120]


def main():
    import glob
    from collections import Counter
    execute = "--execute" in sys.argv

    # Scope STRICTLY to the records this push touched, read back from its own apply log.
    # Do NOT select on "Prospects AND Loss_Reason != null" - that is the bug's signature, but it
    # also matches 3 records we never touched (1 'Other', 2 'Rejected by Owner') which are
    # pre-existing data issues someone else owns. Cleaning those silently would be scope creep
    # into records nobody asked us to change.
    logs = sorted(glob.glob(str(AUDIT_DIR / "txne-onnet-stage-push-APPLY-*.csv")))
    if not logs:
        raise SystemExit("no apply log found - refusing to guess which records were pushed")
    pushed = {r["Id"] for r in csv.DictReader(open(logs[-1]))
              if not r["Loss_Reason__c"] or r["Loss_Reason__c"] == "#N/A"}
    print(f"apply log      : {Path(logs[-1]).name}")
    print(f"rows this push moved to Prospects: {len(pushed)}")

    targets = []
    for i in range(0, len(pushed), 50):
        chunk = ",".join(f"'{x}'" for x in list(pushed)[i:i + 50])
        targets += sfq(
            "SELECT Id, Name, Agreement_Name__c, StageName, Loss_Reason__c FROM Opportunity "
            f"WHERE Id IN ({chunk}) AND Loss_Reason__c != null"
        )
    print(f"of those, still carrying a Loss_Reason: {len(targets)}")
    print(f"  by reason: {dict(Counter(t['Loss_Reason__c'] for t in targets))}")

    others = sfq("SELECT Id, Name, Loss_Reason__c FROM Opportunity "
                 "WHERE StageName = 'Prospects' AND Loss_Reason__c != null")
    out_of_scope = [o for o in others if o["Id"] not in pushed]
    if out_of_scope:
        print(f"\n  NOT TOUCHING - {len(out_of_scope)} pre-existing open Opps with a loss reason,")
        print("  unrelated to this push (flag for review, do not auto-fix):")
        for o in out_of_scope:
            print(f"    {o['Name'][:44]:44s} | {o['Loss_Reason__c']}")
    print()

    if not execute:
        for t in targets[:5]:
            print(f"  would clear: {t['Name'][:44]:44s} | {t['Loss_Reason__c']}")
        print(f"\nDRY RUN. {len(targets)} rows would be cleared. Re-run with --execute.")
        return

    snap = AUDIT_DIR / f"clear-loss-reason-SNAPSHOT-{STAMP}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Agreement_Name__c", "StageName", "Loss_Reason__c"])
        for t in targets:
            w.writerow([t["Id"], t["Name"], t.get("Agreement_Name__c") or "", t["StageName"],
                        t["Loss_Reason__c"]])
    print(f"snapshot -> {snap}\n")

    ok = fail = 0
    fails = []
    for i, t in enumerate(targets, 1):
        good, msg = clear(t["Id"])
        if good:
            ok += 1
        else:
            fail += 1
            fails.append((t["Name"], msg))
        if i % 20 == 0 or i == len(targets):
            print(f"  {i}/{len(targets)} ... ok={ok} fail={fail}")
    print()
    for n, m in fails:
        print(f"  FAILED {n}: {m}")

    # Verify against live SF. The whole reason this script exists is that a success count was
    # not the same as the data being right.
    left = sfq("SELECT Id FROM Opportunity WHERE StageName = 'Prospects' AND Loss_Reason__c != null")
    print(f"\nVERIFY: open Opportunities still carrying a Loss_Reason = {len(left)} (target: 0)")


if __name__ == "__main__":
    main()
