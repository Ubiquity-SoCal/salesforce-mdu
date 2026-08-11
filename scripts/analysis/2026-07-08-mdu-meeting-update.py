"""
Apply the 7/8/2026 Weekly MDU meeting action items to Salesforce Opps.

Updates Next_Action__c (and Next_Action_Date__c where a concrete near-term date was
committed on the call) for each property discussed. Action items were derived from the
FULL transcript (tl;dv 'Weekly MDU' 7/8, id 6a4eab186d0d1b0013a97dbe), not the AI summary.

Default = PROPOSAL only: prints a before/after table and writes a preview CSV. Nothing
is written to SF. Pass --apply to write the changes; on --apply the script first writes a
rollback snapshot CSV (SF_Id + prior value = how to revert) and an audit_logs/ CSV per the
standard SF batch-change audit pattern.

    python 2026-07-08-mdu-meeting-update.py            # proposal only (read-only)
    python 2026-07-08-mdu-meeting-update.py --apply    # write to SF + snapshot + audit log

Opp Ids were resolved by grepping the open-Opp export against the transcript property
names (AI transcript misspells them, so matched to real Opp Names). No em-dashes per house
style. Owners left unchanged; only the next-step fields are touched.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "api" / "Salesforce_Credentials.txt"
OUT = ROOT / "data" / "output"
AUDIT = OUT / "audit_logs"
APPLY = "--apply" in sys.argv
SOURCE = "2026-07-08-mdu-meeting-update.py"
STAMP = "2026-07-08"  # meeting date; Date.now avoided for determinism

# id -> proposed next step. nad = Next_Action_Date__c to set (or None = leave existing).
# flag = surfaced caveat for the reviewer.
PLAN = [
    # ---- Bill (Omaha / Mineral Wells real estate) ----
    dict(id="006WR00000wkFbzYAE", name="The Arthur Apartments", owner="Bill", stage="Engaged",
         na="Bill getting Kelly's (Burlington Capital regional mgr) contact from Lloyd, then handing to "
            "Melissa to engage the closer. Best Omaha opp (~500 units, brand new). Update expected next week.",
         nad=None),
    dict(id="006WR00000wkA6dYAE", name="Howard Street", owner="Bill", stage="Proposal Sent",
         na="Kelly's contact coming from Lloyd (via Bill), then Melissa reaches out and updates SF. "
            "Grouped with Arthur + Terrace Garden under Kelly.",
         nad=None),
    dict(id="006WR00000wkA7oYAE", name="Terrace Garden Apartments", owner="Bill", stage="Proposal Sent",
         na="Kelly's contact coming from Lloyd (via Bill), then Melissa reaches out and updates SF. "
            "Grouped with Arthur + Howard Street under Kelly.",
         nad=None),
    dict(id="006WR00000wkA8mYAE", name="4813-4823 Boyd St Apartments (Victor)", owner="Bill", stage="Contract Negotiations",
         na="Victor is POC. Bill to pass contact to Melissa; folding into this week's Omaha call blitz.",
         nad=None),
    dict(id="006WR00000wkA8zYAE", name="6314 Boyd Street (Dr. Kumar)", owner="Bill", stage="Contract Negotiations",
         na="Dr. Kumar is POC. Bill to pass contact to Melissa; folding into this week's Omaha call blitz.",
         nad=None),
    dict(id="006WR00000wkA6fYAE", name="Bedford Square [fmr Maplewood Court]", owner="Bill", stage="Contract Negotiations",
         na="Marisol interested. Bill adding to the Omaha phone-call push to move the April PAL forward.",
         nad=None),
    dict(id="006WR00000wkA6WYAU", name="Dundee Flats", owner="Bill", stage="On Hold",
         na="On hold (~62 units). Bill to confirm the Cox bulk/EMA expiration (~Sept) from old notes / Tracker, "
            "then revisit when the Cox term ends.",
         nad=None),
    dict(id="006WR00000wkDMRYA2", name="Royal Gardens", owner="Bill", stage="Contract Negotiations",
         na="AK engaged (owns 18, this + Pioneer are the 2 near our fiber). Melissa picking up and addressing AK's 6 "
            "items (renewal terms, balloon, flat fee, tenant termination, free common-area WiFi). Target sign by 7/15.",
         nad="2026-07-09",
         flag="AK call scheduled tomorrow 7/9 10am (Melissa). Niraj also referenced a 'Jim Switzer' 4-property Nebraska "
              "portfolio for AK; those distinct Opps were not identified. Confirm scope."),
    dict(id="006WR00000wkDMXYA2", name="Pioneer Crossing Apartments", owner="Bill", stage="Contract Negotiations",
         na="AK engaged (owns 18, this + Royal Gardens are the 2 near our fiber). Melissa picking up and addressing AK's "
            "6 items (renewal terms, balloon, flat fee, tenant termination, free common-area WiFi). Target sign by 7/15.",
         nad="2026-07-09"),
    dict(id="006WR00000wk9SpYAI", name="Carmel Creekside", owner="Bill", stage="Proposal Sent",
         na="One of the 3 TX July targets (biggest). Angie following up; no substantive update this week "
            "(currently forecast Aug).",
         nad=None),
    dict(id="006WR00000wkC7zYAE", name="Williamsburg Townhomes and Apartments", owner="Bill", stage="Contract Negotiations",
         na="One of the 3 TX July targets. Angie following up; owner went quiet, no update this week (forecast Aug).",
         nad=None),
    dict(id="006WR00000wkCjMYAU", name="Gardens of Taylor", owner="Bill", stage="Contract Negotiations",
         na="Melissa adding to her call blitz this week to push the stalled PAL (strong momentum on the prior call; "
            "owner's current agreement ends Aug). Targeting July close.",
         nad=None),

    # ---- Brett ----
    dict(id="006WR00000wk9SlYAI", name="Mariposa Apartment Homes at River Bend", owner="Brett", stage="Engaged",
         na="Brett following up (was close, very interested). One of 5 TX opps handed off from Chuck; Brett to log updates. "
            "Brett shifting focus to TX + Omaha, tag-teaming calls with Melissa.",
         nad=None),

    # ---- Melissa ----
    dict(id="006WR00000wkEcAYAU", name="Creekside Apartments (Bridgeport)", owner="Melissa", stage="Marketing/Bulk In Progress",
         na="Going bulk. Melissa refreshing notes; had dropped off the next-60 view (past due). Chasing PAL addendum "
            "(bulk agreement already in place).",
         nad=None),
    dict(id="006WR00000wkEcpYAE", name="Sonterra Apartment Homes", owner="Melissa", stage="Marketing/Bulk In Progress",
         na="Going EMA. PAL rerouted from Manny to the correct signer (Sherelle). Melissa + Mitch (marketing) pushing the "
            "EMA signature; strong relationship already, we have service there.",
         nad=None),
    dict(id="006WR00000wkCjuYAE", name="Bradley Arms", owner="Melissa", stage="Marketing/Bulk In Progress",
         na="EMA out for signature (6/25). Melissa targeting signature this month.",
         nad=None,
         flag="Melissa grouped Bradley Arms with a 'Safari Apartments' as past-due EMAs to sign this month. "
              "No open Opp named 'Safari' was found. Confirm the real name / status."),
    dict(id="006WR00000wkEcBYAU", name="Heritage of Newark (FKA Newark Beach Estates)", owner="Melissa", stage="Marketing/Bulk Complete",
         na="Fully signed (bulk + PAL amendment + addendum). Construction ~early Aug (per Niraj). Melissa to give the owner "
            "a start-date update and vet the referral she was sent for a nearby complex.",
         nad=None),
    dict(id="006WR00000wk9SsYAI", name="Sandpiper Pointe", owner="Melissa", stage="Marketing/Bulk In Progress",
         na="PAL signed, design inputs sent to eng. CA build intentionally paused pending the property deal close (no build "
            "spend). Niraj to give Melissa the HOA messaging by Fri 7/10.",
         nad="2026-07-10"),
    dict(id="006WR00000wk1ElYAI", name="The Bluffs of Brookside", owner="Chuck", stage="PAL/ROE Complete",
         na="Worth Telecom (John Smith): explore a non-exclusive marketing agreement if they can exit the Charter EMA "
            "(through 2034). Low penetration (~34%). Melissa working John Smith; awaiting Charter response.",
         nad=None,
         flag="Owner is Chuck McNeely, Substatus 'Incumbent EMA'. Melissa now working it via Worth Telecom."),
    dict(id="006WR00000wk1EjYAI", name="The Renaissance at Stoney Creek", owner="Chuck", stage="PAL/ROE Complete",
         na="Worth Telecom (John Smith): explore a non-exclusive marketing agreement if they can exit the Charter EMA "
            "(through 2034). Low penetration (~19%). Melissa working John Smith; awaiting Charter response.",
         nad=None,
         flag="Owner is Chuck McNeely, Substatus 'Incumbent EMA'. Melissa now working it via Worth Telecom."),
    dict(id="006WR00000wk1EcYAI", name="Terrace Heights Apartments", owner="Chuck", stage="PAL/ROE Complete",
         na="Worth Telecom (John Smith): explore a non-exclusive marketing agreement if they can exit the Charter EMA "
            "(through 2034). Low penetration (~19%). Melissa working John Smith; awaiting Charter response.",
         nad=None,
         flag="Owner is Chuck McNeely, Substatus 'Incumbent EMA'. Melissa now working it via Worth Telecom."),
]


def connect():
    creds = {}
    for line in open(CREDS_PATH, encoding="utf-8"):
        if ":" in line:
            k, v = line.split(":", 1)
            creds[k.strip()] = v.strip()
    return Salesforce(username=creds["Username"], password=creds["Password"],
                      security_token=creds["Security Token"])


def main():
    sf = connect()
    ids = [p["id"] for p in PLAN]
    q = sf.query_all(
        "SELECT Id, Name, StageName, Owner.Name, Next_Action__c, Next_Action_Date__c "
        "FROM Opportunity WHERE Id IN ('" + "','".join(ids) + "')")
    cur = {r["Id"]: r for r in q["records"]}

    rows = []
    for p in PLAN:
        r = cur.get(p["id"])
        if not r:
            print(f"  ** NOT FOUND: {p['name']} ({p['id']})")
            continue
        rows.append(dict(
            p=p, sf_name=r["Name"], sf_owner=(r.get("Owner") or {}).get("Name", ""),
            stage=r["StageName"],
            na_before=r.get("Next_Action__c") or "",
            nad_before=r.get("Next_Action_Date__c") or "",
        ))

    # Proposal table
    print(f"\n{'PROPOSAL' if not APPLY else 'APPLYING'} - 7/8 Weekly MDU -> {len(rows)} Opps\n" + "=" * 100)
    for x in rows:
        p = x["p"]
        print(f"\n[{x['sf_owner']:14s}] {x['sf_name']}  ({x['stage']})")
        print(f"   BEFORE na : {x['na_before'][:160] or '(blank)'}")
        print(f"   AFTER  na : {p['na'][:160]}")
        if p["nad"]:
            print(f"   na date   : {x['nad_before'] or '(blank)'}  ->  {p['nad']}")
        if p.get("flag"):
            print(f"   FLAG      : {p['flag']}")

    # Preview CSV
    OUT.mkdir(parents=True, exist_ok=True)
    prev = OUT / f"{STAMP}-mdu-meeting-update-proposal.csv"
    with open(prev, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Name", "Owner", "Stage", "NextAction_Before", "NextAction_After",
                    "NextActionDate_Before", "NextActionDate_After", "Flag"])
        for x in rows:
            p = x["p"]
            w.writerow([p["id"], x["sf_name"], x["sf_owner"], x["stage"], x["na_before"], p["na"],
                        x["nad_before"], p["nad"] or "", p.get("flag", "")])
    print(f"\nWrote preview -> {prev}")

    if not APPLY:
        print("\nProposal only. Re-run with --apply to write to SF (snapshot + audit log written first).")
        return

    # Rollback snapshot (how to revert) + audit log, written BEFORE/AS we apply
    AUDIT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    snap = OUT / f"{STAMP}-mdu-meeting-update-rollback-{ts}.csv"
    audit = AUDIT / f"{STAMP}-mdu-meeting-update-{ts}.csv"
    with open(snap, "w", newline="", encoding="utf-8") as sf_f, \
         open(audit, "w", newline="", encoding="utf-8") as au_f:
        sw = csv.writer(sf_f)
        sw.writerow(["SF_Id", "Name", "Next_Action__c", "Next_Action_Date__c"])  # prior values = revert target
        aw = csv.writer(au_f)
        aw.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
        now = datetime.now().isoformat(timespec="seconds")
        for x in rows:
            p = x["p"]
            sw.writerow([p["id"], x["sf_name"], x["na_before"], x["nad_before"]])
            payload = {"Next_Action__c": p["na"]}
            aw.writerow([p["id"], x["sf_name"], "Next_Action__c", x["na_before"], p["na"], SOURCE, now, "update"])
            if p["nad"]:
                payload["Next_Action_Date__c"] = p["nad"]
                aw.writerow([p["id"], x["sf_name"], "Next_Action_Date__c", x["nad_before"], p["nad"], SOURCE, now, "update"])
            sf.Opportunity.update(p["id"], payload)
            print(f"  updated {x['sf_name']}")
    print(f"\nApplied {len(rows)} Opps.\n  rollback -> {snap}\n  audit    -> {audit}")


if __name__ == "__main__":
    main()
