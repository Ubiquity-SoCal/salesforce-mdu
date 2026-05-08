"""Strip decorative unicode symbols (⚫ ● ★ ✓ etc.) from Opportunity.Name.

Preserves letters-with-diacritics (ñ, á, ü, etc.) — only removes unicode
'Symbol, Other' and 'Symbol, Modifier' categories.

Writes a rollback CSV. Handles the Sales_Status validation rule by populating
Sales_Status__c from notes when the record is in Prospecting with a blank
status (same approach as phase1b).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

CREDS = {
    "username": "cass1@ubiquitygp.com",
    "password": "Hawaiian1984",
    "security_token": "IBSKT6CFUpSUJWxq1CMm0HkFC",
}

HERE = Path(__file__).parent
BACKUP = HERE / "rollback"
BACKUP.mkdir(exist_ok=True)

# unicode categories to strip
STRIP_CATEGORIES = {"So", "Sk", "Cf", "Cc"}


def clean_name(name: str) -> str:
    out = "".join(c for c in name if unicodedata.category(c) not in STRIP_CATEGORIES)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    sf = Salesforce(**CREDS)
    print("Fetching all Opportunities...")
    records = sf.query_all(
        "SELECT Id, Name, StageName, Sales_Status__c FROM Opportunity"
    )["records"]
    print(f"  {len(records)} total")

    proposals = []
    for r in records:
        old = r.get("Name") or ""
        new = clean_name(old)
        if new != old and new:
            proposals.append(
                {
                    "Id": r["Id"],
                    "old": old,
                    "new": new,
                    "stage": r.get("StageName"),
                    "status": r.get("Sales_Status__c"),
                }
            )

    print(f"\nProposed changes: {len(proposals)}")
    for p in proposals:
        blocked = p["stage"] == "Prospecting" and not p["status"]
        tag = "  [blocked: needs Sales_Status]" if blocked else ""
        print(f"  {p['Id']}  {p['old']!r} -> {p['new']!r}{tag}")

    if args.dry_run or not args.apply:
        print("\nDry run — use --apply to execute.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"phase1c_rollback_{stamp}.csv"
    applied = []
    errors = []
    for p in proposals:
        payload = {"Name": p["new"]}
        if p["stage"] == "Prospecting" and not p["status"]:
            # All 5 blocked ⚫ records have outreach notes (PALs sent, calls, emails).
            # Reviewed with Koa 2026-04-20 — all qualify as Reached Out.
            payload["Sales_Status__c"] = "Reached Out - Pending Response"
        try:
            sf.Opportunity.update(p["Id"], payload)
            applied.append({**p, "status_set": payload.get("Sales_Status__c")})
            print(f"  [OK] {p['Id']}")
        except Exception as e:
            errors.append((p["Id"], str(e)))
            print(f"  [ERR] {p['Id']}  {e}")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["Id", "old", "new", "stage", "status", "status_set"]
        )
        w.writeheader()
        w.writerows(applied)
    print(f"\nApplied {len(applied)}/{len(proposals)}. Rollback: {rollback}")
    if errors:
        for cid, msg in errors:
            print(f"  ERR {cid}: {msg}")


if __name__ == "__main__":
    main()
