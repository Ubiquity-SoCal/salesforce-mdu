"""Phase 2: proper-case ALL CAPS Opportunity names + strip trailing ' -'.

Uses an acronym whitelist (preserve UPPER), a small-word list (lowercase in
middle), and preserves alphanumeric unit tokens like 1G, 300M, BL(1).

Dry-run writes proposals to scripts/cleanup/phase2_proposals.csv for review.
--apply then reads that same CSV and executes. Edit the CSV between runs to
override any titlecased name before applying.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
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
BACKUP = HERE / "rollback"
BACKUP.mkdir(exist_ok=True)
PROPOSALS = HERE / "phase2_proposals.csv"

KEEP_UPPER = {
    # real estate / property
    "HOA", "HOAS", "MDU", "SFU", "SMB", "LLC", "INC", "MHP", "MHC", "RV",
    # telecom / tech
    "SLA", "ISP", "MSO", "ILEC", "CLEC", "ROE", "PAL", "EMA", "VOIP",
    "SAQ", "BL", "ATT", "SFU", "LTE", "FDH", "ONT", "OLT", "GPON",
    # state codes
    "AZ", "TX", "CA", "NE", "CO", "FL", "NV", "NM", "WA", "OR", "ID",
    "IL", "OH", "GA", "NY", "NC", "SC", "VA", "MD", "MA", "NJ", "PA",
    "MI", "MN", "MO", "KS", "OK", "AR", "LA", "KY", "TN", "AL", "MS",
    # directionals
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    # roman numerals
    "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    # other
    "US", "USA", "UK", "FKA", "AKA", "RE", "CP", "LTD", "CO",
    "ASU", "UT", "UA", "UNLV", "UCLA", "SEC", "IT", "AJ",
    "MHP", "NYC", "LA", "SF", "OC", "LV",
}

# Patterns that indicate a synthetic migration key, not a display name.
# These get flagged for manual review instead of auto-titlecased.
MIGRATION_KEY_PATTERNS = [
    re.compile(r"_SA\d+_", re.IGNORECASE),
    re.compile(r"_FDH\d+_", re.IGNORECASE),
    re.compile(r"_PA\d+_", re.IGNORECASE),
    re.compile(r"_MDU_", re.IGNORECASE),
    re.compile(r"_SFU_", re.IGNORECASE),
]


def looks_like_migration_key(name: str) -> bool:
    return any(p.search(name) for p in MIGRATION_KEY_PATTERNS)

LOWER_MID = {
    "a", "an", "and", "or", "the", "of", "in", "at", "on", "to", "for",
    "by", "with", "from", "vs", "de", "la", "le", "du", "da",
}

# Short unit tokens like 1G, 2G, 300M, FDH08, SA12 — uppercase the alpha part.
# Allow up to 3-char alpha prefix so FDH/MDU acronym-codes match, but not long words.
UNIT_TOKEN = re.compile(r"^[0-9]{1,4}[A-Za-z]{1,3}$|^[A-Za-z]{1,3}[0-9]{1,4}$|^[0-9]+$")

# Split points inside a core token — preserve these chars, recurse on pieces
SPLIT_CHARS = "-/_()"


def smart_title_core(core: str, is_first: bool) -> str:
    """Title-case a core token that may contain - / _ separators."""
    if not core:
        return core

    # Split on any SPLIT_CHARS, recurse, rejoin preserving the separator
    for sep in SPLIT_CHARS:
        if sep in core:
            parts = core.split(sep)
            done = []
            for i, p in enumerate(parts):
                done.append(smart_title_core(p, is_first and i == 0))
            return sep.join(done)

    upper = core.upper()
    lower = core.lower()

    # Acronyms
    if upper in KEEP_UPPER:
        return upper

    # Short numeric-alpha unit tokens (1G, 300M, etc.)
    if UNIT_TOKEN.match(core):
        return upper

    # If the core already has a distinctive mixed-case (e.g. "McQueen", "iPhone",
    # brand names like "latitude33"), leave it untouched.
    if (not core.isupper()) and (not core.islower()) and any(c.isalpha() for c in core):
        return core

    # Lowercase-only brand-style tokens with digits (latitude33) — leave as-is
    if any(c.isalpha() for c in core) and any(c.isdigit() for c in core) and core == core.lower():
        return core

    # Single letters in the middle of a name are almost always designators
    # (Phase A, Building B, etc.) — keep them uppercase.
    if len(core) == 1 and core.isalpha():
        return upper

    # Small connecting words stay lowercase in the middle
    if lower in LOWER_MID and not is_first:
        return lower

    # Default: capitalize first letter only
    return lower[:1].upper() + lower[1:]


def smart_title_token(tok: str, is_first: bool) -> str:
    if not tok:
        return tok
    # Peel surrounding punct (parens, brackets, quotes)
    m = re.match(r"^([\(\[\{\"']*)(.*?)([\)\]\}\"',.;:!?]*)$", tok, re.DOTALL)
    lead, core, trail = m.group(1), m.group(2), m.group(3)
    if not core:
        return tok
    return lead + smart_title_core(core, is_first) + trail


def smart_title(name: str) -> str:
    tokens = name.split(" ")
    out = []
    first = True
    for t in tokens:
        if not t:
            out.append(t)
            continue
        out.append(smart_title_token(t, first))
        first = False
    return " ".join(out)


def clean(name: str) -> str:
    # strip trailing ' -' (dangling hyphen after a space)
    name = re.sub(r"\s+-\s*$", "", name)
    # collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return smart_title(name)


def needs_case_fix(name: str) -> bool:
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return False
    if all(c.isupper() for c in letters):
        return True
    if all(c.islower() for c in letters):
        return True
    if name and name[0].islower():
        return True
    return False


def needs_trailing_fix(name: str) -> bool:
    return bool(re.search(r"\s+-\s*$", name))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    sf = Salesforce(**CREDS)

    if not args.apply:
        # Build proposals
        print("Fetching all Opportunities...")
        records = sf.query_all(
            "SELECT Id, Name, StageName, Sales_Status__c FROM Opportunity"
        )["records"]

        proposals = []
        migration_keys = []
        for r in records:
            name = r.get("Name") or ""
            if not (needs_case_fix(name) or needs_trailing_fix(name)):
                continue
            new = clean(name)
            if new == name or not new:
                continue
            row = {
                "Id": r["Id"],
                "old_name": name,
                "proposed_name": new,
                "stage": r.get("StageName") or "",
                "status": r.get("Sales_Status__c") or "",
            }
            if looks_like_migration_key(name):
                migration_keys.append(row)
            else:
                proposals.append(row)

        with PROPOSALS.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["Id", "old_name", "proposed_name", "stage", "status"]
            )
            w.writeheader()
            w.writerows(proposals)

        mig_path = HERE / "phase2_migration_keys_for_review.csv"
        with mig_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f, fieldnames=["Id", "old_name", "proposed_name", "stage", "status"]
            )
            w.writeheader()
            w.writerows(migration_keys)

        print(f"\nAuto-titlecase proposals: {len(proposals)} -> {PROPOSALS}")
        print(f"Migration-key names (manual review): {len(migration_keys)} -> {mig_path}")
        print("Review / edit proposed_name column in the CSV, then rerun with --apply")
        print("\n=== Auto-titlecase preview ===")
        for p in proposals:
            flag = "  [blocked]" if p["stage"] == "Prospecting" and not p["status"] else ""
            print(f"  {p['old_name']!r}")
            print(f"    -> {p['proposed_name']!r}{flag}")
        print("\n=== Migration keys (NOT auto-applied) ===")
        for p in migration_keys:
            print(f"  {p['Id']}  {p['old_name']!r}")
        return

    # Apply mode
    if not PROPOSALS.exists():
        print(f"Missing {PROPOSALS}. Run without --apply first.")
        return
    rows = list(csv.DictReader(PROPOSALS.open(encoding="utf-8")))
    print(f"Loaded {len(rows)} proposals")

    # Pre-fetch notes for any blocked-by-validation rows so we can pick the right
    # Sales_Status based on whether there's outreach activity.
    REACHED_KEYWORDS = [
        "pal sent", "pal draft", "draft pal", "emailed", "left vm", "lvm",
        "called ", "spoke", "met with", "proposal sent", "sent proposal",
        "reached out", "follow up", "followed up", "dropped off",
        "gave proposal", "vm for", "voicemail", "email to", "responded",
    ]
    blocked_ids = [
        r["Id"] for r in rows
        if r.get("stage") == "Prospecting" and not (r.get("status") or "").strip()
    ]
    status_for_blocked: dict[str, str] = {}
    if blocked_ids:
        q = (
            "SELECT LinkedEntityId, ContentDocument.LatestPublishedVersion.TextPreview "
            "FROM ContentDocumentLink WHERE LinkedEntityId IN ('{}')"
            .format("','".join(blocked_ids))
        )
        notes: dict[str, list[str]] = {}
        for r in sf.query_all(q)["records"]:
            ver = r["ContentDocument"].get("LatestPublishedVersion") or {}
            tp = (ver.get("TextPreview") or "").lower()
            notes.setdefault(r["LinkedEntityId"], []).append(tp)
        for oid in blocked_ids:
            nlist = notes.get(oid, [])
            has_outreach = any(any(k in n for k in REACHED_KEYWORDS) for n in nlist)
            status_for_blocked[oid] = (
                "Reached Out - Pending Response" if has_outreach else "Contact Pending"
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"phase2_rollback_{stamp}.csv"
    applied = []
    errors = []
    for r in rows:
        if r["old_name"].strip() == r["proposed_name"].strip():
            continue
        payload = {"Name": r["proposed_name"]}
        if r.get("stage") == "Prospecting" and not (r.get("status") or "").strip():
            payload["Sales_Status__c"] = status_for_blocked.get(r["Id"], "Contact Pending")
        try:
            sf.Opportunity.update(r["Id"], payload)
            applied.append({**r, "status_set": payload.get("Sales_Status__c", "")})
            print(f"  [OK] {r['Id']}  {r['old_name']!r} -> {r['proposed_name']!r}")
        except Exception as e:
            errors.append((r["Id"], str(e)))
            print(f"  [ERR] {r['Id']}  {e}")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["Id", "old_name", "proposed_name", "stage", "status", "status_set"]
        )
        w.writeheader()
        w.writerows(applied)
    print(f"\nApplied {len(applied)}/{len(rows)}. Rollback: {rollback}")
    for cid, msg in errors:
        print(f"  ERR {cid}: {msg}")


if __name__ == "__main__":
    main()
