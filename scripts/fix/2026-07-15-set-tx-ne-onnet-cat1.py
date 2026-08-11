"""
Set Property_Category__c = 'Cat 1' on the TX+NE On-Net MDU Opportunities (Niraj's ask,
2026-07-15: everything on his on-net list should be Cat 1).

WHY authoritative-only: the enrichment matcher's rep choice is NOT safe to drive a prod
write - its plain-address stage can match a coincidental house# + shared street token across
cities (Turkey Creek Trl, Bridgeport -> "Cedar Park Apartments", Cedar Park; Indian Creek
Duplexes -> "302 North", Georgetown), and pick() can prefer a coincidental active match over
the real one. So the WRITE set comes only from two authoritative signals:
  1. SF Opportunity.Agreement_Name__c == a Niraj Site Name (the linking key), or
  2. a Vetro building-footprint match (specific Opp Id, authoritative building).
Everything matched by plain address / near / name-fuzzy is HELD and printed for manual verify.

Dry-run by default. --write snapshots current values to a rollback CSV, then updates, then
writes an audit log. Rollback = restore Property_Category__c from the snapshot CSV.

Usage:
    python 2026-07-15-set-tx-ne-onnet-cat1.py            # dry-run (default)
    python 2026-07-15-set-tx-ne-onnet-cat1.py --write    # snapshot + update + audit
"""
import argparse
import csv
import sys
from pathlib import Path
from collections import Counter, defaultdict

import re
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from enrich_omaha_onnet_mdus import creds  # noqa: E402
from lookup_agree_names_for_unlinked import norm_name, numset, house, st_tokens  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402
from simple_salesforce import Salesforce  # noqa: E402

STOP_ST = {"tx", "texas", "ne", "nebraska", "usa", "us"}


def city_prefix(site):
    parts = re.split(r"_(?:MDU|SFU|BUS|MTU)_", site or "", flags=re.I, maxsplit=1)
    return parts[0] if len(parts) > 1 else ""


def street_set(a, stop):
    # city tokens must be stripped: st_tokens keeps the city inconsistently between Niraj's
    # "... Omaha, NE" and SF's "... OMAHA NE ...", which would break the subset test on the city
    return {t for t in st_tokens(a) if not t.isdigit()} - stop


def prop_part(s):
    parts = re.split(r"_(?:MDU|SFU|BUS|MTU)_", s or "", flags=re.I, maxsplit=1)
    return parts[1] if len(parts) > 1 else (s or "")


def name_corroborated(site, monday, sf_name):
    """True if the SF Opp NAME independently matches the property name (a second signal
    on top of the address match). Digit-sets must agree, so 1019 N College != 119 N College,
    and a name swap (Turkey Creek -> Cedar Park) is rejected."""
    sfn = norm_name(sf_name)
    if not sfn:
        return False
    for c in (prop_part(site), monday or ""):
        cn = norm_name(c)
        if not cn or numset(cn) != numset(sfn):
            continue
        if cn == sfn or min(fuzz.token_set_ratio(cn, sfn), fuzz.ratio(cn, sfn)) >= 90:
            return True
    return False

CSV = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\2026-07-15-tx-ne-onnet-mdus-sf-enrichment.csv")
OUT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output")
AUDIT_DIR = OUT / "audit_logs"
SNAP = OUT / "audit_logs" / "2026-07-15-tx-ne-cat1-rollback-snapshot.csv"
AUDIT = OUT / "audit_logs" / "2026-07-15-tx-ne-cat1-write-audit.csv"
TARGET = "Cat 1"
FIELDS = ("Id, Name, Agreement_Name__c, Property_Category__c, Property_City__c, "
          "Property_State__c, Property_Address__c, StageName")


def soql_in(sf, names):
    """Opps whose Agreement_Name__c is exactly one of `names` (apostrophes escaped)."""
    got = {}
    names = sorted(set(names))
    for i in range(0, len(names), 200):
        vals = "','".join(n.replace("\\", "\\\\").replace("'", "\\'") for n in names[i:i + 200])
        for o in sf.query_all(f"SELECT {FIELDS} FROM Opportunity "
                              f"WHERE Agreement_Name__c IN ('{vals}')")["records"]:
            got[o["Id"]] = o
    return got


def fetch_by_ids(sf, ids):
    got = {}
    ids = sorted(i for i in ids if i)
    for i in range(0, len(ids), 300):
        vals = "','".join(ids[i:i + 300])
        for o in sf.query_all(f"SELECT {FIELDS} FROM Opportunity WHERE Id IN ('{vals}')")["records"]:
            got[o["Id"]] = o
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="perform the update (default: dry-run)")
    args = ap.parse_args()

    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    site_names = [r["Site Name"] for r in rows]
    sf = Salesforce(*creds())

    # ---- signal 1: exact Agreement_Name__c ----
    by_agn = soql_in(sf, site_names)
    reason = {i: "agree-name" for i in by_agn}
    # ---- signal 2: Vetro building-footprint matches (from the enrichment) ----
    for i in {r["_sf_id"] for r in rows if "vetro-footprint" in r["_match"] and r["_sf_id"]}:
        reason.setdefault(i, "vetro-footprint")
    # ---- signal 3: address match CORROBORATED by a matching SF Opp name (two signals) ----
    promoted = 0
    for r in rows:
        sid = r["_sf_id"]
        if (r["In Salesforce"] == "YES" and sid and sid not in reason
                and name_corroborated(r["Site Name"], r["Monday.com name"], r["Property Name (SF)"])):
            reason[sid] = "address+name"
            promoted += 1

    # ---- signal 4: plain-address match where Niraj's FULL street name is a subset of the SF
    # Opp's address (same building, SF just named it with an FDH code / truncated name). The
    # subset test excludes Turkey Creek Trl -> Cypress Creek Rd (streets differ). Verified 8. ----
    addr_ids = {r["_sf_id"] for r in rows
                if r["In Salesforce"] == "YES" and r["_sf_id"] and r["_sf_id"] not in reason
                and "address" in r["_match"]}
    addr_opp = fetch_by_ids(sf, addr_ids)
    row_by_id = {r["_sf_id"]: r for r in rows if r["_sf_id"] in addr_ids}
    # place tokens = state + every city that appears (site-name prefix + SF city), so the
    # street comparison is street-name-only
    place = set(STOP_ST)
    for r in rows:
        place |= {t for t in re.findall(r"[a-z]+", city_prefix(r["Site Name"]).lower())}
    for o in addr_opp.values():
        place |= {t for t in re.findall(r"[a-z]+", (o.get("Property_City__c") or "").lower())}
    promoted_addr = 0
    for sid, o in addr_opp.items():
        r = row_by_id[sid]
        oaddr = o["Property_Address__c"] or ""
        ns = street_set(r["Full Address"], place)
        if (house(r["Full Address"]) and house(r["Full Address"]) == house(oaddr)
                and ns and ns <= street_set(oaddr, place)):
            reason[sid] = "address-exact"
            promoted_addr += 1

    authoritative = fetch_by_ids(sf, set(reason))
    print(f"trusted Opps  |  agree-name {sum(v=='agree-name' for v in reason.values())} "
          f"+ vetro {sum(v=='vetro-footprint' for v in reason.values())} "
          f"+ address+name {promoted} + address-exact {promoted_addr}  =  {len(authoritative)}")
    print(f"  current category dist: {dict(Counter(o['Property_Category__c'] or '(blank)' for o in authoritative.values()))}")

    to_change = [o for o in authoritative.values() if (o["Property_Category__c"] or "") != TARGET]
    print(f"\nWILL SET TO '{TARGET}': {len(to_change)} Opps")
    for k, n in Counter(o["Property_Category__c"] or "(blank)" for o in to_change).most_common():
        print(f"    from {k:9}: {n}")
    for o in to_change:
        if (o["Property_Category__c"] or "") != "":  # show the non-blank (deliberate) overwrites
            print(f"      OVERWRITE {o['Property_Category__c']} -> {TARGET}: {o['Name'][:34]:34} "
                  f"({o['Agreement_Name__c']}) [{o['StageName']}]  via {reason[o['Id']]}")

    # ---- held for manual verify: matched non-Cat1 rows with only a weak/uncorroborated match ----
    held = [r for r in rows
            if (r["Category (SF)"] or "") != TARGET and r["_sf_id"] not in reason
            and r["Site Name"].lower() not in {(o["Agreement_Name__c"] or "").lower() for o in authoritative.values()}]
    print(f"\nHELD for manual verify ({len(held)} rows - name did NOT corroborate the address "
          f"match, or REVIEW/MISSING; NOT written):")
    for r in sorted(held, key=lambda r: -int(r["Total Units"])):
        print(f"    {r['In Salesforce']:6} [{r['_match'][:16]:16}] {r['Site Name'][:38]:38} "
              f"u={r['Total Units']:<4} SFcat={r['Category (SF)'] or 'blank'} -> {r['Property Name (SF)'][:26]}")

    if not args.write:
        print(f"\nDRY-RUN. Re-run with --write to snapshot + update {len(to_change)} Opps.")
        return

    # ---- snapshot (rollback point) ----
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with SNAP.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Agreement_Name__c", "old_Property_Category__c"])
        for o in to_change:
            w.writerow([o["Id"], o["Name"], o["Agreement_Name__c"], o["Property_Category__c"] or ""])
    print(f"\nsnapshot (rollback) written: {SNAP}")

    # ---- update ----
    audit = []
    ok = err = 0
    for o in to_change:
        try:
            sf.Opportunity.update(o["Id"], {"Property_Category__c": TARGET})
            ok += 1
            audit.append([o["Id"], o["Name"], o["Agreement_Name__c"],
                          o["Property_Category__c"] or "", TARGET, "OK"])
        except Exception as e:
            err += 1
            audit.append([o["Id"], o["Name"], o["Agreement_Name__c"],
                          o["Property_Category__c"] or "", TARGET, f"ERROR: {e}"])
            print(f"  ERROR {o['Id']} {o['Name']}: {e}")
    with AUDIT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Agreement_Name__c", "old_category", "new_category", "result"])
        w.writerows(audit)
    print(f"\nupdated OK: {ok}  |  errors: {err}")
    print(f"audit written: {AUDIT}")
    print(f"rollback: restore old_Property_Category__c from {SNAP}")


if __name__ == "__main__":
    main()
