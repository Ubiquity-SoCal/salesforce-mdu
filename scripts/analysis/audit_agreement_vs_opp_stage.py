"""
Audit: do Opportunity stages agree with the state of their child Agreements?

Scope: MDU + SFU record types (the pipeline the MDU stages map to).
Read-only. Creds from env (SF_MAIN_USERNAME/PASSWORD/TOKEN).

Logic
-----
Each Opp's stage is bucketed (PRE-contract / SECURED-or-later / ON HOLD / LOST / legacy).
Each Opp's agreements roll up to: any Completed, any Completed PAL/ROE, any in-flight
(Create/Review/Sign), any Paused.

Flags (categorization smells):
  A  SECURED stage but ZERO completed agreements   -> mis-staged forward, or agr not synced
  B  PRE-contract stage but a Completed PAL/ROE      -> should advance to PAL/ROE Complete+
  C  Closed Lost / On Hold but a Completed PAL/ROE   -> signed yet parked negative
  L  Legacy/unknown stage value on an MDU/SFU Opp    -> stale stage, not in current pipeline

Outputs a console summary (cross-tab + flag counts) and a CSV of every flagged Opp.
"""
import os
import sys
import csv
from collections import Counter, defaultdict
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

OUT_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output",
                       "agreement_vs_opp_stage_audit.csv")

# --- stage buckets (current MDU pipeline + still-active legacy values) ---
PRE = {"Prospects", "Prospecting", "Engaged", "Proposal Sent", "Contract Negotiations",
       "Qualification", "Needs Analysis", "Negotiation", "Proposal"}
SECURED = {"PAL/ROE Complete", "ROE Secured", "Marketing/Bulk In Progress",
           "Marketing/Bulk Complete", "Under Contract", "Ready for Engineering",
           "Under Construction", "Engineering", "Construction", "Activation", "Closed Won"}
HOLD = {"On Hold"}
LOST = {"Closed Lost"}

# canonical current MDU pipeline (used only to flag legacy stage names)
CANONICAL_MDU = {"Closed Lost", "On Hold", "Prospects", "Prospecting", "Engaged",
                 "Proposal Sent", "Contract Negotiations", "PAL/ROE Complete",
                 "Marketing/Bulk In Progress", "Marketing/Bulk Complete"}

PALROE_TYPES = {"PAL", "ROE", "NEMA", "PAL Addendum", "2nd ISP NEMA"}
COMPLETED = {"Completed"}
INFLIGHT = {"Create", "Review", "Sign"}


def env(n):
    v = os.environ.get(n)
    if not v:
        print(f"[ERROR] missing env {n}"); sys.exit(1)
    return v


def query_all(sf, soql):
    res = sf.query(soql)
    recs = res["records"]
    while not res["done"]:
        res = sf.query_more(res["nextRecordsUrl"], True)
        recs.extend(res["records"])
    return recs


def bucket(stage):
    if stage in LOST: return "LOST"
    if stage in HOLD: return "HOLD"
    if stage in PRE: return "PRE"
    if stage in SECURED: return "SECURED"
    return "LEGACY"


def main():
    sf = Salesforce(username=env("SF_MAIN_USERNAME"), password=env("SF_MAIN_PASSWORD"),
                    security_token=env("SF_MAIN_TOKEN"))
    soql = ("SELECT Id, Name, StageName, RecordType.DeveloperName, Owner.Name, "
            "(SELECT Agreement_Type__c, Status__c, Signed_Date__c FROM Agreements__r) "
            "FROM Opportunity WHERE RecordType.DeveloperName IN ('MDU','SFU')")
    opps = query_all(sf, soql)
    print(f"Pulled {len(opps)} MDU/SFU Opportunities\n")

    # cross-tab: stage -> counts
    xtab = defaultdict(lambda: Counter())
    flagged = []
    flag_counts = Counter()
    legacy_stage_counts = Counter()

    for o in opps:
        stage = o["StageName"]
        b = bucket(stage)
        agrs = (o.get("Agreements__r") or {}).get("records", []) if o.get("Agreements__r") else []
        n = len(agrs)
        n_completed = sum(1 for a in agrs if a["Status__c"] in COMPLETED)
        n_completed_palroe = sum(1 for a in agrs if a["Status__c"] in COMPLETED
                                 and (a.get("Agreement_Type__c") or "") in PALROE_TYPES)
        n_inflight = sum(1 for a in agrs if a["Status__c"] in INFLIGHT)

        c = xtab[stage]
        c["opps"] += 1
        c["with_agr"] += 1 if n else 0
        c["completed_agr"] += 1 if n_completed else 0
        c["completed_palroe"] += 1 if n_completed_palroe else 0
        c["inflight_only"] += 1 if (n and n_inflight and n_completed == 0) else 0
        c["no_agr"] += 1 if n == 0 else 0

        flag = None
        if b == "SECURED" and n_completed == 0:
            flag = "A_secured_no_completed"
        elif b == "PRE" and n_completed_palroe >= 1:
            flag = "B_pre_has_completed_palroe"
        elif b in ("LOST", "HOLD") and n_completed_palroe >= 1:
            flag = "C_lost_hold_has_completed_palroe"
        if b == "LEGACY":
            legacy_stage_counts[stage] += 1
            # legacy flag is independent; record it too if not already flagged
            if flag is None:
                flag = "L_legacy_stage"

        if flag:
            flag_counts[flag] += 1
            detail = ";".join(f"{a.get('Agreement_Type__c') or '?'}:{a['Status__c']}" for a in agrs) or "(none)"
            flagged.append({
                "Flag": flag, "OppId": o["Id"], "Name": o["Name"],
                "Owner": (o.get("Owner") or {}).get("Name", ""),
                "RecordType": (o.get("RecordType") or {}).get("DeveloperName", ""),
                "Stage": stage, "n_agr": n, "completed": n_completed,
                "completed_palroe": n_completed_palroe, "inflight": n_inflight,
                "agreements": detail,
            })

    # ---- console report ----
    order = ["Closed Lost", "On Hold", "Prospects", "Prospecting", "Engaged",
             "Proposal Sent", "Contract Negotiations", "PAL/ROE Complete",
             "Marketing/Bulk In Progress", "Marketing/Bulk Complete"]
    extras = [s for s in xtab if s not in order]
    print("=== Stage x Agreement cross-tab (MDU/SFU) ===")
    hdr = f"{'Stage':<28}{'Opps':>6}{'noAgr':>7}{'wAgr':>6}{'compl':>7}{'PAL/ROE':>9}{'inflt-only':>11}"
    print(hdr); print("-" * len(hdr))
    for s in order + sorted(extras):
        if s not in xtab: continue
        c = xtab[s]
        print(f"{s:<28}{c['opps']:>6}{c['no_agr']:>7}{c['with_agr']:>6}"
              f"{c['completed_agr']:>7}{c['completed_palroe']:>9}{c['inflight_only']:>11}")

    print("\n=== Flag counts ===")
    for f in ["A_secured_no_completed", "B_pre_has_completed_palroe",
              "C_lost_hold_has_completed_palroe", "L_legacy_stage"]:
        print(f"  {f}: {flag_counts.get(f, 0)}")
    print(f"  TOTAL flagged Opps: {len(flagged)}")

    if legacy_stage_counts:
        print("\n=== Legacy/unknown stage values on MDU/SFU Opps ===")
        for s, n in legacy_stage_counts.most_common():
            print(f"  {s}: {n}")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Flag", "OppId", "Name", "Owner", "RecordType",
                                           "Stage", "n_agr", "completed", "completed_palroe",
                                           "inflight", "agreements"])
        w.writeheader()
        w.writerows(sorted(flagged, key=lambda r: (r["Flag"], r["Stage"], r["Name"])))
    print(f"\nWrote {len(flagged)} flagged rows -> {os.path.relpath(OUT_CSV)}")


if __name__ == "__main__":
    main()
