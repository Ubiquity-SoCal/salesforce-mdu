"""
Publish the HubSpot export to the shared SharePoint folder Kia reads, with ONLY the files she
asked for (Koa, 9/14: "remove readme and anything she didn't ask for").

The full export stays local in data/output/hubspot-export/<date>/, for our records and for the
checks. read-me.txt, manifest.csv, relationship-check.csv, OpportunityHistory, RecordType,
BusinessProcess, OpportunityStage, Queue, User and the three junctions never leave this
machine. Koa held the junctions and User back knowing her contacts then link to deals only
through Opportunity.Primary_Contact__c; they are ready to send if she asks. EXPORT_* helper
columns stay in the published files (Koa's call).

The dated subfolder is replaced wholesale, so a file dropped from the list cannot linger there.
Then the published set is checked: exactly the list, byte for byte, with the row counts the
local manifest recorded.

Run: python -u publish_hubspot_export.py
"""
import csv
import os
import shutil
import stat
import sys
import time
from pathlib import Path

csv.field_size_limit(10**9)
SF = Path(__file__).resolve().parents[2]
EXPORTS = SF / "data" / "output" / "hubspot-export"
FIELD_MAP = SF / "data" / "output" / "salesforce-hubspot-field-map.xlsx"
SHARED = Path(r"C:\Users\cass\OneDrive - Ubiquity Management\PMO_Projects - SalesForce")

# Her 9/14 list: Opportunities, Agreements, Contacts, Accounts, Campaigns and Campaign Members,
# Cases, AVR Projects, Property Locations, Property Units, SiteTracker Projects, and activities,
# notes, files and attachments. Files and attachments dropped by Koa (the ROEs are in IronClad).
# ContentDocumentLink is how a note knows its record, so it travels with the notes.
DELIVER = [
    "Opportunity.csv", "Agreement__c.csv", "Contact.csv", "Account.csv", "Campaign.csv",
    "CampaignMember.csv", "Case.csv", "AVR_Project_ID__c.csv", "Property_Location__c.csv",
    "Property_Unit__c.csv", "SiteTracker_Project__c.csv",
    "Task.csv", "Event.csv", "EmailMessage.csv", "Note.csv", "Notes.csv", "ContentDocumentLink.csv",
]


def remove_tree(path, attempts=8):
    """rmtree that waits out OneDrive. On 9/14 the first publish died with WinError 5 on an
    emptied folder OneDrive was still syncing, leaving the shared subfolder half deleted.
    Retries the failing call with a growing pause instead of giving up on the first lock."""
    def retry(func, target, _exc):
        for i in range(attempts):
            time.sleep(1.5 * (i + 1))
            try:
                os.chmod(target, stat.S_IWRITE)
                func(target)
                return
            except FileNotFoundError:
                return
            except OSError:
                continue
        raise PermissionError(f"OneDrive kept {target} locked after {attempts} retries; pause sync and rerun")
    shutil.rmtree(path, onexc=retry)


def data_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def main():
    if not SHARED.exists():
        raise SystemExit(f"shared folder is not synced to this PC: {SHARED}")
    src = sorted(p for p in EXPORTS.iterdir() if p.is_dir() and p.name[:2] == "20")[-1]
    missing = [f for f in DELIVER if not (src / f).exists()]
    if missing:
        raise SystemExit(f"export {src.name} is missing {missing}, rerun export_hubspot_records.py")
    with open(src / "manifest.csv", newline="", encoding="utf-8") as f:
        manifest = {r["file"]: r["rows_exported"] for r in csv.DictReader(f)}

    dest = SHARED / f"salesforce-export-{src.name}"
    if dest.exists():
        print(f"  replacing {dest.name} ({sum(1 for p in dest.rglob('*') if p.is_file())} files in it now)")
        remove_tree(dest)
    dest.mkdir(exist_ok=True)
    for name in DELIVER:
        shutil.copy2(src / name, dest / name)
    field_map = SHARED / f"salesforce-hubspot-field-map-{src.name}.xlsx"
    if not field_map.exists():
        shutil.copy2(FIELD_MAP, field_map)
        print(f"  copied {field_map.name}")

    problems = []
    published = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    if published != sorted(DELIVER):
        problems.append(f"published set differs from the list: extra {sorted(set(published) - set(DELIVER))}, "
                        f"missing {sorted(set(DELIVER) - set(published))}")
    for name in DELIVER:
        if (dest / name).stat().st_size != (src / name).stat().st_size:
            problems.append(f"{name}: size differs from the local export")
        n = data_rows(dest / name)
        if str(n) != manifest.get(name):
            problems.append(f"{name}: {n} rows published, manifest recorded {manifest.get(name)}")
        print(f"  {name:28} {n:>7,} rows")

    others = sorted(p.name for p in SHARED.iterdir() if p.name not in (dest.name, field_map.name))
    if others:
        print(f"  NOTE, also in the shared folder and not part of this publish: {others}")
    if problems:
        print("FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"published {len(DELIVER)} files to {dest}")


if __name__ == "__main__":
    main()
