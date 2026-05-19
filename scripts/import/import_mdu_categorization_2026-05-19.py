"""Map 'MDU Categorization' (OnNet/OffNet/NearNet) from
'Signed MDU Agreement Analysis V1.xlsx' (sheet 'Signed MDUs') into
Opportunity.MDU_Categorization__c.

Matching (per source row -> Opportunity):
  1. source Monday.com name -> SiteTracker_Project__c.Monday_Name__c -> Opportunity__c link
  2. fallback: source Monday.com name -> Opportunity.Name (exact, case-insensitive)
Unmatched rows get name-substring candidate suggestions (reported, never auto-written).

Default is DRY RUN: writes a preview CSV + a rollback snapshot, no SF writes.
Pass --apply to perform the live update (also writes an audit log).

  python import_mdu_categorization_2026-05-19.py            # dry run
  python import_mdu_categorization_2026-05-19.py --apply    # live
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl
from simple_salesforce import Salesforce

SRC = r"C:\Users\cass\Downloads\Signed MDU Agreement Analysis V1.xlsx"
SHEET = "Signed MDUs"
FIELD = "MDU_Categorization__c"
VALID = {"OnNet", "OffNet", "NearNet"}

# Confident manual recoveries for rows that don't auto-match via ST link / Opp Name.
# Keyed by source Site Name -> explicit Opportunity Id(s). One source row may map to
# more than one Opp (e.g. a combined "A & B" pursuit split into two SF Opps).
MANUAL_OVERRIDES = {
    "Solana Beach_MDU_Santa Helena Park Condominiums": ["006WR00000wkA8kYAE"],
    "Omaha_MDU_Farnam Flats": ["006WR00000y46nRYAQ"],
    "Killeen_SFU_Southern Hills MHP": ["006WR00000wkEbFYAU"],
    "Killeen_MDU_1807 Mulford & 1810 N 8th St": ["006WR00000wkEbUYAU", "006WR000013P1ulYAC"],
}

ROOT = Path(__file__).resolve().parents[2]            # SalesForce/
OUT_DIR = ROOT / "data" / "output"
AUDIT_DIR = OUT_DIR / "audit_logs"
STAMP = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def load_creds():
    creds = {}
    p = ROOT / "api" / "Salesforce_Credentials.txt"
    for line in p.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            creds[k.strip().lower()] = v.strip()
    return creds


def load_source():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb[SHEET]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(v is not None for v in r):
            continue
        out.append({
            "project_id": (str(r[0]).strip() if r[0] else ""),
            "site_name": (str(r[3]).strip() if r[3] else ""),
            "mdu_cat": (str(r[8]).strip() if r[8] else ""),
            "monday_name": (str(r[13]).strip() if r[13] else ""),
            "full_address": (str(r[16]).strip() if r[16] else ""),
        })
    return out


def main(apply: bool):
    sys.stdout.reconfigure(line_buffering=True)
    src = load_source()
    print(f"[INFO] {len(src)} source rows")

    # Validate categorization values up front
    bad = [s for s in src if s["mdu_cat"] and s["mdu_cat"] not in VALID]
    if bad:
        print(f"[WARN] {len(bad)} rows have unexpected categorization values:")
        for s in bad[:20]:
            print(f"   {s['project_id']} {s['site_name']} -> {s['mdu_cat']!r}")

    print("[INFO] Connecting to Salesforce...")
    c = load_creds()
    sf = Salesforce(username=c["username"], password=c["password"],
                    security_token=c["security token"])

    print("[INFO] Pulling SiteTracker projects...")
    st = sf.query_all(
        "SELECT Id, Name, Monday_Name__c, Opportunity__c "
        "FROM SiteTracker_Project__c"
    )["records"]
    print(f"[INFO] {len(st)} SiteTracker projects")

    print("[INFO] Pulling Opportunities...")
    opp = sf.query_all(
        f"SELECT Id, Name, Agreement_Name__c, {FIELD} FROM Opportunity"
    )["records"]
    print(f"[INFO] {len(opp)} Opportunities")

    opp_by_id = {o["Id"]: o for o in opp}

    # Indexes (detect duplicates so we never silently pick the wrong record)
    st_by_monday = defaultdict(list)
    for s in st:
        if s.get("Monday_Name__c"):
            st_by_monday[s["Monday_Name__c"].strip().lower()].append(s)
    opp_by_name = defaultdict(list)
    for o in opp:
        if o.get("Name"):
            opp_by_name[o["Name"].strip().lower()].append(o)

    def resolve(row):
        """Return (opp_id, matched_via, note). opp_id None if unresolved.
        Returns a list of (opp_id, via, note) to support 1-row -> N-Opp overrides."""
        ov = MANUAL_OVERRIDES.get(row["site_name"])
        if ov:
            return [(oid, "manual", "manual override") for oid in ov]
        mn = row["monday_name"].strip().lower()
        # 1. SiteTracker link
        if mn:
            sts = st_by_monday.get(mn, [])
            linked = [s for s in sts if s.get("Opportunity__c")]
            if len(linked) == 1:
                return [(linked[0]["Opportunity__c"], "ST link", "")]
            if len(linked) > 1:
                opp_ids = {s["Opportunity__c"] for s in linked}
                if len(opp_ids) == 1:
                    return [(linked[0]["Opportunity__c"], "ST link", "multiple ST rows, same Opp")]
                return [(None, "", f"AMBIGUOUS: {len(linked)} ST rows -> {len(opp_ids)} Opps")]
        # 2. Opp Name fallback
        if mn:
            os_ = opp_by_name.get(mn, [])
            if len(os_) == 1:
                return [(os_[0]["Id"], "Opp Name", "")]
            if len(os_) > 1:
                return [(None, "", f"AMBIGUOUS: {len(os_)} Opps named {row['monday_name']!r}")]
        return [(None, "", "no match")]

    def candidates(row):
        """Name-substring candidate Opps for an unmatched row (reporting only)."""
        keys = []
        if row["monday_name"]:
            keys.append(row["monday_name"].strip().lower())
        # descriptive tail of site name e.g. Solana Beach_MDU_Santa Helena... -> last segment
        if row["site_name"] and "_" in row["site_name"]:
            keys.append(row["site_name"].split("_")[-1].strip().lower())
        hits = {}
        for name_l, recs in opp_by_name.items():
            for k in keys:
                if k and (k in name_l or name_l in k):
                    for o in recs:
                        hits[o["Id"]] = o["Name"]
        return hits

    # Resolve all rows
    preview = []
    resolved_count = 0
    target = {}  # opp_id -> list of (source_cat, row) for conflict detection
    unmatched = []
    for row in src:
        if not row["mdu_cat"]:
            preview.append({**row, "opp_id": "", "opp_name": "", "matched_via": "",
                            "current_value": "", "new_value": "", "will_change": "",
                            "note": "source has no categorization"})
            continue
        matches = resolve(row)
        if matches and matches[0][0] is None:
            note = matches[0][2]
            cands = candidates(row)
            cand_str = "; ".join(f"{v} ({k})" for k, v in list(cands.items())[:5])
            unmatched.append({**row, "candidates": cand_str, "note": note})
            preview.append({**row, "opp_id": "", "opp_name": "", "matched_via": "",
                            "current_value": "", "new_value": row["mdu_cat"],
                            "will_change": "NO-UNMATCHED",
                            "note": (note + (" | candidates: " + cand_str if cand_str else ""))})
            continue
        resolved_count += 1
        for opp_id, via, note in matches:
            o = opp_by_id.get(opp_id, {})
            cur = o.get(FIELD) or ""
            will = "yes" if cur != row["mdu_cat"] else "no (already set)"
            target.setdefault(opp_id, []).append((row["mdu_cat"], row))
            preview.append({**row, "opp_id": opp_id, "opp_name": o.get("Name", ""),
                            "matched_via": via, "current_value": cur,
                            "new_value": row["mdu_cat"], "will_change": will, "note": note})

    # Conflict detection: same Opp targeted with differing values
    conflicts = {oid: vals for oid, vals in target.items()
                 if len({v for v, _ in vals}) > 1}

    # ---- Write preview + rollback ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    preview_path = OUT_DIR / f"mdu_categorization_preview_{STAMP}.csv"
    cols = ["project_id", "site_name", "monday_name", "full_address", "mdu_cat",
            "opp_id", "opp_name", "matched_via", "current_value", "new_value",
            "will_change", "note"]
    with preview_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(preview)

    # Rollback snapshot of every targeted Opp's current value
    rollback_path = OUT_DIR / f"mdu_categorization_rollback_{STAMP}.csv"
    with rollback_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opp_id", "opp_name", "field", "prior_value"])
        for oid in target:
            o = opp_by_id.get(oid, {})
            w.writerow([oid, o.get("Name", ""), FIELD, o.get(FIELD) or ""])

    # Updates to perform (skip unchanged + conflicts)
    to_update = []
    for oid, vals in target.items():
        if oid in conflicts:
            continue
        new_val = vals[0][0]
        cur = opp_by_id.get(oid, {}).get(FIELD) or ""
        if cur != new_val:
            to_update.append((oid, cur, new_val))

    # ---- Summary ----
    via_counter = Counter(p["matched_via"] for p in preview if p["matched_via"])
    print("\n========== DRY RUN SUMMARY ==========" if not apply else "\n========== APPLY SUMMARY ==========")
    print(f"Source rows:            {len(src)}")
    print(f"Resolved to Opp:        {resolved_count}")
    for k, v in via_counter.items():
        print(f"   via {k}: {v}")
    print(f"Unique Opps targeted:   {len(target)}")
    print(f"Will change value:      {len(to_update)}")
    print(f"Already correct:        {len(target) - len(to_update) - len(conflicts)}")
    print(f"Conflicts (skipped):    {len(conflicts)}")
    print(f"Unmatched rows:         {len(unmatched)}")
    print(f"\nPreview:  {preview_path}")
    print(f"Rollback: {rollback_path}")

    if conflicts:
        print("\n[CONFLICTS] same Opp, differing categorization (NOT written):")
        for oid, vals in conflicts.items():
            o = opp_by_id.get(oid, {})
            vset = ", ".join(sorted({v for v, _ in vals}))
            print(f"   {o.get('Name','?')} ({oid}): {vset}")

    if unmatched:
        print(f"\n[UNMATCHED] {len(unmatched)} rows (need manual review):")
        for u in unmatched:
            print(f"   {u['project_id']:>10} | {u['site_name']} | monday={u['monday_name']!r} | {u['mdu_cat']}")
            if u["candidates"]:
                print(f"        candidates: {u['candidates']}")

    if not apply:
        print("\n[DRY RUN] No SF writes. Review preview, then re-run with --apply.")
        return

    # ---- APPLY ----
    if not to_update:
        print("\n[APPLY] Nothing to change. Done.")
        return
    print(f"\n[APPLY] Updating {len(to_update)} Opportunities...")
    audit_path = AUDIT_DIR / f"mdu_categorization_applied_{STAMP}.csv"
    ok = err = 0
    with audit_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
        for oid, before, after in to_update:
            name = opp_by_id.get(oid, {}).get("Name", "")
            try:
                sf.Opportunity.update(oid, {FIELD: after})
                ok += 1
                w.writerow([oid, name, FIELD, before, after,
                            "Signed MDU Agreement Analysis V1.xlsx", STAMP, "update"])
            except Exception as e:
                err += 1
                print(f"   [ERROR] {name} ({oid}): {e}")
    print(f"\n[DONE] Updated: {ok}, Errors: {err}")
    print(f"Audit log: {audit_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Perform live SF update")
    main(ap.parse_args().apply)
