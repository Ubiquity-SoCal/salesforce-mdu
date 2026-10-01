"""MDU / AVR / California summary for Koa, 2026-09-28.

Every figure comes from LOCAL SNAPSHOT DATA. Nothing is pulled live.

Each metric is reported twice: all time, and 2026 year to date.

  MDUs done      Opportunity RecordType MDU/SFU at stage PAL/ROE Complete,
                 Marketing/Bulk In Progress or Marketing/Bulk Complete.
                 The YEAR comes from the latest signed agreement on the
                 opportunity, NOT from CloseDate: a Flow auto-populates
                 CloseDate on insert, so it is a creation date and dating
                 completions by it is wrong.
  AVRs           Salesforce Cases whose subject matches 'AVR Request Created'.
                 Year from CreatedDate.
  ROEs / PALs    Agreement__c. "Signed" = Status in (Completed, Cancelled) AND
                 a Signed Date present. Cancelled counts because a
                 signed-then-cancelled contract was still signed. Year from
                 the signed date.
  CA passed      A point-in-time STATE, so it has no year dimension at all.
                 Reported once, with both Vetro signals, because they disagree
                 by design and neither alone is "homes passed".
  CA activations Address-level circuit flags carry no date, so only the
                 serving-area activation milestone can be split by year.

Sources, all local:
  Property_Lookup/data/index/lookup-index.sqlite    SF Opps + Agreements, 2026-09-28
  AVR_Request_Form/tests/fixtures/omnia-cases.json  AVR Cases, pulled 2026-09-11
  Vetro/data/snapshot/vetro-unified.parquet         Vetro, data as of 2026-09-25
  Vetro/data/output/ca-fdh-build-status-map-2026-09-25.html  area activation

Writes SalesForce/data/output/2026-09-28-mdu-avr-ca-summary.json.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sqlite3
import sys

# SalesForce is a git submodule, so there are two roots: the submodule (where
# output belongs) and Work_Projects (where the sibling projects live). Reaching
# across follows lookup_agree_names_for_unlinked.py.
SF_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORK = pathlib.Path(__file__).resolve().parents[3]
INDEX = WORK / "Property_Lookup" / "data" / "index" / "lookup-index.sqlite"
AVR = WORK / "AVR_Request_Form" / "tests" / "fixtures" / "omnia-cases.json"
MAP = (WORK / "Vetro" / "data" / "output"
       / "ca-fdh-build-status-map-2026-09-25.html")
OUT = SF_ROOT / "data" / "output" / "2026-09-28-mdu-avr-ca-summary.json"

sys.path.insert(0, str(WORK / "Vetro" / "scripts" / "lib"))
sys.path.insert(0, str(WORK / "Property_Lookup" / "scripts" / "lib"))
# The AVR state only exists inside the parsed email body and it is dirty: TX,
# Tx, tx and "TEXAS" spelled out all appear. Reuse Property_Lookup's own table.
from address import STATES, STATE_BY_NAME  # noqa: E402

DONE_STAGES = {"PAL/ROE Complete", "Marketing/Bulk In Progress",
               "Marketing/Bulk Complete"}
SIGNED_STATUS = {"Completed", "Cancelled"}
YEAR = "2026"


def units(o: dict) -> int:
    try:
        return int(o.get("units") or 0)
    except (TypeError, ValueError):
        return 0


def norm_state(s) -> str:
    s = (s or "").strip().upper()
    return s if len(s) == 2 and s.isalpha() else "(blank)"


def main() -> None:
    con = sqlite3.connect(INDEX)
    opps = {}
    for (d,) in con.execute("select data from records where source='sf_opp'"):
        o = json.loads(d)
        opps[o["id"]] = o
    ags_by_opp = collections.defaultdict(list)
    all_ags = []
    for p, d in con.execute(
            "select parent_id, data from records where source='sf_agreement'"):
        a = json.loads(d)
        ags_by_opp[p].append(a)
        all_ags.append((p, a))
    con.close()

    def signed_year(a) -> str | None:
        if a["status"] in SIGNED_STATUS and a["signed"]:
            return a["signed"][:4]
        return None

    def opp_done_year(o) -> str | None:
        """When the opportunity actually landed: latest signed agreement on it."""
        ys = [y for y in (signed_year(a) for a in ags_by_opp.get(o["id"], []))
              if y]
        return max(ys) if ys else None

    # ---------------------------------------------------------------- MDU
    mdu = [o for o in opps.values() if o["record_type"] == "MDU/SFU"]
    done = [o for o in mdu if o["stage"] in DONE_STAGES]
    done_2026 = [o for o in done if opp_done_year(o) == YEAR]
    done_undated = [o for o in done if opp_done_year(o) is None]

    by_stage = collections.defaultdict(lambda: {"opps": 0, "units": 0,
                                                "opps_2026": 0, "units_2026": 0})
    for o in mdu:
        s = by_stage[o["stage"]]
        s["opps"] += 1
        s["units"] += units(o)
        if o["stage"] in DONE_STAGES and opp_done_year(o) == YEAR:
            s["opps_2026"] += 1
            s["units_2026"] += units(o)

    done_years = collections.defaultdict(lambda: {"opps": 0, "units": 0})
    for o in done:
        y = opp_done_year(o) or "(no signed agreement)"
        done_years[y]["opps"] += 1
        done_years[y]["units"] += units(o)

    # ---------------------------------------------------------------- AVR
    avr_raw = json.loads(AVR.read_text(encoding="utf-8"))
    avrs = []
    for c in avr_raw["cases"]:
        m = re.search(r"State:\s*(.*)", c.get("description") or "")
        raw = (m.group(1).strip().upper() if m else "")
        st = raw if raw in STATES else STATE_BY_NAME.get(raw, "(unparsed)")
        avrs.append({"created": c.get("createdDate") or "", "state": st})
    avr_2026 = [a for a in avrs if a["created"].startswith(YEAR)]

    # ------------------------------------------------------- agreements
    def ag_counts(kind):
        tot = sgn = sgn_yr = 0
        for _, a in all_ags:
            if a["type"] != kind:
                continue
            tot += 1
            y = signed_year(a)
            if y:
                sgn += 1
                if y == YEAR:
                    sgn_yr += 1
        return {"total": tot, "signed": sgn, "signed_2026": sgn_yr}

    roe = ag_counts("ROE")
    pal = ag_counts("PAL")

    # ---------------------------------------------------------- by state
    per = collections.defaultdict(lambda: collections.Counter())
    for o in done:
        st = norm_state(o["state"])
        per[st]["mdu_done"] += 1
        per[st]["mdu_units"] += units(o)
        if opp_done_year(o) == YEAR:
            per[st]["mdu_done_2026"] += 1
            per[st]["mdu_units_2026"] += units(o)
    for p, a in all_ags:
        st = norm_state((opps.get(p) or {}).get("state"))
        t = a["type"]
        y = signed_year(a)
        if t in ("ROE", "PAL"):
            key = t.lower()
            per[st][key] += 1
            if y:
                per[st][key + "_signed"] += 1
                if y == YEAR:
                    per[st][key + "_signed_2026"] += 1
    for a in avrs:
        if a["state"] != "(unparsed)":
            per[a["state"]]["avr"] += 1
            if a["created"].startswith(YEAR):
                per[a["state"]]["avr_2026"] += 1

    keys = ["mdu_done", "mdu_done_2026", "mdu_units", "mdu_units_2026",
            "roe", "roe_signed", "roe_signed_2026",
            "pal", "pal_signed", "pal_signed_2026", "avr", "avr_2026"]
    by_state = [dict({"state": st}, **{k: per[st][k] for k in keys})
                for st in per]
    by_state.sort(key=lambda r: (-r["mdu_units"], -r["mdu_done"]))

    # -------------------------------------------------------- california
    from load_vetro import load_vetro, service_locations
    ca = service_locations(load_vetro(warn_if_stale_days=99999))
    ca = ca[ca.state == "CA"].copy()
    abcol = ca.vetro_id_asbuilt.astype(str).str.strip().str.lower()
    ca["has_ab"] = ca.vetro_id_asbuilt.notna() & ~abcol.isin(["", "nan"])
    ff = ca.ckta_insvc == "Active customer"
    ting = ca.cktb_insvc == "Drop completed"

    areas = None
    for line in MAP.read_text(encoding="utf-8").splitlines():
        if line.startswith("const DATA "):
            areas = json.loads(line.split("=", 1)[1].rstrip().rstrip(";"))
            break
    act = [r for r in areas if r["act"]]
    act_years = collections.defaultdict(lambda: {"areas": 0, "addresses": 0})
    for r in act:
        y = r["act"][:4]
        act_years[y]["areas"] += 1
        act_years[y]["addresses"] += r["addrs"]

    by_city = []
    for city, x in ca.groupby(ca.city.astype(str).str.title()):
        if len(x) < 5:
            continue
        by_city.append({
            "city": city, "addresses": int(len(x)),
            "serviceable": int((x.addrstatus == "serviceable").sum()),
            "as_built": int(x.has_ab.sum()),
            "activations": int(((x.ckta_insvc == "Active customer")
                                | (x.cktb_insvc == "Drop completed")).sum()),
        })
    by_city.sort(key=lambda r: -r["addresses"])

    payload = {
        "generated": "2026-09-28",
        "year": YEAR,
        "headline": [
            {"metric": "MDU opportunities completed",
             "all_time": len(done), "year": len(done_2026), "unit": "opps"},
            {"metric": "Units in those completions",
             "all_time": sum(units(o) for o in done),
             "year": sum(units(o) for o in done_2026), "unit": "units"},
            {"metric": "AVRs raised",
             "all_time": len(avrs), "year": len(avr_2026), "unit": "cases"},
            {"metric": "ROEs signed",
             "all_time": roe["signed"], "year": roe["signed_2026"],
             "unit": "agreements"},
            {"metric": "PALs signed",
             "all_time": pal["signed"], "year": pal["signed_2026"],
             "unit": "agreements"},
            {"metric": "CA serving areas activated",
             "all_time": len(act), "year": act_years[YEAR]["areas"],
             "unit": "areas"},
        ],
        "mdu": {
            "total_opps": len(mdu), "total_units": sum(units(o) for o in mdu),
            "done_opps": len(done), "done_units": sum(units(o) for o in done),
            "done_opps_2026": len(done_2026),
            "done_units_2026": sum(units(o) for o in done_2026),
            "done_undated": len(done_undated),
            "with_unit_value": sum(1 for o in done if o["units"]),
            "by_stage": {k: dict(v) for k, v in by_stage.items()},
            "by_year": {k: dict(v) for k, v in sorted(done_years.items())},
        },
        "avr": {"all_time": len(avrs), "year": len(avr_2026),
                "prior": len(avrs) - len(avr_2026),
                "by_month": dict(sorted(collections.Counter(
                    a["created"][:7] for a in avr_2026).items())),
                "pulled_at": avr_raw["pulledAt"]},
        "roe": roe, "pal": pal,
        "california": {
            "service_locations": int(len(ca)),
            "addrstatus": {k: int(v)
                           for k, v in ca.addrstatus.value_counts().items()},
            "as_built": int(ca.has_ab.sum()),
            "ff_active": int(ff.sum()), "ting_drop": int(ting.sum()),
            "activations_total": int((ff | ting).sum()),
            "serving_areas": len(areas), "areas_activated": len(act),
            "areas_activated_2026": act_years[YEAR]["areas"],
            "addresses_activated_2026": act_years[YEAR]["addresses"],
            "activation_by_year": {k: dict(v)
                                   for k, v in sorted(act_years.items())},
            "by_city": by_city,
        },
        "by_state": by_state,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    for h in payload["headline"]:
        print(f"  {h['metric']:<30} all time {h['all_time']:>7,}   "
              f"{YEAR} YTD {h['year']:>6,}")
    print(f"  completions with no signed agreement to date them: "
          f"{payload['mdu']['done_undated']}")
    print(f"  states in the by-state table: {len(by_state)}")


if __name__ == "__main__":
    main()
