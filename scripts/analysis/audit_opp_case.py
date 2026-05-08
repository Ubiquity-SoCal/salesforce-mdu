"""Audit Opportunity Name casing — find ALL CAPS, all lowercase, etc.

Read-only. Writes report to SalesForce/scripts/analysis/opp_case_audit.json.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from simple_salesforce import Salesforce

CREDS = {
    "username": "cass1@ubiquitygp.com",
    "password": "Hawaiian1984",
    "security_token": "IBSKT6CFUpSUJWxq1CMm0HkFC",
}

OUT = Path(__file__).parent / "opp_case_audit.json"

# Acronyms/tokens that must stay uppercase after titlecasing
KEEP_UPPER = {
    "HOA", "HOAs", "MDU", "SFU", "SMB", "LLC", "RV", "MHP", "MHC",
    "USA", "US", "UK", "II", "III", "IV", "V", "VI", "VII", "VIII",
    "AZ", "TX", "CA", "NE", "CO", "FL", "NV", "NM", "WA", "OR", "ID",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    "ISP", "MSO", "ILEC", "CLEC", "ROE", "PAL", "EMA", "SAQ", "AT&T",
    "MHP", "NYC", "LA", "SF", "OC",
}
LOWER_IN_MIDDLE = {"of", "the", "and", "or", "in", "at", "on", "to", "for", "by", "a", "an", "vs", "de", "la"}


def main() -> None:
    sf = Salesforce(**CREDS)
    rows = sf.query_all("SELECT Id, Name FROM Opportunity")["records"]
    names = [(r["Id"], r.get("Name") or "") for r in rows]

    buckets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for oid, n in names:
        letters = [c for c in n if c.isalpha()]
        if not letters:
            buckets["no_letters"].append((oid, n))
            continue
        if all(c.isupper() for c in letters):
            buckets["all_upper"].append((oid, n))
        elif all(c.islower() for c in letters):
            buckets["all_lower"].append((oid, n))
        elif n[0].islower():
            buckets["lower_start"].append((oid, n))
        else:
            # any word that's entirely UPPER and >1 char and not in KEEP_UPPER
            tokens = re.split(r"\s+", n)
            offenders = [t for t in tokens
                         if len(t) > 1 and t.isalpha() and t.isupper() and t.upper() not in KEEP_UPPER]
            if offenders:
                buckets["mixed_has_caps_word"].append((oid, n))

    print("=== Casing buckets ===")
    for k, v in buckets.items():
        print(f"  {k:25s} {len(v)}")

    # sample up to 30 per bucket
    samples = {k: v[:30] for k, v in buckets.items()}
    OUT.write_text(
        json.dumps(
            {k: [{"Id": i, "Name": n} for i, n in v] for k, v in buckets.items()},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {OUT}")
    print("\n=== Samples ===")
    for k, v in samples.items():
        print(f"\n[{k}] ({len(buckets[k])} total, showing up to 30)")
        for _id, n in v:
            print(f"  {_id}  {n!r}")


if __name__ == "__main__":
    main()
