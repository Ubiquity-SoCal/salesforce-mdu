"""
Populate Opportunity.Primary_Contact__c / Primary_Contact_Role__c / Contact_Count__c
from the Opportunity_Contact__c junction.

Primary contact rule (Koa, 2026-07-09): highest ROLE priority wins; oldest link breaks ties.
Contact_Count__c counts DISTINCT contacts, so the 62 duplicate (opp, contact) pairs do not
inflate it. A roll-up summary could not do this, which is why the field is a plain Number.

Only opportunities that HAVE at least one linked contact are written. Opportunity has two
active triggers -- OpportunityAddressDupBlock (before update, can reject) and
OpportunityUnitLinkTrigger (after update) -- so we do not touch the 3,724 contactless opps
just to write a zero. Blank Contact_Count__c means "no contact on file".

Re-runnable. Writes a rollback CSV before touching anything.

Usage:
    python backfill_opportunity_primary_contact.py                  # dry run
    python backfill_opportunity_primary_contact.py --limit 5 --apply  # smoke test
    python backfill_opportunity_primary_contact.py --apply          # full
"""
import sys
import io
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

# who do we actually want to call, best first
ROLE_PRIORITY = [
    "Property Owner",
    "Property Manager",
    "Leasing Contact",
    "HOA Contact",
    "Broker",
    "Developer",
    "Legal Contact",
    "Other",
]
RANK = {r: i for i, r in enumerate(ROLE_PRIORITY)}
UNRANKED = len(ROLE_PRIORITY) + 1  # blank / unknown role sorts last

APPLY = "--apply" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

AUDIT_DIR = ROOT / "data" / "output" / "audit_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now().strftime("%Y-%m-%d-%H%M%S")

sf = Salesforce(*creds())

# ---- read the junction ----------------------------------------------------
links = sf.query_all(
    "SELECT Id, Opportunity__c, Contact__c, Contact__r.Name, Role__c, CreatedDate "
    "FROM Opportunity_Contact__c "
    "WHERE Opportunity__c != null AND Contact__c != null "
    "ORDER BY CreatedDate ASC, Id ASC"
)["records"]
print(f"junction rows with both parents: {len(links)}")

by_opp = defaultdict(list)
for r in links:
    by_opp[r["Opportunity__c"]].append(r)


def pick_primary(rows):
    """Highest role priority; oldest link (already sorted) breaks ties."""
    return min(
        rows,
        key=lambda r: (
            RANK.get((r.get("Role__c") or "").strip(), UNRANKED),
            r["CreatedDate"],
            r["Id"],
        ),
    )


# ---- current values, for rollback ----------------------------------------
opp_ids = list(by_opp)
if LIMIT:
    opp_ids = opp_ids[:LIMIT]
print(f"opportunities with >=1 contact: {len(by_opp)}"
      + (f"  (limited to {len(opp_ids)})" if LIMIT else ""))

current = {}
CHUNK = 200
for i in range(0, len(opp_ids), CHUNK):
    ids = "','".join(opp_ids[i:i + CHUNK])
    for o in sf.query_all(
        "SELECT Id, Name, Primary_Contact__c, Primary_Contact_Role__c, Contact_Count__c "
        f"FROM Opportunity WHERE Id IN ('{ids}')"
    )["records"]:
        current[o["Id"]] = o

# ---- build the change set -------------------------------------------------
changes = []
for oid in opp_ids:
    rows = by_opp[oid]
    primary = pick_primary(rows)
    distinct = len({r["Contact__c"] for r in rows})
    cur = current.get(oid, {})
    new = {
        "Primary_Contact__c": primary["Contact__c"],
        "Primary_Contact_Role__c": (primary.get("Role__c") or None),
        "Contact_Count__c": distinct,
    }
    if all(cur.get(k) == v for k, v in new.items()):
        continue  # already correct, re-run is a no-op
    changes.append({
        "Id": oid,
        "opp_name": cur.get("Name"),
        "old_primary": cur.get("Primary_Contact__c"),
        "old_role": cur.get("Primary_Contact_Role__c"),
        "old_count": cur.get("Contact_Count__c"),
        "new_primary": new["Primary_Contact__c"],
        "new_primary_name": (primary.get("Contact__r") or {}).get("Name"),
        "new_role": new["Primary_Contact_Role__c"],
        "new_count": distinct,
        "junction_rows": len(rows),
    })

print(f"opportunities needing an update: {len(changes)}")
dupe_inflated = [c for c in changes if c["junction_rows"] != c["new_count"]]
print(f"  of those, junction rows > distinct contacts (duplicate links): {len(dupe_inflated)}")

print("\nsample:")
for c in changes[:5]:
    print(f"  {str(c['opp_name'])[:40]:40s} -> {str(c['new_primary_name'])[:24]:24s} "
          f"({c['new_role']})  count={c['new_count']} (links={c['junction_rows']})")

audit = AUDIT_DIR / f"{STAMP}-backfill-opp-primary-contact.csv"
with audit.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(changes[0].keys()) if changes else ["Id"])
    w.writeheader()
    w.writerows(changes)
print(f"\nrollback/audit CSV: {audit}")

if not APPLY:
    print("\nDRY RUN. pass --apply to write. (--limit N to smoke test first)")
    sys.exit(0)

# ---- write ----------------------------------------------------------------
ok = err = 0
failures = []
for c in changes:
    try:
        sf.Opportunity.update(c["Id"], {
            "Primary_Contact__c": c["new_primary"],
            "Primary_Contact_Role__c": c["new_role"],
            "Contact_Count__c": c["new_count"],
        })
        ok += 1
    except Exception as e:
        err += 1
        failures.append((c["Id"], c["opp_name"], str(e)[:160]))
print(f"\nupdated={ok} failed={err}")
for f in failures[:10]:
    print("  FAIL", f)

# ---- verify by re-reading -------------------------------------------------
check_ids = [c["Id"] for c in changes]
verified = mismatch = 0
for i in range(0, len(check_ids), CHUNK):
    ids = "','".join(check_ids[i:i + CHUNK])
    for o in sf.query_all(
        "SELECT Id, Primary_Contact__c, Contact_Count__c FROM Opportunity "
        f"WHERE Id IN ('{ids}')"
    )["records"]:
        want = next(c for c in changes if c["Id"] == o["Id"])
        if o["Primary_Contact__c"] == want["new_primary"] and o["Contact_Count__c"] == want["new_count"]:
            verified += 1
        else:
            mismatch += 1
print(f"\nVERIFY re-read: {verified} match, {mismatch} mismatch")
print("PASS" if mismatch == 0 and err == 0 else "REVIEW FAILURES ABOVE")
