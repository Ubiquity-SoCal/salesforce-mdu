"""Follow-up to 2026-06-11-apply-brett-jones-jones-pal-ironclad.py.

The 30 Brett Spivey Opps were owned by an INACTIVE duplicate user
(005WR00000CXEZyYAP), so SF rejected the AccountId reparent
(CANNOT_REPARENT_RECORD: "Owner is inactive"). The PAL IronClad_ID__c /
Expiration_Date__c writes already succeeded.

There is an ACTIVE duplicate "Brett Spivey" (005WR00000Ewjj3YAB). Koa approved
(6/11): reassign the 30 Opps to the active Brett, then set the Account. Owner
still displays "Brett Spivey".

Per record, two sequential writes (owner first so the reparent sees an active
owner):
  1. OwnerId   -> 005WR00000Ewjj3YAB (active Brett)
  2. AccountId -> 001WR00001SPM7zYAH (Jones & Jones Communities)

Source of the 30 Opp Ids: the snapshot written by the prior apply run (the Opps
that were owned by the inactive Brett). Fresh full-record snapshot taken here too.

Dry-run by default; pass --apply to write.
"""
import sys
import csv
import json
from pathlib import Path
from datetime import datetime
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


APPLY = "--apply" in sys.argv
INACTIVE_BRETT = "005WR00000CXEZyYAP"
ACTIVE_BRETT = "005WR00000Ewjj3YAB"
ACCT_ID = "001WR00001SPM7zYAH"
ACCT_NAME = "Jones & Jones Communities"

OUT = Path("C:/Users/cass/Work_Projects/SalesForce/data/output/audit_logs")
TS = datetime.now().strftime("%Y%m%d-%H%M%S")
SOURCE = "Cleanup need Ironclad IDs - Taylor's Notes 6.10.26.xlsx (reassign+account)"

sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])

# --- load the 30 target Opp Ids from the prior snapshot ---
snap_file = sorted(OUT.glob("brett_jones_jones_snapshot_*.json"))[-1]
prior = json.loads(snap_file.read_text(encoding="utf-8"))
opp_ids = [k for k, v in prior.items()
           if v.get("attributes", {}).get("type") == "Opportunity"
           and v.get("OwnerId") == INACTIVE_BRETT]
print(f"Loaded {len(opp_ids)} Opps owned by inactive Brett from {snap_file.name}")

# --- re-query live state for those Opps ---
ids_in = "','".join(opp_ids)
opps = sf.query_all(
    f"SELECT Id, Name, OwnerId, Owner.Name, AccountId, Account.Name, StageName "
    f"FROM Opportunity WHERE Id IN ('{ids_in}')"
)["records"]

plan = []
for o in opps:
    needs_owner = o["OwnerId"] != ACTIVE_BRETT
    needs_acct = o.get("AccountId") != ACCT_ID
    if needs_owner or needs_acct:
        plan.append((o, needs_owner, needs_acct))

print(f"\nPLAN ({len(plan)} Opps):")
print(f"  OwnerId  -> active Brett ({ACTIVE_BRETT})")
print(f"  AccountId -> {ACCT_NAME} ({ACCT_ID})")

# --- fresh snapshot ---
fresh = {o["Id"]: sf.Opportunity.get(o["Id"]) for o, _, _ in plan}
fresh_path = OUT / f"brett_reassign_snapshot_{TS}.json"
fresh_path.write_text(json.dumps(fresh, indent=2, default=str), encoding="utf-8")
print(f"Fresh snapshot ({len(fresh)} Opps): {fresh_path}")

audit = OUT / f"brett_reassign_audit_{TS}.csv"
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SF_Id", "Name", "Action", "Field", "Before", "After",
                "Source", "Result", "Timestamp"])
    if not APPLY:
        for o, no, na in plan:
            if no:
                w.writerow([o["Id"], o["Name"], "REASSIGN_OWNER", "OwnerId",
                            o["OwnerId"], ACTIVE_BRETT, SOURCE, "preview",
                            datetime.now().isoformat()])
            if na:
                w.writerow([o["Id"], o["Name"], "SET_ACCOUNT", "AccountId",
                            o.get("AccountId") or "(blank)", ACCT_ID, SOURCE,
                            "preview", datetime.now().isoformat()])
        print(f"\nAudit (preview): {audit}")
        print("\nPREVIEW ONLY. Re-run with --apply to execute.")
    else:
        oown = ofail = aok = afail = 0
        for o, no, na in plan:
            if no:
                try:
                    sf.Opportunity.update(o["Id"], {"OwnerId": ACTIVE_BRETT})
                    w.writerow([o["Id"], o["Name"], "REASSIGN_OWNER", "OwnerId",
                                o["OwnerId"], ACTIVE_BRETT, SOURCE, "ok",
                                datetime.now().isoformat()])
                    oown += 1
                except Exception as e:
                    w.writerow([o["Id"], o["Name"], "REASSIGN_OWNER", "OwnerId",
                                o["OwnerId"], ACTIVE_BRETT, SOURCE, f"error:{e}",
                                datetime.now().isoformat()])
                    ofail += 1
                    continue  # don't try the reparent if owner change failed
            if na:
                try:
                    sf.Opportunity.update(o["Id"], {"AccountId": ACCT_ID})
                    w.writerow([o["Id"], o["Name"], "SET_ACCOUNT", "AccountId",
                                o.get("AccountId") or "(blank)", ACCT_ID, SOURCE,
                                "ok", datetime.now().isoformat()])
                    aok += 1
                except Exception as e:
                    w.writerow([o["Id"], o["Name"], "SET_ACCOUNT", "AccountId",
                                o.get("AccountId") or "(blank)", ACCT_ID, SOURCE,
                                f"error:{e}", datetime.now().isoformat()])
                    afail += 1
        print(f"\nOwner reassign: ok={oown} fail={ofail}   Account set: ok={aok} fail={afail}")
        print(f"Audit: {audit}")
        print(f"Restore from: {fresh_path}")
