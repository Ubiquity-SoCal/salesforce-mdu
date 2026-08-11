"""
Set Build_Effort__c and User__c on 4 Property Locations from
SMB_ROE_Project.xlsx (the 4 of 7 newly-flagged PLs that matched the source).

Skipping RE_Notes__c per Koa: notes now live on the Opp records.

Audit log: SalesForce/audit_logs/pl_build_effort_4_<timestamp>.csv
"""

import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]

LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

SOURCE = "backfill_4pl_build_effort_2026-05-01.py"

TANYA_ID = "005WR0000030R1hYAE"

UPDATES = [
    # (PL Id, PL Name, Build_Effort, User Id)
    ("a01WR00000UGWKFYA5", "1855 W BASELINE RD MESA AZ", "Hard", TANYA_ID),
    ("a01WR00000YlMXNYA3", "320 E 10TH DR MESA AZ",      "Easy", TANYA_ID),
    ("a01WR00000YlMXIYA3", "303 E SOUTHERN AVE MESA AZ", "Hard", TANYA_ID),
    ("a01WR00000YlMXSYA3", "347 E SOUTHERN AVE MESA AZ", "Hard", TANYA_ID),
]


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"pl_build_effort_4_{timestamp}.csv"

    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])

        for pl_id, name, effort, user_id in UPDATES:
            current = sf.Property_Location__c.get(pl_id)
            before_effort = current.get("Build_Effort__c")
            before_user   = current.get("User__c")

            sf.Property_Location__c.update(pl_id, {
                "Build_Effort__c": effort,
                "User__c": user_id,
            })

            writer.writerow([pl_id, name, "Build_Effort__c", before_effort or "null", effort, SOURCE, timestamp, "update"])
            writer.writerow([pl_id, name, "User__c",         before_user   or "null", user_id, SOURCE, timestamp, "update"])
            print(f"  Updated {pl_id}  {name}  ->  Build_Effort={effort}, User=Tanya Friese")

    print(f"\nDone. Audit log: {log_path}")


if __name__ == "__main__":
    main()
