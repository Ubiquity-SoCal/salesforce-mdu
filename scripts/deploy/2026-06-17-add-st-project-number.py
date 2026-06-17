"""Surfaces the SiteTracker project number (P-XXXXXX, the mirror's Name) onto the
Opportunity as ST_Project_Number__c, so the tracker report can show it as a column.
The Opp's existing SiteTracker_Project_ID__c holds the raw SF record id (a2X...),
which is not human-readable. Adds the field + FLS, then backfills from the linked
SiteTracker_Project__c mirror (most-advanced build status per opp, matching how
ST_Build_Status__c is surfaced).

Freshness: backfilled here; for new opp<->ST links to stay current, add this to the
daily surface_to_opportunity.py in the Automation repo (follow-up, like the v2 design date)."""
import csv
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from _md_deploy import connect, deploy

sf = connect()

# 1. Add the field (granular CustomField member; Opportunity is standard so safe).
FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>ST_Project_Number__c</fullName>
        <label>SiteTracker Project #</label>
        <type>Text</type>
        <length>40</length>
        <description>SiteTracker project number (P-XXXXXX) from the most-advanced linked SiteTracker_Project__c mirror. Surfaced for the MDU Agreements Milestone Tracker.</description>
    </fields>
</CustomObject>"""

if "ST_Project_Number__c" not in [f["name"] for f in sf.Opportunity.describe()["fields"]]:
    if not deploy(sf, {"objects/Opportunity.object": FIELD},
                  [("Opportunity.ST_Project_Number__c", "CustomField")], "st-proj-num"):
        raise SystemExit(1)
    FLS = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<Profile xmlns="http://soap.sforce.com/2006/04/metadata">'
           '<fieldPermissions><editable>false</editable>'
           '<field>Opportunity.ST_Project_Number__c</field><readable>true</readable>'
           '</fieldPermissions></Profile>')
    for prof in ["Admin", "Standard User - Custom"]:
        deploy(sf, {f"profiles/{prof}.profile": FLS}, [(prof, "Profile")], f"fls-{prof}")
else:
    print("ST_Project_Number__c already exists; skipping field deploy.")

# 2. Build opp -> project number from the mirror (pick most-advanced build status).
def query_all(soql):
    out, r = [], sf.query(soql)
    out.extend(r["records"])
    while not r["done"]:
        r = sf.query_more(r["nextRecordsUrl"], True); out.extend(r["records"])
    return out

by_opp = defaultdict(list)
for m in query_all("SELECT Name, Build_Status__c, Opportunity__c FROM SiteTracker_Project__c WHERE Opportunity__c != null"):
    by_opp[m["Opportunity__c"]].append((m.get("Build_Status__c") or "", m["Name"]))

desired = {oid: max(rows)[1] for oid, rows in by_opp.items()}  # max() sorts by build status then name

# 3. Only update opps whose value differs (idempotent).
current = {r["Id"]: r.get("ST_Project_Number__c")
           for r in query_all("SELECT Id, ST_Project_Number__c FROM Opportunity "
                              "WHERE Id IN ('%s')" % "','".join(desired))}
changes = [(oid, current.get(oid), num) for oid, num in desired.items() if current.get(oid) != num]
print(f"Linked opps: {len(desired)} | updates needed: {len(changes)}")
for oid, before, after in changes[:5]:
    print(f"  {oid}  {before!r} -> {after!r}")

if changes:
    sf.bulk.Opportunity.update([{"Id": oid, "ST_Project_Number__c": num} for oid, _, num in changes])
    base = Path(__file__).resolve().parents[2] / "data" / "output" / "audit_logs"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = base / f"{datetime.now():%Y-%m-%d_%H%M%S}-st-project-number-backfill.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["SF_Id", "Field", "Before", "After", "Source", "Timestamp", "Action"])
        for oid, before, after in changes:
            w.writerow([oid, "ST_Project_Number__c", before, after,
                        "scripts/deploy/2026-06-17-add-st-project-number.py", ts, "update"])
    print(f"Applied {len(changes)} update(s). Audit: {path}")

# 4. Verify + show the Sub_Bucket__c (Stage Status) label for the report header.
sf2 = connect()
n = sf2.query("SELECT COUNT(Id) c FROM Opportunity WHERE ST_Project_Number__c != null")["records"][0]["c"]
lbl = next(f["label"] for f in sf2.Opportunity.describe()["fields"] if f["name"] == "Sub_Bucket__c")
print(f"\nOpps with ST_Project_Number__c populated: {n}")
print(f"Sub_Bucket__c label (report column header) = {lbl!r}")
sample = sf2.query("SELECT Name, ST_Project_Number__c, Sub_Bucket__c, ST_Build_Status__c FROM Opportunity WHERE ST_Project_Number__c != null LIMIT 3")["records"]
for r in sample:
    print("  ", {k: v for k, v in r.items() if k != "attributes"})
print("OK.")
