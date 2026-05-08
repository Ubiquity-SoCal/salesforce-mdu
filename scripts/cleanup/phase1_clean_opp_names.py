"""Phase 1 Opportunity name cleanup.

Scope (from audit):
- Collapse runs of whitespace to single spaces (multiple_spaces bucket)
- Unwrap raw Monday.com export strings: {"text6__1"=>"<value>"}

Writes a rollback CSV (Id, old_name, new_name) for every change.

Usage:
    python phase1_clean_opp_names.py --dry-run   # preview, no writes
    python phase1_clean_opp_names.py             # apply
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

CREDS = {
    "username": "cass1@ubiquitygp.com",
    "password": "Hawaiian1984",
    "security_token": "IBSKT6CFUpSUJWxq1CMm0HkFC",
}

HERE = Path(__file__).parent
AUDIT = HERE.parent / "analysis" / "opp_name_audit.json"
BACKUP_DIR = HERE / "rollback"
BACKUP_DIR.mkdir(exist_ok=True)

JSON_WRAPPER = re.compile(r'^\s*\{\s*"[^"]+"\s*=>\s*"(?P<inner>.*)"\s*\}\s*$')


def proposed_name(current: str) -> str:
    m = JSON_WRAPPER.match(current)
    if m:
        current = m.group("inner")
    # collapse whitespace
    current = re.sub(r"\s+", " ", current).strip()
    return current


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    flagged = data["flagged"]
    changes = []
    for row in flagged:
        issues = set(row["issues"])
        if not (issues & {"multiple_spaces", "double_quote"}):
            continue
        old = row["current"]
        new = proposed_name(old)
        if new == old:
            continue
        changes.append({"Id": row["Id"], "old": old, "new": new, "issues": sorted(issues)})

    print(f"Phase 1 changes queued: {len(changes)}")
    for c in changes:
        print(f"  {c['Id']}  {c['issues']}")
        print(f"     OLD: {c['old']!r}")
        print(f"     NEW: {c['new']!r}")

    if args.dry_run:
        print("\nDry run — no writes.")
        return

    if not changes:
        print("Nothing to do.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP_DIR / f"phase1_rollback_{stamp}.csv"

    sf = Salesforce(**CREDS)
    applied = []
    errs = []
    for c in changes:
        try:
            sf.Opportunity.update(c["Id"], {"Name": c["new"]})
            applied.append(c)
            print(f"  [OK] {c['Id']}")
        except Exception as e:
            errs.append((c["Id"], str(e)))
            print(f"  [ERR] {c['Id']}  {e}")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "old_name", "new_name", "issues"])
        for c in applied:
            w.writerow([c["Id"], c["old"], c["new"], ";".join(c["issues"])])
    print(f"\nRollback CSV (applied only): {rollback}")
    ok = len(applied)

    print(f"\nApplied {ok}/{len(changes)}. Errors: {len(errs)}")
    for cid, msg in errs:
        print(f"  {cid}: {msg}")


if __name__ == "__main__":
    main()
