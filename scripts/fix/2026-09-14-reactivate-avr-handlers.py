"""
Reactivate Kevin Sheets + Michell Wilburn so they can take over AVRs after 2026-09-25.

Ask: Zak Dubree, "AVR Process Transition" email 2026-09-14.
Both already exist INACTIVE on profile 'Standard User - Custom' (Koa created them 2025).
That profile alone grants the Address Management app, Case R/C/E + View All, and edit
on all AVR fields, so no perm sets are added. Zak's 5 perm sets are MDU/tracker access,
not AVR access; deliberately not copied.

Changes:
  Kevin Sheets    005WR0000036jGrYAI  IsActive -> true
  Michell Wilburn 005WR000003nr4fYAA  IsActive -> true, FirstName Michelle -> Michell (GAL),
                                      TimeZone LA -> Chicago (Omaha office per GAL)

Reactivation sends no email. Login email is a separate step (--send-login-email),
which calls System.resetPassword(id, true): Salesforce emails each user a set-password link.

Preview by default; --apply to write. Snapshot before + after in
audit_logs/user_reactivate_avr_handlers_<ts>.csv. Rollback = write the before values back.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _c

_s = _c()
sf = Salesforce(username=_s["username"], password=_s["password"], security_token=_s["token"])
APPLY = "--apply" in sys.argv
SEND_LOGIN = "--send-login-email" in sys.argv
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")

TARGETS = {
    "005WR0000036jGrYAI": {"IsActive": True},
    "005WR000003nr4fYAA": {"IsActive": True, "FirstName": "Michell",
                           "TimeZoneSidKey": "America/Chicago"},
}
FIELDS = ["Id", "FirstName", "LastName", "Username", "Email", "IsActive",
          "TimeZoneSidKey", "Profile.Name", "LastLoginDate"]


def snapshot():
    ids = "','".join(TARGETS)
    recs = sf.query(f"SELECT {', '.join(FIELDS)} FROM User WHERE Id IN ('{ids}')")["records"]
    return {r["Id"]: {**{k: r[k] for k in FIELDS if "." not in k},
                      "Profile.Name": r["Profile"]["Name"]} for r in recs}


before = snapshot()
if len(before) != len(TARGETS):
    sys.exit(f"ABORT: expected {len(TARGETS)} users, found {len(before)}")

print("PREVIEW" if not APPLY else "APPLYING")
changes = {}
for uid, want in TARGETS.items():
    b = before[uid]
    if b["Profile.Name"] != "Standard User - Custom":
        sys.exit(f"ABORT: {b['Username']} profile is {b['Profile.Name']!r}, re-check access")
    diff = {k: v for k, v in want.items() if b[k] != v}
    changes[uid] = diff
    print(f"  {b['FirstName']} {b['LastName']} ({b['Username']})")
    for k, v in diff.items():
        print(f"    {k}: {b[k]!r} -> {v!r}")
    if not diff:
        print("    no change needed")

if APPLY:
    for uid, diff in changes.items():
        if diff:
            sf.User.update(uid, diff)
    after = snapshot()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"user_reactivate_avr_handlers_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(log, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "field", "before", "after"])
        for uid in TARGETS:
            for k in FIELDS[1:]:
                w.writerow([uid, k, before[uid][k], after[uid][k]])
    print(f"\nAudit log: {log}")

    bad = [(uid, k) for uid, want in TARGETS.items() for k, v in want.items() if after[uid][k] != v]
    if bad:
        sys.exit(f"VERIFY FAILED: {bad}")
    print("Verified: all target values read back from Salesforce.")

if SEND_LOGIN:
    if not APPLY and not all(before[u]["IsActive"] for u in TARGETS):
        sys.exit("ABORT: users must be active before sending login email (run with --apply)")
    for uid in TARGETS:
        body = f"System.resetPassword('{uid}', true);"
        res = sf.toolingexecute("executeAnonymous/", method="GET",
                                params={"anonymousBody": body})
        print(f"  login email {uid}: compiled={res['compiled']} success={res['success']} "
              f"{res.get('exceptionMessage') or res.get('compileProblem') or ''}")
