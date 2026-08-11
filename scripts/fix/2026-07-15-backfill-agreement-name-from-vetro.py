"""
Backfill Opportunity.Agreement_Name__c from Vetro for TX/NE MDU/SFU Opps where it is BLANK.

Agreement_Name__c is the cross-system linking key (== Vetro agreename == SiteTracker Site.Name),
and it feeds the daily ST-linking automation - so we fill ONLY on a 100% match, defined as two
independent signals agreeing:
  1. ADDRESS: the Opp's Property_Address__c resolves to EXACTLY ONE Vetro agreename by
     house# (exact) + city (exact) + a shared distinctive street token.
  2. NAME: the Opp Name is equal to / a subset of that agreename's property name (digit-sets
     must agree). "The Mill" -> "The Mill Apartments" passes; "Stone Vista" -> "Stone Ranch"
     and "Riverside Apartments" -> "Riverside Villas" are rejected.
Both must hold. Each filled Opp also gets a Note recording that it was filled from Vetro.

Dry-run by default. --write snapshots (rollback), updates, adds the Note, and audits.
"""
import argparse
import base64
import csv
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
sys.path.insert(0, r"C:\Users\cass\Work_Projects\Vetro\scripts\lib")
from enrich_omaha_onnet_mdus import creds  # noqa: E402
from lookup_agree_names_for_unlinked import house, st_tokens, norm_name  # noqa: E402
from simple_salesforce import Salesforce  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from load_vetro import load_vetro, service_locations  # noqa: E402

OUT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
SNAP = OUT / "2026-07-15-agreename-backfill-rollback-snapshot.csv"
AUDIT = OUT / "2026-07-15-agreename-backfill-audit.csv"
NOTE_BODY = ("Agreement_Name__c filled 2026-07-15 based on address lookup in Vetro "
             "(Property Address matched to the Vetro building footprint; agreename applied).")

ncity = lambda s: re.sub(r"[^a-z]", "", (s or "").lower())
GEN = {"creek", "park", "ridge", "oak", "oaks", "hill", "hills", "valley", "lake", "trail",
       "trl", "ranch", "village", "apartments", "apartment", "apts", "the", "and", "at", "of"}


def stoks(a):
    return {t for t in st_tokens(a) if not t.isdigit() and len(t) >= 3}


def prop_part(s):
    parts = re.split(r"_(?:MDU|SFU|BUS|MTU)_", s or "", flags=re.I, maxsplit=1)
    return parts[1] if len(parts) > 1 else (s or "")


def ntoks(s):
    # RAW tokens, not norm_name: norm_name strips "apartments" but not "villas", which would
    # let "Riverside Apartments" == "Riverside Villas" through. Raw keeps the type word so the
    # subset test rejects a type mismatch while still passing "The Mill" subset of "The Mill Apts".
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def nums(toks):
    return {t for t in toks if any(c.isdigit() for c in t)}


def name_matches(sf_name, agreename):
    """SF name == or subset-of the agreename's property name, digit tokens must agree."""
    a, s = ntoks(prop_part(agreename)), ntoks(sf_name)
    if not a or not s or nums(a) != nums(s):
        return False
    return s <= a or a <= s


def existing_agreenames(sf):
    """Every Agreement_Name__c already in use (lowercased). Filling a blank Opp with an
    agreename that ALREADY exists on another Opp would create a duplicate linking key - the
    blank Opp is probably a duplicate of that record, so we skip it instead."""
    got = set()
    for r in sf.query_all("SELECT Agreement_Name__c FROM Opportunity "
                          "WHERE Agreement_Name__c != null")["records"]:
        got.add((r["Agreement_Name__c"] or "").strip().lower())
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    sf = Salesforce(*creds())
    q = ("SELECT Id, Name, Property_Address__c, Property_City__c FROM Opportunity WHERE "
         "Property_State__c IN ('TX','Texas','NE','Nebraska') AND RecordType.Name='MDU/SFU' "
         "AND Agreement_Name__c = null AND Property_Address__c != null")
    opps = sf.query_all(q)["records"]
    print(f"blank-agreename TX/NE MDU/SFU Opps: {len(opps)}")

    v = service_locations(load_vetro())
    v = v[v.state.isin(["TX", "NE"])]
    face = defaultdict(lambda: defaultdict(set))  # (house, city) -> {agreename: streettokens}
    for agn, hn, sn, sfx, city in zip(v.agreename, v.housenum, v.streetname, v.streetsuff, v.city):
        a = str(agn)
        if a in ("nan", "None", "") or str(hn) in ("nan", "None", ""):
            continue
        face[(str(hn), ncity(city))][a] |= stoks(f"{sn} {sfx}")

    fills, rejected_name, ambiguous, nohit = [], [], 0, 0
    for o in opps:
        oaddr = o["Property_Address__c"] or ""
        oh, oc, ot = house(oaddr), ncity(o.get("Property_City__c")), stoks(oaddr)
        if not oh:
            nohit += 1
            continue
        cands = set()
        for agn, toks in face.get((oh, oc), {}).items():
            shared = ot & toks
            if shared and any(t not in GEN for t in shared):  # distinctive shared street token
                cands.add(agn)
        if len(cands) != 1:
            if len(cands) > 1:
                ambiguous += 1
            else:
                nohit += 1
            continue
        agn = next(iter(cands))
        if name_matches(o["Name"], agn):
            fills.append((o, agn))
        else:
            rejected_name.append((o, agn))

    # ---- duplicate guard: never assign an agreename that already exists on another Opp, and
    # never assign the same agreename to two blank Opps in this batch ----
    from collections import Counter
    existing = existing_agreenames(sf)
    batch_ct = Counter(agn for _, agn in fills)
    safe, dup_skip = [], []
    for o, agn in fills:
        if agn.strip().lower() in existing:
            dup_skip.append((o, agn, "agreename already on another Opp (likely duplicate)"))
        elif batch_ct[agn] > 1:
            dup_skip.append((o, agn, "2+ blank Opps resolve to this agreename (likely duplicates)"))
        else:
            safe.append((o, agn))
    fills = safe

    print(f"  100% match (address-unique + name agrees): {len(fills) + len(dup_skip)}")
    print(f"    -> SAFE to fill (agreename not already used): {len(fills)}")
    print(f"    -> SKIPPED as would-be duplicate agreename: {len(dup_skip)}")
    print(f"  rejected on NAME (address unique but name diverges): {len(rejected_name)}")
    print(f"  ambiguous (>1 agreename): {ambiguous}   |   no unique address hit: {nohit}")
    if dup_skip:
        print(f"\n--- SKIPPED (would duplicate an existing agreename) ---")
        for o, agn, why in dup_skip:
            print(f"  {o['Name'][:34]:34} @ {str(o['Property_Address__c'])[:24]:24} -> {agn}  [{why}]")
    print(f"\n--- {len(fills)} to fill ---")
    for o, agn in sorted(fills, key=lambda x: x[1]):
        print(f"  {o['Name'][:34]:34} @ {str(o['Property_Address__c'])[:30]:30} -> {agn}")
    print(f"\n--- rejected on name (NOT filled) ---")
    for o, agn in rejected_name[:25]:
        print(f"  {o['Name'][:34]:34} @ {str(o['Property_Address__c'])[:26]:26} -> {agn}")

    if not args.write:
        print(f"\nDRY-RUN. Re-run with --write to fill {len(fills)} + add notes.")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    with SNAP.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "old_Agreement_Name__c", "new_Agreement_Name__c", "matched_address"])
        for o, agn in fills:
            w.writerow([o["Id"], o["Name"], "", agn, o["Property_Address__c"]])
    print(f"\nsnapshot (rollback) written: {SNAP}")

    audit, ok, err, notes_ok, notes_err = [], 0, 0, 0, 0
    for o, agn in fills:
        try:
            sf.Opportunity.update(o["Id"], {"Agreement_Name__c": agn})
            ok += 1
            note_result = "note-skip"
            try:
                res = sf.ContentNote.create({
                    "Title": "Agreement Name backfilled from Vetro",
                    "Content": base64.b64encode(f"<p>{NOTE_BODY} Value: {agn}</p>".encode()).decode()})
                sf.ContentDocumentLink.create({
                    "ContentDocumentId": res["id"], "LinkedEntityId": o["Id"],
                    "ShareType": "V", "Visibility": "AllUsers"})
                notes_ok += 1
                note_result = "note-ok"
            except Exception as ne:
                notes_err += 1
                note_result = f"note-ERROR: {ne}"
            audit.append([o["Id"], o["Name"], agn, "OK", note_result])
        except Exception as e:
            err += 1
            audit.append([o["Id"], o["Name"], agn, f"ERROR: {e}", "-"])
            print(f"  ERROR {o['Id']} {o['Name']}: {e}")
    with AUDIT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "Agreement_Name__c_set", "update_result", "note_result"])
        w.writerows(audit)
    print(f"\nAgreement_Name__c set: {ok}  |  errors: {err}")
    print(f"notes added: {notes_ok}  |  note errors: {notes_err}")
    print(f"audit: {AUDIT}\nrollback: null Agreement_Name__c on the Ids in {SNAP}")


if __name__ == "__main__":
    main()
