"""
Tie the 7 MarCon / Albert Moellenbeck Omaha opps into one bulk portfolio:
  1. Link all 7 -> Account "Marcon Enterprises" (001WR00001K2k7dYAB)
  2. Reassign the 6 non-Melissa opps -> Melissa Baker (005WR000003CD6DYAW)
  3. Reassign the Marcon Enterprises account owner -> Melissa Baker
  4. Append a bulk-meeting note to Next_Action__c on all 7 (preserve existing text)

Idempotent: skips a change that's already in place; won't double-append the note.
Writes a before/after audit CSV to data/output/audit_logs/.

Usage:
    python ...py            # DRY RUN (no writes)
    python ...py --apply    # execute
"""
import sys
import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


APPLY = "--apply" in sys.argv

sf = Salesforce(username=_SF["username"], password=_SF["password"],
                security_token=_SF["token"])

ACCOUNT_ID = "001WR00001K2k7dYAB"          # Marcon Enterprises
ACCOUNT_NAME = "Marcon Enterprises"
MELISSA_ID = "005WR000003CD6DYAW"          # Melissa Baker (active)
NOTE = " | [2026-06-24] Melissa to meet owner (Albert Moellenbeck / MarCon) re: portfolio bulk."
NOTE_MARKER = "portfolio bulk"             # idempotency guard
SOURCE = "2026-06-23-tie-marcon-portfolio-to-account-melissa.py"
TS = datetime.now().isoformat()

OPPS = {
    "006WR00000xvWR0YAM": "4810-4812 Capital Ave",
    "006WR00000xv174YAA": "The Wakeley Pointe",
    "006WR00000wkA8yYAE": "78th Place Apartments (78th Street)",
    "006WR00000xwGATYA2": "California Place",
    "006WR00000wkBToYAM": "Orchard Park Apartments",
    "006WR00000wkBTuYAM": "Indian Hills Village Apartments",
    "006WR00000wk1ERYAY": "Indian Hills Terrace (Indian Hills Village Court)",
}

audit = []  # (Action, SF_Id, Name, Field, Before, After)


def log(action, sfid, name, field, before, after):
    audit.append((action, sfid, name, field, before, after))
    flag = "WOULD" if not APPLY else "DID"
    print(f"  [{flag} {action}] {name} :: {field}\n      before: {before!r}\n      after:  {after!r}")


# ── Pull current state of the 7 ────────────────────────────────────────────────
ids = "(" + ",".join(f"'{i}'" for i in OPPS) + ")"
opps = sf.query(
    "SELECT Id, Name, OwnerId, Owner.Name, AccountId, Account.Name, Next_Action__c "
    "FROM Opportunity WHERE Id IN " + ids)["records"]

print(f"\n{'='*84}\n{'APPLYING' if APPLY else 'DRY RUN'} — Marcon portfolio tie-together\n{'='*84}")

for o in opps:
    oid, nm = o["Id"], OPPS.get(o["Id"], o["Name"])
    print(f"\n### {nm}")
    update = {}

    # 1) Account link
    if o.get("AccountId") != ACCOUNT_ID:
        log("UPDATE", oid, nm, "AccountId",
            (o.get("Account") or {}).get("Name"), ACCOUNT_NAME)
        update["AccountId"] = ACCOUNT_ID
    else:
        print("      account already linked - skip")

    # 2) Owner -> Melissa
    if o.get("OwnerId") != MELISSA_ID:
        log("UPDATE", oid, nm, "OwnerId",
            (o.get("Owner") or {}).get("Name"), "Melissa Baker")
        update["OwnerId"] = MELISSA_ID
    else:
        print("      already owned by Melissa - skip")

    # 3) Next_Action__c append
    cur = o.get("Next_Action__c") or ""
    if NOTE_MARKER not in cur:
        new = (cur + NOTE).strip()
        log("UPDATE", oid, nm, "Next_Action__c", cur, new)
        update["Next_Action__c"] = new
    else:
        print("      bulk note already present - skip")

    if APPLY and update:
        sf.Opportunity.update(oid, update)

# ── Account owner -> Melissa ───────────────────────────────────────────────────
print(f"\n### Account: {ACCOUNT_NAME}")
acct = sf.query(f"SELECT Id, Name, OwnerId, Owner.Name FROM Account WHERE Id='{ACCOUNT_ID}'")["records"][0]
if acct.get("OwnerId") != MELISSA_ID:
    log("UPDATE", ACCOUNT_ID, ACCOUNT_NAME, "OwnerId",
        (acct.get("Owner") or {}).get("Name"), "Melissa Baker")
    if APPLY:
        sf.Account.update(ACCOUNT_ID, {"OwnerId": MELISSA_ID})
else:
    print("      account already owned by Melissa - skip")

# ── Write audit log ────────────────────────────────────────────────────────────
if audit:
    out = Path("SalesForce/data/output/audit_logs")
    out.mkdir(parents=True, exist_ok=True)
    suffix = "applied" if APPLY else "dryrun"
    fp = out / f"marcon_portfolio_tie_{suffix}_{datetime.now():%Y%m%dT%H-%M-%S}.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Action", "SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp"])
        for row in audit:
            w.writerow([*row, SOURCE, TS])
    print(f"\nAudit log: {fp}  ({len(audit)} change rows)")
else:
    print("\nNo changes needed.")

print(f"\n{'APPLIED' if APPLY else 'DRY RUN complete — re-run with --apply to execute'}.")
