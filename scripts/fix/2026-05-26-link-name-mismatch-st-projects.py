"""
Manually link 5 SiteTracker_Project__c rows to their Opportunities. The
automated link pass (link_sitetracker_opportunities.py) missed them because
the ST mirror's Monday_Name__c carries the bare property name (e.g.
'Fontenelle Cottages') while the Opp's Name/Agreement_Name__c carries the
full Monday.com prefix format (e.g. 'Omaha_MDU_Fontenelle Cottages').

Confirmed pairs (curated 2026-05-26 from
_probes/2026-05-26-unlinked-st-candidate-match.py output):

  P-004316  Waterford Place Apts          -> Waterford Place Apartments (Mesa AZ)
  P-005533  Fontenelle Cottages           -> Omaha_MDU_Fontenelle Cottages
  P-005536  Grand Estates @ Keller        -> Grand Estates at Keller (Keller TX)
  P-005539  Farnam Flats                  -> Omaha_MDU_Farnam Flats
  P-006201  Southern Hills MHP            -> Southern Hills Manufactured Home Community (Killeen TX)

Writes:
  - Opportunity__c on each SiteTracker_Project__c row
  - SiteTracker_Project_ID__c on each Opportunity (so In_SiteTracker__c flips true)

Audit:
  SalesForce/data/output/audit_logs/st_name_mismatch_link_<ts>.csv
"""
import csv
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

DRY_RUN = "--apply" not in sys.argv

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

# (ST Name, Opp Name) pairs - curated, NOT fuzzy-resolved at runtime
PAIRS = [
    ("P-004316", "Waterford Place Apartments"),
    ("P-005533", "Omaha_MDU_Fontenelle Cottages"),
    ("P-005536", "Grand Estates at Keller"),
    ("P-005539", "Omaha_MDU_Farnam Flats"),
    ("P-006201", "Southern Hills Manufactured Home Community"),
]

# Pull both sides
st_names = "','".join(p[0] for p in PAIRS)
opp_names = "','".join(p[1].replace("'", "\\'") for p in PAIRS)

sts = sf.query(f"""
    SELECT Id, Name, Monday_Name__c, Site_Name__c, Opportunity__c,
           SiteTracker_Record_Id__c, City__c, State__c, Site_Status__c
    FROM SiteTracker_Project__c
    WHERE Name IN ('{st_names}')
""")["records"]
st_by_name = {r["Name"]: r for r in sts}

opps = sf.query(f"""
    SELECT Id, Name, Property_State__c, StageName, SiteTracker_Project_ID__c
    FROM Opportunity
    WHERE Name IN ('{opp_names}')
""")["records"]
opp_by_name = {r["Name"]: r for r in opps}

OUT = Path("C:/Users/cass/Work_Projects/SalesForce/data/output/audit_logs")
OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit_path = OUT / f"st_name_mismatch_link_{ts}.csv"

cols = [
    "timestamp", "st_name", "opp_name", "st_id", "opp_id",
    "st_record_id", "previous_opp_link", "previous_st_link",
    "city", "state", "site_status", "opp_stage", "action", "result",
]

print(f"\n{'DRY RUN' if DRY_RUN else 'APPLY'}: linking {len(PAIRS)} pairs\n")
results = []
with open(audit_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(cols)
    stamp = datetime.now().isoformat(timespec="seconds")

    for st_name, opp_name in PAIRS:
        st = st_by_name.get(st_name)
        opp = opp_by_name.get(opp_name)

        if not st:
            print(f"[SKIP] ST {st_name} not found")
            continue
        if not opp:
            print(f"[SKIP] Opp {opp_name!r} not found")
            continue

        # Safety: do not silently overwrite an existing link
        if st.get("Opportunity__c") and st["Opportunity__c"] != opp["Id"]:
            print(f"[SKIP] {st_name} already linked to a different Opp: {st['Opportunity__c']}")
            w.writerow([stamp, st_name, opp_name, st["Id"], opp["Id"],
                        st.get("SiteTracker_Record_Id__c"),
                        st.get("Opportunity__c"), opp.get("SiteTracker_Project_ID__c"),
                        st.get("City__c"), st.get("State__c"),
                        st.get("Site_Status__c"), opp.get("StageName"),
                        "would_link", "skipped_existing_link"])
            continue

        print(f"  {st_name:>10}  {(st.get('Monday_Name__c') or '')[:35]:35}  "
              f"-> {opp_name[:50]}  ({opp.get('Property_State__c')}, {opp.get('StageName')})")

        if DRY_RUN:
            w.writerow([stamp, st_name, opp_name, st["Id"], opp["Id"],
                        st.get("SiteTracker_Record_Id__c"),
                        st.get("Opportunity__c"), opp.get("SiteTracker_Project_ID__c"),
                        st.get("City__c"), st.get("State__c"),
                        st.get("Site_Status__c"), opp.get("StageName"),
                        "would_link", "dry_run"])
            continue

        try:
            sf.SiteTracker_Project__c.update(st["Id"], {"Opportunity__c": opp["Id"]})
            sf.Opportunity.update(opp["Id"], {
                "SiteTracker_Project_ID__c": st.get("SiteTracker_Record_Id__c") or st["Name"]
            })
            w.writerow([stamp, st_name, opp_name, st["Id"], opp["Id"],
                        st.get("SiteTracker_Record_Id__c"),
                        st.get("Opportunity__c"), opp.get("SiteTracker_Project_ID__c"),
                        st.get("City__c"), st.get("State__c"),
                        st.get("Site_Status__c"), opp.get("StageName"),
                        "linked", "ok"])
            results.append(("ok", st_name, opp_name))
        except Exception as e:
            w.writerow([stamp, st_name, opp_name, st["Id"], opp["Id"],
                        st.get("SiteTracker_Record_Id__c"),
                        st.get("Opportunity__c"), opp.get("SiteTracker_Project_ID__c"),
                        st.get("City__c"), st.get("State__c"),
                        st.get("Site_Status__c"), opp.get("StageName"),
                        "linked", f"error:{type(e).__name__}:{str(e)[:120]}"])
            results.append(("fail", st_name, str(e)[:80]))

print(f"\nAudit: {audit_path}")
if not DRY_RUN:
    ok = sum(1 for r in results if r[0] == "ok")
    fail = sum(1 for r in results if r[0] == "fail")
    print(f"Linked: ok={ok}  fail={fail}")
else:
    print("DRY RUN. Re-run with --apply to write.")
