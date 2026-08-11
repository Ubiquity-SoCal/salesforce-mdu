"""Normalize Opportunity.Property_State__c and Account.BillingState to
2-letter US state codes. Preserves blanks. Flags non-US values (e.g. Ontario).

Usage:
    python normalize_states.py             # dry run preview
    python normalize_states.py --apply     # apply
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import Counter
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

US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
CODES = set(US_STATES.values())
NAME_TO_CODE = {k.lower(): v for k, v in US_STATES.items()}


def normalize(value: str | None) -> tuple[str | None, str]:
    """Return (new_value, action). action in {'skip','case_fix','expand','unknown'}."""
    if value is None:
        return None, "skip"
    v = value.strip()
    if not v:
        return None, "skip"
    up = v.upper()
    if up in CODES:
        if v == up:
            return v, "skip"
        return up, "case_fix"
    low = v.lower()
    if low in NAME_TO_CODE:
        return NAME_TO_CODE[low], "expand"
    return v, "unknown"


def process(sf: Salesforce, obj: str, field: str, apply: bool) -> list[dict]:
    print(f"\n=== {obj}.{field} ===")
    rows = sf.query_all(f"SELECT Id, {field} FROM {obj}")["records"]
    actions = Counter()
    changes = []
    unknowns = Counter()
    for r in rows:
        current = r.get(field)
        new, act = normalize(current)
        actions[act] += 1
        if act == "unknown":
            unknowns[current] += 1
            continue
        if act in ("case_fix", "expand"):
            changes.append({
                "Id": r["Id"], "object": obj, "field": field,
                "old": current, "new": new, "action": act,
            })
    print(f"  actions: {dict(actions)}")
    if unknowns:
        print(f"  unknown values (left alone):")
        for v, n in unknowns.most_common():
            print(f"    {v!r:30s} {n}")
    print(f"  changes queued: {len(changes)}")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sf = Salesforce(**CREDS)

    all_changes: list[dict] = []
    all_changes += process(sf, "Opportunity", "Property_State__c", args.apply)
    all_changes += process(sf, "Account", "BillingState", args.apply)

    if not args.apply:
        # print a small preview
        by_change = Counter((c["old"], c["new"]) for c in all_changes)
        print("\n=== Change summary (old -> new, count) ===")
        for (o, n), k in by_change.most_common(30):
            print(f"  {o!r:25s} -> {n!r:6s}  {k}")
        print(f"\nTotal: {len(all_changes)}. Re-run with --apply to execute.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"normalize_states_rollback_{stamp}.csv"

    applied = []
    errors = []

    # Group by object and use Bulk API for speed (3k+ records).
    by_obj: dict[str, list[dict]] = {}
    for ch in all_changes:
        by_obj.setdefault(ch["object"], []).append(ch)

    for obj, chs in by_obj.items():
        print(f"\nBulk-updating {len(chs)} {obj} records...")
        payload = [{"Id": c["Id"], c["field"]: c["new"]} for c in chs]
        results = sf.bulk.__getattr__(obj).update(payload, batch_size=2000)
        for ch, res in zip(chs, results):
            if res.get("success"):
                applied.append(ch)
            else:
                err_msg = ";".join(e.get("message", "") for e in (res.get("errors") or []))[:300]
                errors.append((ch["Id"], obj, ch["field"], err_msg))

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Id", "object", "field", "old", "new", "action"])
        w.writeheader(); w.writerows(applied)

    print(f"\nApplied {len(applied)}/{len(all_changes)}. Errors: {len(errors)}")
    print(f"Rollback: {rollback}")
    if errors:
        print("\nErrors (first 20):")
        for oid, obj, fld, msg in errors[:20]:
            print(f"  {obj}.{fld} {oid}  {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
        # save errors too
        err_path = BACKUP / f"normalize_states_errors_{stamp}.csv"
        with err_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Id", "object", "field", "error"])
            w.writerows(errors)
        print(f"Full errors: {err_path}")


if __name__ == "__main__":
    main()
