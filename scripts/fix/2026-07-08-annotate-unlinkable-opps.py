"""
Annotate the ~22 unlinkable Opps from "Not Linked to Site Tracker.xlsx" with a
Description note explaining WHY they can't link, classified against Vetro:
  - Vetro serviceable + fdh found  -> area/FDH-grain build, no per-Opp ST site (expected, see sfu-lit-fiber-build)
  - Vetro future_serviceable       -> in FDH area but not yet built
  - no Vetro as-built match         -> no ST site + no Vetro; confirm whether built (possible real gap)
Excludes 1471 Rubenstein (address data-quality, fix the address instead).

Note is APPEND-safe: prepends a tagged line, preserves existing Description.
Read-only until --apply. Resolves Opp Ids from SF by Name (+address disambiguation).
"""
import sys, argparse, re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import openpyxl
from simple_salesforce import Salesforce

sys.path.insert(0, str(Path(r"C:\Users\cass\Work_Projects\SalesForce\scripts\analysis")))
from lookup_agree_names_for_unlinked import house, st_tokens, norm_state
sys.path.insert(0, str(Path(r"C:\Users\cass\Work_Projects\Vetro\scripts\lib")))
from load_vetro import load_vetro

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
REPORT = Path(r"C:\Users\cass\AppData\Local\Temp\claude\C--Users-cass-Work-Projects\eb63bd25-744f-4859-9c80-939403c2cb8e\scratchpad\notlinked.xlsx")
TODAY = "2026-07-08"

def report_unlinkable():
    wb = openpyxl.load_workbook(REPORT, read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in list(ws.iter_rows(values_only=True))[1:] if r[0] not in (None, "")]
    seen, out = set(), []
    for r in rows:
        opp, addr, state, src, note = r[0], r[2], r[4], r[18], str(r[20] or "")
        if src not in (None, "None"):
            continue  # matched, skip
        if "only '1471'" in note or str(addr).strip() == "1471":
            continue  # data-quality exclusion
        key = str(opp).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(opp=str(opp).strip(), addr=str(addr or "").strip(), state=norm_state(state)))
    return out

def build_vetro_index():
    df = load_vetro(warn_if_stale_days=999)
    idx = defaultdict(list)      # (house, state) -> list(dict)
    stidx = defaultdict(list)    # (state) -> list for street-only fallback
    for hn, sn, ss, ct, stt, fdh, status, agn in zip(
            df.housenum, df.streetname, df.streetsuff, df.city, df.state,
            df.fdh, df.addrstatus, df.agreename):
        rec = dict(toks=st_tokens(f"{sn} {ss or ''}"), city=str(ct or ""),
                   fdh=str(fdh or "").strip(), status=str(status or "").strip(),
                   agn=str(agn or "").strip())
        h = str(hn).strip()
        if h and h.lower() != "nan":
            idx[(h, str(stt).strip().upper())].append(rec)
        stidx[str(stt).strip().upper()].append(rec)
    return idx, stidx

def classify(addr, state, idx, stidx):
    h = house(addr); gt = st_tokens(addr)
    cands = []
    for rec in idx.get((h, state), []):
        ov = gt & rec["toks"]
        if ov:
            cands.append((len(ov), rec))
    matched_by = "house+street"
    if not cands:  # street-only fallback within state
        for rec in stidx.get(state, []):
            ov = gt & rec["toks"]
            if len(ov) >= 2:
                cands.append((len(ov), rec))
        matched_by = "street-only"
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    best = cands[0][1]
    return dict(fdh=best["fdh"], status=best["status"], agn=best["agn"],
                city=best["city"], via=matched_by)

def fdh_label(c):
    fdh = c["fdh"] if c["fdh"] and c["fdh"].lower() != "nan" else None
    city = (c["city"] or "").strip().title()
    if fdh and city:
        return f"{city} {fdh}"
    return fdh or (f"the {city} area" if city else "its parent FDH area")

def make_note(c, state):
    if c is None:
        return ("no-vetro",
                f"[ST linking {TODAY}] Not linked to a SiteTracker project: no per-Opp ST Site "
                f"and no Vetro as-built match found. Confirm whether built - may be a genuine ST "
                f"project gap.")
    where = fdh_label(c)
    ca = (state == "CA")
    if c["status"] == "serviceable" and ca:
        # CA SoCal SFU footprint: area/FDH-grain is the known, expected pattern
        return ("ca-area-grain",
                f"[ST linking {TODAY}] Not linked to a SiteTracker project: no per-Opp ST Site exists. "
                f"Served at area/FDH grain (Vetro: {where}, serviceable). SoCal SFU builds are tracked "
                f"per-FDH on Lit_Fiber in the SiteTracker org, not per-Opp - expected here, not a build "
                f"gap. Verify against {where} if needed.")
    if c["status"] == "serviceable":
        # non-CA (MDU markets): service exists but a built property normally has its OWN ST project
        return ("nonca-serviceable-verify",
                f"[ST linking {TODAY}] Not linked to a SiteTracker project: no per-Opp ST Site. Vetro "
                f"shows fiber service in {where} (serviceable), but this market normally tracks each "
                f"built property as its own ST project - confirm whether an ST project exists under a "
                f"different name, or if this is a genuine gap.")
    if c["status"] == "future_serviceable":
        return ("fdh-planned",
                f"[ST linking {TODAY}] Not linked to a SiteTracker project: no per-Opp ST Site. In "
                f"{where} but Vetro status is future_serviceable (planned, not yet built). Confirm build "
                f"completion before treating as active.")
    return ("area-other",
            f"[ST linking {TODAY}] Not linked to a SiteTracker project: no per-Opp ST Site. Vetro shows "
            f"{where} (status {c['status'] or 'unknown'}); confirm whether an ST project should exist.")

def main():
    apply = argparse.ArgumentParser(); apply.add_argument("--apply", action="store_true")
    apply = apply.parse_args().apply
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

    targets = report_unlinkable()
    print(f"{len(targets)} distinct unlinkable Opps from report (1471 excluded)\n")
    print("loading Vetro...")
    idx, stidx = build_vetro_index()

    names = "','".join(t["opp"].replace("'", "\\'") for t in targets)
    opps = sf.query_all(
        f"SELECT Id, Name, Property_Address__c, Property_State__c, Description "
        f"FROM Opportunity WHERE Name IN ('{names}')")["records"]
    by_name = defaultdict(list)
    for o in opps:
        by_name[o["Name"]].append(o)

    plan, unresolved = [], []
    for t in targets:
        matches = by_name.get(t["opp"], [])
        if len(matches) != 1:
            unresolved.append((t, len(matches))); continue
        o = matches[0]
        c = classify(t["addr"] or o["Property_Address__c"], t["state"], idx, stidx)
        bucket, note = make_note(c, t["state"])
        plan.append((o, bucket, note, c))

    print(f"\n=== proposed notes ({len(plan)} resolved) ===")
    for o, bucket, note, c in sorted(plan, key=lambda x: x[1]):
        via = f"via {c['via']}" if c else "no-vetro-match"
        print(f"\n[{bucket}] {o['Name'][:34]}  ({o['Property_State__c']})  {str(o['Property_Address__c'])[:30]}  [{via}]")
        print(f"   {note}")
    if unresolved:
        print(f"\n=== UNRESOLVED (name matched {'/'.join(str(n) for _,n in unresolved)} Opps - skipped) ===")
        for t, n in unresolved:
            print(f"   {t['opp']}  ({n} SF matches)")

    from collections import Counter
    print("\nbucket counts:", dict(Counter(b for _, b, _, _ in plan)))
    if not apply:
        print("\nDRY RUN - pass --apply to write Description notes."); return

    print("\nwriting (append-safe)...")
    import csv
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    audit = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs") / f"2026-07-08-unlinkable-opp-notes-{stamp}.csv"
    audit.parent.mkdir(parents=True, exist_ok=True)
    rows_written = []
    for o, bucket, note, c in plan:
        existing = o.get("Description") or ""
        if "[ST linking" in existing:
            print(f"  SKIP {o['Name']} (already annotated)"); continue
        newval = note if not existing.strip() else f"{note}\n\n{existing}"
        sf.Opportunity.update(o["Id"], {"Description": newval})
        rows_written.append(dict(SF_Id=o["Id"], Name=o["Name"], Field="Description",
                                 Before=existing, After=newval, Bucket=bucket,
                                 Source="2026-07-08-annotate-unlinkable-opps.py",
                                 Timestamp=datetime.now().isoformat(), Action="update"))
        print(f"  {o['Name'][:36]:36} [{bucket}]")
    with audit.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["SF_Id","Name","Field","Before","After","Bucket","Source","Timestamp","Action"])
        w.writeheader(); w.writerows(rows_written)
    print(f"\naudit log ({len(rows_written)} rows) -> {audit}")

if __name__ == "__main__":
    main()
