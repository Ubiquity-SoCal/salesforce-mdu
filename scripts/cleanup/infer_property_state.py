"""Infer Opportunity.Property_State__c for the 71 blank records.

Signals (in priority order):
  1. Account.BillingState (high confidence)
  2. Explicit state mention in Name (regex for ', TX' / ' TX ' / 'Texas' / 'of Nebraska')
  3. City word in Name that maps to a known state
  4. SiteTracker linked project's State__c

Writes proposals CSV; --apply uses the CSV (edit between runs for overrides).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
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
PROPOSALS = HERE / "state_infer_proposals.csv"
BACKUP = HERE / "rollback"

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
    "Wisconsin": "WI", "Wyoming": "WY",
}
CODES = set(US_STATES.values())

# Known cities in our service areas → state
CITY_TO_STATE = {
    "omaha": "NE", "lincoln": "NE", "bellevue": "NE", "papillion": "NE",
    "la vista": "NE", "elkhorn": "NE", "fremont": "NE",
    "mesa": "AZ", "phoenix": "AZ", "chandler": "AZ", "gilbert": "AZ",
    "tempe": "AZ", "scottsdale": "AZ", "glendale": "AZ", "tucson": "AZ",
    "killeen": "TX", "harker heights": "TX", "hutto": "TX", "austin": "TX",
    "dallas": "TX", "fort worth": "TX", "houston": "TX", "san antonio": "TX",
    "georgetown": "TX", "bridgeport": "TX",  # Bridgeport TX (likely context)
    "carlsbad": "CA", "encinitas": "CA", "solana beach": "CA", "oceanside": "CA",
    "san diego": "CA", "los angeles": "CA",
    "saint paul": "MN", "st paul": "MN", "minneapolis": "MN",
    "mineral wells": "TX",
}

# Regex to find state abbreviation tokens in a name
STATE_ABBR_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])")


def infer_state(name: str, account_state: str | None, st_state: str | None) -> tuple[str | None, str]:
    """Return (state_code, source). Source ∈ {account, st, name_abbr, name_full, city, none}."""
    # 1. Account
    if account_state and account_state.upper() in CODES:
        return account_state.upper(), "account"
    # 2. SiteTracker linked
    if st_state and st_state.upper() in CODES:
        return st_state.upper(), "st"
    if not name:
        return None, "none"
    # 3. Explicit 2-letter abbreviation (with strong-context guards)
    #    Prefer if preceded by a comma, or appears before a number, or in "[XX]"
    for m in STATE_ABBR_RE.finditer(name):
        code = m.group(1)
        if code not in CODES:
            continue
        start = m.start()
        preceding = name[max(0, start - 3) : start]
        # strong context: ", XX " or "(XX " or " XX,"
        if any(p in preceding for p in [", ", "[", "("]) or re.search(r"[A-Za-z]+ " + code + r"\b", name):
            # avoid "NE" as directional like "500 NE 70th"
            if code == "NE" and re.search(r"\d+\s+NE\s", name):
                continue
            return code, "name_abbr"
    # 4. Full state name in words (only if token matches whole word)
    lower = name.lower()
    for full, code in US_STATES.items():
        if re.search(r"\b" + re.escape(full.lower()) + r"\b", lower):
            # avoid street words that coincide (Washington Manor, Maryland Ave, etc.)
            # require context "of <state>" or "<city>, <state>" or state as last word
            if re.search(r"(?i)\bof " + re.escape(full) + r"\b", name):
                return code, "name_full"
            if re.search(r"(?i),\s*" + re.escape(full) + r"\b", name):
                return code, "name_full"
            if re.search(r"(?i)\b" + re.escape(full) + r"\s+(Solar|Spine|Health|Roofing|Seamless)\b", name):
                # "New Texas Solar Roofing" — state in business name, not location signal
                return None, "name_full_business"
            if lower.rstrip(".").endswith(full.lower()):
                return code, "name_full"
    # 5. City
    for city, code in CITY_TO_STATE.items():
        if re.search(r"(?i)\b" + re.escape(city) + r"\b", lower):
            return code, "city"
    return None, "none"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    sf = Salesforce(**CREDS)

    q = (
        "SELECT Id, Name, Property_City__c, AccountId, Account.BillingState "
        "FROM Opportunity WHERE Property_State__c = null"
    )
    rows = sf.query_all(q)["records"]
    print(f"Blank Property_State__c opps: {len(rows)}")

    # Fetch ST state for any linked project
    ids = [r["Id"] for r in rows]
    st_state: dict[str, str] = {}
    if ids:
        stq = (
            "SELECT Opportunity__c, State__c FROM SiteTracker_Project__c "
            "WHERE Opportunity__c IN ('{}')".format("','".join(ids))
        )
        for s in sf.query_all(stq)["records"]:
            if s.get("State__c"):
                st_state[s["Opportunity__c"]] = s["State__c"]

    proposals: list[dict] = []
    by_source = Counter()
    for r in rows:
        acct = (r.get("Account") or {}).get("BillingState") if r.get("Account") else None
        stt = st_state.get(r["Id"])
        code, source = infer_state(r.get("Name") or "", acct, stt)
        by_source[source] += 1
        proposals.append({
            "Id": r["Id"],
            "name": r.get("Name") or "",
            "account_state": acct or "",
            "st_state": stt or "",
            "inferred_state": code or "",
            "source": source,
        })

    print(f"\nInference sources: {dict(by_source)}")
    print(f"Total with an inferred state: {sum(1 for p in proposals if p['inferred_state'])}")
    print(f"Total without: {sum(1 for p in proposals if not p['inferred_state'])}")

    if not args.apply:
        with PROPOSALS.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Id", "name", "account_state", "st_state", "inferred_state", "source"])
            w.writeheader(); w.writerows(proposals)
        print(f"\nProposals: {PROPOSALS}")
        print("\n=== With inference ===")
        for p in proposals:
            if p["inferred_state"]:
                print(f"  {p['source']:6s} {p['inferred_state']}  {p['name']!r}")
        print("\n=== No signal (stay blank) ===")
        for p in proposals:
            if not p["inferred_state"]:
                print(f"  ----  {p['name']!r}")
        return

    # Apply — read back the CSV so user can override
    rows = list(csv.DictReader(PROPOSALS.open(encoding="utf-8")))
    to_update = [r for r in rows if r.get("inferred_state")]
    payload = [{"Id": r["Id"], "Property_State__c": r["inferred_state"]} for r in to_update]
    print(f"Applying {len(payload)}...")
    results = sf.bulk.Opportunity.update(payload, batch_size=2000)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rb = BACKUP / f"state_infer_rollback_{stamp}.csv"
    applied = []
    errs = []
    for r, res in zip(to_update, results):
        if res.get("success"):
            applied.append(r)
        else:
            errs.append((r["Id"], str(res.get("errors"))[:200]))
    with rb.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Id", "name", "account_state", "st_state", "inferred_state", "source"])
        w.writeheader(); w.writerows(applied)
    print(f"Applied {len(applied)}/{len(payload)}. Errors: {len(errs)}")
    for i, m in errs[:10]:
        print(f"  {i}  {m}")
    print(f"Rollback: {rb}")


if __name__ == "__main__":
    main()
