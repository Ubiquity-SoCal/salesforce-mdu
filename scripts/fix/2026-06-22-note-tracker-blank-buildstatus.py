"""
Add an explanatory Salesforce Note (ContentNote) to each Opportunity that does NOT
show a SiteTracker build status in the MDU Agreements Milestone Tracker, so the team
knows WHY it's blank (per Koa, 2026-06-22 -- annotate rather than fix/dedupe).

Idempotent: skips an opp that already has a note with the same title.
Audit: SalesForce/data/output/audit_logs/tracker_blank_notes_<TS>.csv
"""
import sys, csv, base64
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER = _SF["username"]; PW = _SF["password"]; TOK = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
TITLE = "MDU Tracker - Build Status Note"

# opp_id -> explanatory body
NOTES = {
    "006WR00000wk1EFYAY": (  # Affordable Storage
        "MDU Agreements Tracker: intentionally not showing a build status. This is a "
        "self-storage / Mixed-Use (commercial) site, not a residential MDU. Per Niraj "
        "(6/22/2026), business/non-MDU sites are excluded from the MDU tracker. Record is "
        "currently MDU record type but should be treated as business for tracker purposes."
    ),
    "006WR000013P1ulYAC": (  # 1810 N 8th St_Colt RE
        "MDU Agreements Tracker: blank build status. The SiteTracker project "
        "'Killeen_MDU_1807 Mulford & 1810 N 8th St' is one combined project covering both "
        "buildings and is already linked to the sibling opp '1807 Mulford Apartments_Colt RE' "
        "(showing Design Phase). 1810 has no separate SiteTracker project, so its status is "
        "blank. One-line-vs-per-building decision pending (grouped with Benson Crest review)."
    ),
    "006WR00000wk9RyYAI": (  # Rivers Edge
        "MDU Agreements Tracker: blank build status. SiteTracker project "
        "'Georgetown_MDU_Linea Stillwater' (confirmed correct by Niraj 6/22/2026) is linked to "
        "the separate 'Linea Stillwater' opp, which carries the build status. Rivers Edge "
        "(115 Stone Mountain Rd, 92 units) vs Linea Stillwater (901 Big Rocky Bend, 230 units) "
        "share one project -- shared/duplicate, pending review with Benson Crest."
    ),
    "006WR00000wkEbDYAU": (  # Heritage Oaks
        "MDU Agreements Tracker: blank build status. No SiteTracker project exists for this "
        "property yet. Per Niraj (6/22/2026), blank = 'not yet in SiteTracker.' Will populate "
        "automatically once a SiteTracker project is created and linked."
    ),
}

sf = Salesforce(username=USER, password=PW, security_token=TOK)

# names for nicer logging
names = {r["Id"]: r["Name"] for r in sf.query_all(
    "SELECT Id, Name FROM Opportunity WHERE Id IN ('" + "','".join(NOTES) + "')")["records"]}

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"tracker_blank_notes_{ts}.csv"
rows = []
created = skipped = fail = 0

for opp_id, body in NOTES.items():
    nm = names.get(opp_id, opp_id)
    # idempotency: any existing note with this title already linked?
    existing = sf.query_all(
        f"SELECT ContentDocument.Title FROM ContentDocumentLink WHERE LinkedEntityId = '{opp_id}'"
    )["records"]
    if any((e.get("ContentDocument") or {}).get("Title") == TITLE for e in existing):
        print(f"SKIP (note already present): {nm}")
        skipped += 1
        rows.append(["SKIP", opp_id, nm, "", "already has note"])
        continue
    if not APPLY:
        print(f"WOULD ADD note -> {nm}")
        rows.append(["PREVIEW", opp_id, nm, "", body[:60] + "..."])
        continue
    try:
        content_b64 = base64.b64encode(esc(body).encode("utf-8")).decode("utf-8")
        note = sf.ContentNote.create({"Title": TITLE, "Content": content_b64})
        sf.ContentDocumentLink.create({
            "ContentDocumentId": note["id"], "LinkedEntityId": opp_id,
            "ShareType": "V", "Visibility": "AllUsers",
        })
        print(f"ADDED note -> {nm}  (note {note['id']})")
        created += 1
        rows.append(["CREATE", opp_id, nm, note["id"], body[:60] + "..."])
    except Exception as e:
        print(f"FAIL {nm}: {e}")
        fail += 1
        rows.append(["FAIL", opp_id, nm, "", str(e)[:120]])

with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Action", "Opp_Id", "Opp_Name", "Note_Id", "Detail"])
    w.writerows(rows)
print(f"\ncreated={created} skipped={skipped} fail={fail}")
print(f"Audit: {audit}")
if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to create the notes.")
