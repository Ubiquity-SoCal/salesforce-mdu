"""Disassociate 'Indian Hills Terrace' from Marcon Enterprises (clear AccountId).
Approved by Koa 2026-06-24 (bulk-connect yesterday was wrong; it's a separate,
already-built property). Single-record prod data fix, audit-logged.
"""
import sys, csv
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(r"C:\Users\cass\Work_Projects\SalesForce")
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))
from _md_deploy import connect

OPP_ID = "006WR00000wk1ERYAY"  # Indian Hills Terrace
AUDIT = ROOT / "data" / "output" / "audit_logs" / "2026-06-24-disassociate-indian-hills-terrace.csv"
AUDIT.parent.mkdir(parents=True, exist_ok=True)

sf = connect()
F = "Id, Name, AccountId, Account.Name"

before = sf.query(f"SELECT {F} FROM Opportunity WHERE Id = '{OPP_ID}'")["records"][0]
b_acct_id = before.get("AccountId")
b_acct_nm = (before.get("Account") or {}).get("Name") if before.get("Account") else None
print(f"BEFORE: {before['Name']!r}  AccountId={b_acct_id}  Account={b_acct_nm!r}")

if not b_acct_id:
    print("Already has no Account. Nothing to do.")
    sys.exit(0)

resp = sf.Opportunity.update(OPP_ID, {"AccountId": None})
print(f"update HTTP status: {resp}")

after = sf.query(f"SELECT {F} FROM Opportunity WHERE Id = '{OPP_ID}'")["records"][0]
a_acct_id = after.get("AccountId")
print(f"AFTER:  {after['Name']!r}  AccountId={a_acct_id}")

ts = datetime.now(timezone.utc).isoformat()
with AUDIT.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
    w.writerow([OPP_ID, before["Name"], "AccountId", f"{b_acct_id} ({b_acct_nm})", a_acct_id or "",
                "Melissa flag via Koa 2026-06-24; wrong bulk-connect to Marcon Enterprises",
                ts, "disassociate account"])
print(f"\n{'OK - account cleared' if not a_acct_id else 'WARNING - still set'}. Audit -> {AUDIT}")
