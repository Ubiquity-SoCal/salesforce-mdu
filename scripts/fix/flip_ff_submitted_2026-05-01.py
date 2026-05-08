"""
Flip Submitted_to_FiberFirst__c=true on all 32 Opps with
Sales_Status__c='FF Sales - Tenant Interest Required'.

Per Koa's rule: Sales_Status='FF Sales - Tenant Interest Required'
implies Submitted_to_FiberFirst__c=True (Stage already=Engaged on all 32).

Audit log: SalesForce/audit_logs/ff_submitted_flip_<timestamp>.csv
"""

import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"

LOG_DIR = Path("C:/Users/cass/Work_Projects/SalesForce/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

SOURCE = "flip_ff_submitted_2026-05-01.py"


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    soql = """
        SELECT Id, Name, Submitted_to_FiberFirst__c
        FROM Opportunity
        WHERE Sales_Status__c = 'FF Sales - Tenant Interest Required'
    """
    rows = sf.query_all(soql)["records"]
    print(f"Found {len(rows)} Opps with Sales_Status=FF Sales - Tenant Interest Required")

    to_update = [r for r in rows if r["Submitted_to_FiberFirst__c"] is False]
    print(f"  {len(to_update)} need flipping (Submitted_to_FiberFirst__c=false -> true)")

    if not to_update:
        print("Nothing to do.")
        return

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"ff_submitted_flip_{timestamp}.csv"

    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])

        for r in to_update:
            sf.Opportunity.update(r["Id"], {"Submitted_to_FiberFirst__c": True})
            writer.writerow([
                r["Id"], r["Name"], "Submitted_to_FiberFirst__c",
                "false", "true", SOURCE, timestamp, "update"
            ])
            print(f"  Updated {r['Id']}  {r['Name']}")

    print(f"\nDone. Audit log: {log_path}")


if __name__ == "__main__":
    main()
