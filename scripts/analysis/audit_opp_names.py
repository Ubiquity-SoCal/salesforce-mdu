"""Audit Opportunity names for weird characters, spaces, 'text', etc.

Read-only. Writes a report to SalesForce/scripts/analysis/opp_name_audit.json
and prints a summary + category samples to stdout.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from simple_salesforce import Salesforce

CREDS = {
    "username": "cass1@ubiquitygp.com",
    "password": "Hawaiian1984",
    "security_token": "IBSKT6CFUpSUJWxq1CMm0HkFC",
}

OUT_PATH = Path(__file__).parent / "opp_name_audit.json"


def categorize(name: str) -> list[str]:
    issues: list[str] = []
    if name is None:
        return ["null"]
    if name == "":
        issues.append("empty")
        return issues
    stripped = name.strip()
    if stripped == "":
        issues.append("whitespace_only")
        return issues
    if name != stripped:
        issues.append("leading_or_trailing_space")
    if re.search(r"  +", name):
        issues.append("multiple_spaces")
    if re.search(r"[\t\r\n]", name):
        issues.append("tab_or_newline")
    if re.search(r"\btext\b", name, flags=re.IGNORECASE):
        issues.append("literal_text")
    # curly quotes, em/en dashes
    if re.search(r"[\u2018\u2019\u201C\u201D\u2013\u2014]", name):
        issues.append("smart_punctuation")
    # non-ASCII other than smart punctuation already flagged
    non_ascii = [c for c in name if ord(c) > 127]
    if non_ascii:
        # subtract smart punctuation
        other = [c for c in non_ascii if c not in "\u2018\u2019\u201C\u201D\u2013\u2014"]
        if other:
            issues.append("non_ascii_other")
    # control chars
    if any(unicodedata.category(c).startswith("C") for c in name):
        issues.append("control_chars")
    # suspicious symbols repeated
    if re.search(r"[!?*]{2,}", name):
        issues.append("repeated_punct")
    # trailing dot / comma / hyphen
    if stripped and stripped[-1] in ".,-":
        issues.append("trailing_punct")
    # starts with lowercase (may be fine, just flag)
    # quote chars
    if re.search(r'["\u0022]', name):
        issues.append("double_quote")
    return issues


def main() -> None:
    print("Connecting to Salesforce...")
    sf = Salesforce(**CREDS)
    print("Querying Opportunities...")

    query = (
        "SELECT Id, Name, Monday_Item_ID__c, StageName, RecordType.Name "
        "FROM Opportunity"
    )
    results = sf.query_all(query)
    records = results["records"]
    print(f"Fetched {len(records)} Opportunities")

    by_category: dict[str, list[dict]] = defaultdict(list)
    flagged: list[dict] = []

    for r in records:
        name = r.get("Name") or ""
        issues = categorize(name)
        if not issues:
            continue
        stripped = name.strip()
        cleaned = re.sub(r"\s+", " ", stripped)
        row = {
            "Id": r["Id"],
            "Monday_Item_ID__c": r.get("Monday_Item_ID__c"),
            "Stage": r.get("StageName"),
            "RecordType": (r.get("RecordType") or {}).get("Name") if r.get("RecordType") else None,
            "current": name,
            "current_repr": repr(name),
            "proposed": cleaned,
            "issues": issues,
        }
        flagged.append(row)
        for i in issues:
            by_category[i].append(row)

    summary = {cat: len(rows) for cat, rows in sorted(by_category.items(), key=lambda kv: -len(kv[1]))}
    print("\n=== Summary ===")
    for cat, count in summary.items():
        print(f"  {cat:30s} {count}")
    print(f"\nTotal flagged: {len(flagged)} / {len(records)}")

    OUT_PATH.write_text(
        json.dumps(
            {
                "total_opps": len(records),
                "total_flagged": len(flagged),
                "summary": summary,
                "flagged": flagged,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote full report to {OUT_PATH}")

    print("\n=== Samples per category (up to 5) ===")
    for cat, rows in by_category.items():
        print(f"\n[{cat}] {len(rows)} rows")
        for row in rows[:5]:
            same = " (no change)" if row["current"] == row["proposed"] else ""
            print(f"  {row['Id']}  {row['current_repr']}  ->  {row['proposed']!r}{same}")


if __name__ == "__main__":
    sys.exit(main())
