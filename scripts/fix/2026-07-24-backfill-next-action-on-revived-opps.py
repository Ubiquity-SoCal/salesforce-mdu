"""Backfill Next_Action__c on the Opportunities revived out of Closed Lost on 7/16 and 7/23.

Why: both pushes wrote only StageName + Loss_Reason__c. Opportunity field history tracking is
OFF in this org and neither script logged a Task or Chatter post, so 172 records flipped from
Closed Lost to Prospects with ZERO in-Salesforce trace of why. Verified 2026-07-24: 0/73 and
1/99 carry a Description, 4 of 172 carry a Next Action, 0 field-history rows exist. The whole
audit trail lives only in data/output/audit_logs/.

Next_Action__c is the right home per house convention: this org already uses it as a mixed
status/history log ("moved to engage status", "Owner rejected - no agreement"), not strictly as
a forward-looking action. Description was the alternative and is not where the team reads.

Scope: the 172 rows moved OUT of Closed Lost (73 on 7/16 + 99 on 7/23).
       --include-closes adds the 16 rows pushed INTO Closed Lost, which carry their own
       judgment call (Existing BULK recorded as 'Existing Contract' because the picklist has
       no BULK value).

Safety:
  * Dry-run by default. --write executes.
  * Snapshots Id/Name/StageName/Next_Action__c to audit_logs BEFORE writing (rollback source).
  * NEVER overwrites an existing Next_Action__c. Human-typed text wins; those rows are skipped
    and listed, so they can be adjudicated by hand.
  * Idempotent: a row already carrying this backfill note is skipped on re-run.
  * Single-record REST updates, not Bulk API. Bulk 2.0 silently ignored an empty value on the
    7/16 push and reported success anyway; this re-queries every record after writing rather
    than trusting the job's own count.

Usage:
  python -u 2026-07-24-backfill-next-action-on-revived-opps.py                    # dry-run
  python -u 2026-07-24-backfill-next-action-on-revived-opps.py --write
  python -u 2026-07-24-backfill-next-action-on-revived-opps.py --write --include-closes
"""
import csv
import datetime
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # .../SalesForce
AUDIT = ROOT / "data" / "output" / "audit_logs"
STAMP = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

APPLY_0716 = AUDIT / "txne-onnet-stage-push-APPLY-2026-07-16T16-20-53.csv"
STAGED_0716 = AUDIT / "txne-onnet-stage-push-STAGED-2026-07-16T16-20-53.csv"
AUDIT_0723 = AUDIT / "2026-07-23-tx-ne-call-actions-apply-audit.csv"

CALL_0716 = "7/15/2026"   # the review call that decided the 7/16 batch
CALL_0723 = "7/23/2026"   # the review call that decided the 7/23 batch
MARKER = "Moved from"     # idempotency probe: our note always starts with this
MAXLEN = 255              # Next_Action__c is a 255-char string field

WRITE = "--write" in sys.argv
INCLUDE_CLOSES = "--include-closes" in sys.argv


def sf(args):
    p = subprocess.run(["sf"] + args, capture_output=True, text=True, shell=True)
    i = p.stdout.find("{")
    if i < 0:
        raise SystemExit(f"sf returned no JSON: {p.stdout[:200]} {p.stderr[:200]}")
    return json.loads(p.stdout[i:])


def query(soql):
    d = sf(["data", "query", "--query", soql, "--json"])
    if d.get("status") != 0:
        raise SystemExit(f"query failed: {str(d)[:300]}")
    return d["result"]["records"]


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def note_for(old_stage, old_loss, new_stage, call_date):
    """Per-row note: where it came from, where it went, which call decided it. Nothing else.

    Koa's call on wording - the rationale tail ("no contact could be reached", "soft loss
    reason, re-approachable") is dropped. The note states the movement, not the argument for
    it. Per-row loss reason is KEPT because the two batches came out of different reasons and
    a blanket "Contact Info" string would be false on the 82 rows that closed for other reasons.
    "Closed - Contact Info" matches the workbook's own action label for that bucket.
    """
    old_loss = (old_loss or "").strip()
    to_stage = "Prospects" if new_stage == "Prospects" else "Closed Lost"
    if old_stage != "Closed Lost":
        frm = old_stage
    elif old_loss == "No Contact Info":
        frm = "Closed - Contact Info"
    elif old_loss:
        frm = f"Closed Lost - {old_loss}"
    else:
        frm = "Closed Lost"
    return f"Moved from {frm} to {to_stage} per {call_date} call"


def build_plan():
    """(id, site, old_stage, old_loss, new_stage, batch, note) for every record we touched."""
    plan = []

    # --- 7/16: the APPLY log records what actually wrote; STAGED carries the before-state.
    staged = {r["SF Id"]: r for r in rows(STAGED_0716)}
    for r in rows(APPLY_0716):
        s = staged.get(r["Id"], {})
        plan.append({
            "id": r["Id"],
            "site": s.get("Site Name") or s.get("SF Name") or "",
            "old_stage": s.get("Stage: from", "Closed Lost"),
            "old_loss": s.get("Loss Reason: from", ""),
            "new_stage": r["StageName"],
            "batch": "2026-07-16",
            "call": CALL_0716,
        })

    # --- 7/23: single audit CSV carries both before and after.
    for r in rows(AUDIT_0723):
        if r["result"] != "OK":
            continue
        plan.append({
            "id": r["Id"], "site": r["site"],
            "old_stage": r["old_stage"], "old_loss": r["old_loss"],
            "new_stage": r["new_stage"], "batch": "2026-07-23", "call": CALL_0723,
        })

    for p in plan:
        n = note_for(p["old_stage"], p["old_loss"], p["new_stage"], p["call"])
        if len(n) > MAXLEN:                      # never let SF truncate mid-word for us
            n = n[:MAXLEN - 3].rsplit(" ", 1)[0] + "..."
        # the value is passed to the CLI single-quoted; an apostrophe would break out of it
        # and silently mangle the write. Loss reason picklist values have none, but assert.
        assert "'" not in n, f"note contains an apostrophe, would break --values: {n}"
        p["note"] = n

    if not INCLUDE_CLOSES:
        plan = [p for p in plan if p["new_stage"] == "Prospects"]
    return plan


def main():
    plan = build_plan()
    print(f"audit logs -> {len(plan)} records touched by the two pushes")
    print(f"   {dict(Counter((p['batch'], p['new_stage']) for p in plan))}")

    ids = sorted({p["id"] for p in plan})
    live = {}
    for i in range(0, len(ids), 150):
        chunk = ",".join(f"'{x}'" for x in ids[i:i + 150])
        for r in query("SELECT Id, Name, StageName, Loss_Reason__c, Next_Action__c "
                       f"FROM Opportunity WHERE Id IN ({chunk})"):
            live[r["Id"]] = r
    print(f"live SF lookup: {len(live)}/{len(ids)} records found")

    # Rows THIS backfill has already written. Proven from our own pre-write snapshots, which
    # recorded Next_Action__c as it stood before we touched anything - not from a text prefix.
    # An earlier run wrote a longer wording that Koa has since revised; those rows must be
    # REWRITTEN, while a human-typed note on the same field must never be.
    ours = set()
    for snapf in AUDIT.glob("backfill-next-action-SNAPSHOT-*.csv"):
        for r in rows(snapf):
            if not (r.get("Next_Action__c") or "").strip():
                ours.add(r["Id"])
    print(f"previously targeted by this backfill (safe to rewrite): {len(ours)}")

    todo, skip_has_note, skip_done, missing, drifted, rewrite = [], [], [], [], [], []
    for p in plan:
        rec = live.get(p["id"])
        if not rec:
            missing.append(p)
            continue
        p["name"] = rec["Name"]
        p["cur_stage"] = rec["StageName"]
        existing = (rec.get("Next_Action__c") or "").strip()
        if rec["StageName"] != p["new_stage"]:
            # someone has moved it on since the push. Note is still true history, but say so.
            drifted.append(p)
        if existing == p["note"]:
            skip_done.append(p)                 # already exactly right, re-run no-op
        elif existing and p["id"] in ours:
            p["existing"] = existing            # our own earlier wording, replace it
            rewrite.append(p)
            todo.append(p)
        elif existing:
            p["existing"] = existing            # human wrote this. Hands off.
            skip_has_note.append(p)
        else:
            todo.append(p)

    print(f"\n  to write .................. {len(todo)}  (of which rewrites: {len(rewrite)})")
    print(f"  skipped, human note ....... {len(skip_has_note)}  (never overwritten)")
    print(f"  skipped, already correct .. {len(skip_done)}")
    print(f"  not found in SF ........... {len(missing)}")
    print(f"  stage drifted since push .. {len(drifted)}  (note still written, history is true)")

    if skip_has_note:
        print("\n  rows left alone because a human already typed a Next Action:")
        for p in skip_has_note:
            print(f"    {p['name'][:42]:42} | {p['existing'][:70]}")
    if drifted:
        print("\n  stage no longer matches the push:")
        for p in drifted:
            print(f"    {p['name'][:42]:42} {p['new_stage']} -> now {p['cur_stage']}")

    staged_f = AUDIT / f"backfill-next-action-STAGED-{STAMP}.csv"
    with staged_f.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Site", "Batch", "From Stage", "From Loss",
                    "To Stage", "Proposed Next_Action__c", "Chars"])
        for p in todo:
            w.writerow([p["id"], p["name"], p["site"], p["batch"], p["old_stage"],
                        p["old_loss"], p["new_stage"], p["note"], len(p["note"])])
    print(f"\nstaged diff -> {staged_f.name}")

    print("\nnote variants that will be written:")
    for note, n in Counter(p["note"] for p in todo).most_common():
        print(f"  [{n:>3}] {note}")

    if not WRITE:
        print("\nDRY-RUN. Nothing written. Re-run with --write to apply.")
        return

    # ---- rollback snapshot BEFORE any write
    snap = AUDIT / f"backfill-next-action-SNAPSHOT-{STAMP}.csv"
    with snap.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "StageName", "Loss_Reason__c", "Next_Action__c"])
        for p in todo:
            r = live[p["id"]]
            w.writerow([r["Id"], r["Name"], r["StageName"],
                        r.get("Loss_Reason__c") or "", r.get("Next_Action__c") or ""])
    nonblank = sum(1 for p in todo if (live[p["id"]].get("Next_Action__c") or "").strip())
    print(f"rollback snapshot -> {snap.name}  ({len(todo)} rows, "
          f"{len(todo) - nonblank} previously blank, {nonblank} carrying our earlier wording)")

    applied = AUDIT / f"backfill-next-action-APPLY-{STAMP}.csv"
    res = Counter()
    with applied.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Next_Action__c", "result", "detail"])
        for i, p in enumerate(todo, 1):
            # `sf data update record` splits --values on WHITESPACE. An unquoted value with
            # spaces dies as "Malformed key=value pair for value: from." The value must be
            # single-quoted, exactly as the 7/23 script does it. Verified round-trip: the CLI
            # strips the quotes, SF stores the bare string (196 chars in, 196 out, exact match).
            d = sf(["data", "update", "record", "--sobject", "Opportunity", "--record-id",
                    p["id"], "--values", f"Next_Action__c='{p['note']}'", "--json"])
            ok = d.get("status") == 0
            res["OK" if ok else "FAIL"] += 1
            detail = "" if ok else json.dumps(d.get("message") or d)[:200]
            w.writerow([p["id"], p["name"], p["note"], "OK" if ok else "FAIL", detail])
            if i % 25 == 0 or not ok:
                print(f"  [{i}/{len(todo)}] {'OK ' if ok else 'FAIL'} {p['name'][:45]} {detail}")
    print(f"\nwrite results: {dict(res)} -> {applied.name}")

    # ---- verify by re-query. The 7/16 push taught us not to trust a job's own success count.
    check = {}
    wrote = [p["id"] for p in todo]
    for i in range(0, len(wrote), 150):
        chunk = ",".join(f"'{x}'" for x in wrote[i:i + 150])
        for r in query(f"SELECT Id, Next_Action__c FROM Opportunity WHERE Id IN ({chunk})"):
            check[r["Id"]] = (r.get("Next_Action__c") or "")
    good = sum(1 for p in todo if check.get(p["id"], "").startswith(MARKER))
    print(f"VERIFY (re-queried, not job-reported): {good}/{len(todo)} carry the note")
    bad = [p for p in todo if not check.get(p["id"], "").startswith(MARKER)]
    for p in bad:
        print(f"  MISSING NOTE: {p['id']} {p['name']}")


if __name__ == "__main__":
    main()
