"""Backfill required validation fields on Opps stuck in mid-stage with blank keys.

- Prospecting + blank Sales_Status__c: use note-keyword heuristic
  (outreach words -> 'Reached Out - Pending Response'; else 'Contact Pending')
- Closed Lost + blank Loss_Reason__c: default 'Other'
- On Hold + blank Hold_Reason__c: default 'Other'

Uses Bulk API. Writes rollback CSV.

Scoped to the records currently blocked from state normalization (all Opps).
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CREDS = {
    "username": _SF["username"],
    "password": _SF["password"],
    "security_token": _SF["token"],
}

HERE = Path(__file__).parent
BACKUP = HERE / "rollback"
BACKUP.mkdir(exist_ok=True)

REACHED_KEYWORDS = [
    "pal sent", "pal draft", "draft pal", "emailed", "left vm", "lvm",
    "called ", "spoke", "met with", "proposal sent", "sent proposal",
    "reached out", "follow up", "followed up", "dropped off",
    "gave proposal", "vm for", "voicemail", "email to", "responded",
    "meeting with", "talked with", "asked for a",
]


def fetch_notes_batched(sf: Salesforce, ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for i in range(0, len(ids), 150):
        chunk = ids[i : i + 150]
        q = (
            "SELECT LinkedEntityId, ContentDocument.LatestPublishedVersion.TextPreview "
            "FROM ContentDocumentLink WHERE LinkedEntityId IN ('{}')"
            .format("','".join(chunk))
        )
        for r in sf.query_all(q)["records"]:
            ver = r["ContentDocument"].get("LatestPublishedVersion") or {}
            tp = (ver.get("TextPreview") or "").lower()
            if tp:
                out[r["LinkedEntityId"]].append(tp)
        if (i // 150) % 5 == 0:
            print(f"    notes fetched for {min(i + 150, len(ids))}/{len(ids)}")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    sf = Salesforce(**CREDS)

    print("Querying Opps missing required fields...")
    prospecting = sf.query_all(
        "SELECT Id, Name FROM Opportunity "
        "WHERE StageName = 'Prospecting' AND Sales_Status__c = null"
    )["records"]
    closed_lost = sf.query_all(
        "SELECT Id, Name FROM Opportunity "
        "WHERE StageName = 'Closed Lost' AND Loss_Reason__c = null"
    )["records"]
    on_hold = sf.query_all(
        "SELECT Id, Name FROM Opportunity "
        "WHERE StageName = 'On Hold' AND Hold_Reason__c = null"
    )["records"]

    print(f"  Prospecting blank:  {len(prospecting)}")
    print(f"  Closed Lost blank:  {len(closed_lost)}")
    print(f"  On Hold blank:      {len(on_hold)}")

    # Fetch notes only for Prospecting (heuristic needs them)
    print("\nFetching notes for Prospecting opps...")
    prospecting_ids = [r["Id"] for r in prospecting]
    notes = fetch_notes_batched(sf, prospecting_ids) if prospecting_ids else {}
    print(f"  {sum(len(v) for v in notes.values())} notes across {len(notes)} Opps")

    # Decide status
    prospecting_updates = []
    status_counts = Counter()
    for r in prospecting:
        oid = r["Id"]
        nlist = notes.get(oid, [])
        has_outreach = any(
            any(k in n for k in REACHED_KEYWORDS) for n in nlist
        )
        status = "Reached Out - Pending Response" if has_outreach else "Contact Pending"
        prospecting_updates.append({"Id": oid, "Name": r.get("Name"), "Sales_Status__c": status})
        status_counts[status] += 1

    print(f"\n  Status distribution: {dict(status_counts)}")

    closed_lost_updates = [
        {"Id": r["Id"], "Name": r.get("Name"), "Loss_Reason__c": "Other"}
        for r in closed_lost
    ]
    on_hold_updates = [
        {"Id": r["Id"], "Name": r.get("Name"), "Hold_Reason__c": "Other"}
        for r in on_hold
    ]

    total = len(prospecting_updates) + len(closed_lost_updates) + len(on_hold_updates)
    print(f"\nTotal updates queued: {total}")

    if not args.apply:
        print("\nDry run — re-run with --apply to execute.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"backfill_statuses_rollback_{stamp}.csv"
    all_applied: list[dict] = []
    all_errors: list[tuple] = []

    def bulk_update(payloads: list[dict], label: str) -> None:
        if not payloads:
            return
        print(f"\n  Bulk-updating {len(payloads)} {label}...")
        payload_api = [{k: v for k, v in p.items() if k != "Name"} for p in payloads]
        results = sf.bulk.Opportunity.update(payload_api, batch_size=2000)
        for orig, res in zip(payloads, results):
            if res.get("success"):
                all_applied.append({**orig, "kind": label})
            else:
                err_msg = ";".join(
                    e.get("message", "") for e in (res.get("errors") or [])
                )[:300]
                all_errors.append((orig["Id"], label, err_msg))

    bulk_update(prospecting_updates, "Sales_Status")
    bulk_update(closed_lost_updates, "Loss_Reason")
    bulk_update(on_hold_updates, "Hold_Reason")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Id", "Name", "kind", "Sales_Status__c", "Loss_Reason__c", "Hold_Reason__c"],
            extrasaction="ignore",
        )
        w.writeheader(); w.writerows(all_applied)
    print(f"\nApplied {len(all_applied)}/{total}. Errors: {len(all_errors)}")
    print(f"Rollback: {rollback}")
    if all_errors:
        err_path = BACKUP / f"backfill_statuses_errors_{stamp}.csv"
        with err_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["Id", "kind", "error"]); w.writerows(all_errors)
        print(f"Errors: {err_path}")
        ctr = Counter(e[2][:80] for e in all_errors)
        for m, n in ctr.most_common(10):
            print(f"  {n}  {m}")


if __name__ == "__main__":
    main()
