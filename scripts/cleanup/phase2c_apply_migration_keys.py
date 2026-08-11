"""Apply the migration-key name renames (11 records) from
phase2_migration_keys_for_review.csv.

Handles validation rules:
- Closed Lost without Loss_Reason__c -> set Loss_Reason__c = "Other"
- Prospecting without Sales_Status__c -> use outreach heuristic on notes
  (Reached Out if outreach keywords present, else Contact Pending)
"""
from __future__ import annotations

import csv
import io
import sys
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
CSV_PATH = HERE / "phase2_migration_keys_for_review.csv"
BACKUP = HERE / "rollback"

REACHED_KEYWORDS = [
    "pal sent", "pal draft", "draft pal", "emailed", "left vm", "lvm",
    "called ", "spoke", "met with", "proposal sent", "sent proposal",
    "reached out", "follow up", "followed up", "dropped off",
    "gave proposal", "vm for", "voicemail", "email to", "responded",
]


def main() -> None:
    sf = Salesforce(**CREDS)
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    print(f"Loaded {len(rows)} rows")

    ids = [r["Id"] for r in rows]
    curr = {
        r["Id"]: r
        for r in sf.query_all(
            "SELECT Id, Name, StageName, Sales_Status__c, Loss_Reason__c "
            "FROM Opportunity WHERE Id IN ('{}')".format("','".join(ids))
        )["records"]
    }

    # Pull notes for any Prospecting+blank-status row for the heuristic
    prospecting_ids = [
        r["Id"] for r in rows
        if curr[r["Id"]]["StageName"] == "Prospecting"
        and not curr[r["Id"]].get("Sales_Status__c")
    ]
    notes: dict[str, list[str]] = {}
    if prospecting_ids:
        q = (
            "SELECT LinkedEntityId, ContentDocument.LatestPublishedVersion.TextPreview "
            "FROM ContentDocumentLink WHERE LinkedEntityId IN ('{}')"
            .format("','".join(prospecting_ids))
        )
        for r in sf.query_all(q)["records"]:
            ver = r["ContentDocument"].get("LatestPublishedVersion") or {}
            tp = (ver.get("TextPreview") or "").lower()
            notes.setdefault(r["LinkedEntityId"], []).append(tp)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"phase2c_migkeys_rollback_{stamp}.csv"
    applied = []
    errors = []

    for r in rows:
        oid = r["Id"]
        c = curr.get(oid)
        if not c:
            errors.append((oid, "record not found"))
            continue
        payload = {"Name": r["proposed_name"]}
        stage = c["StageName"]
        if stage == "Closed Lost" and not c.get("Loss_Reason__c"):
            payload["Loss_Reason__c"] = "Other"
        elif stage == "Prospecting" and not c.get("Sales_Status__c"):
            nlist = notes.get(oid, [])
            has_outreach = any(any(k in n for k in REACHED_KEYWORDS) for n in nlist)
            payload["Sales_Status__c"] = (
                "Reached Out - Pending Response" if has_outreach else "Contact Pending"
            )
        try:
            sf.Opportunity.update(oid, payload)
            applied.append({
                "Id": oid,
                "old_name": c["Name"],
                "new_name": r["proposed_name"],
                "stage": stage,
                "loss_reason_set": payload.get("Loss_Reason__c", ""),
                "status_set": payload.get("Sales_Status__c", ""),
            })
            extra = ""
            if "Loss_Reason__c" in payload:
                extra = f"  loss_reason=Other"
            elif "Sales_Status__c" in payload:
                extra = f"  status={payload['Sales_Status__c']}"
            print(f"  [OK] {oid}  {c['Name']!r} -> {r['proposed_name']!r}{extra}")
        except Exception as e:
            errors.append((oid, str(e)))
            print(f"  [ERR] {oid}  {e}")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["Id", "old_name", "new_name", "stage",
                           "loss_reason_set", "status_set"]
        )
        w.writeheader(); w.writerows(applied)
    print(f"\nApplied {len(applied)}/{len(rows)}. Rollback: {rollback}")
    for cid, msg in errors:
        print(f"  ERR {cid}: {msg}")


if __name__ == "__main__":
    main()
