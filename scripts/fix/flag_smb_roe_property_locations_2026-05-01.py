"""
Set FF_Sales_Project__c='SMB ROE' on the 7 Property_Location__c records
that are linked to FF Sales Tenant Interest Required SMB ROE Opps but
not yet flagged for the SMB ROE report.

Audit log: SalesForce/audit_logs/smb_roe_pl_flag_<timestamp>.csv
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

SOURCE = "flag_smb_roe_property_locations_2026-05-01.py"


def main():
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    soql = """
        SELECT Property_Location__c, Property_Location__r.Name, Property_Location__r.FF_Sales_Project__c
        FROM Opportunity
        WHERE Sales_Status__c = 'FF Sales - Tenant Interest Required'
          AND Property_Location__c != NULL
          AND Property_Location__r.FF_Sales_Project__c = NULL
    """
    rows = sf.query_all(soql)["records"]
    print(f"Found {len(rows)} Property Locations to flag")

    pl_ids = sorted({r["Property_Location__c"] for r in rows})
    pl_names = {r["Property_Location__c"]: r["Property_Location__r"]["Name"] for r in rows}

    if not pl_ids:
        print("Nothing to do.")
        return

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"smb_roe_pl_flag_{timestamp}.csv"

    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])

        for pl_id in pl_ids:
            sf.Property_Location__c.update(pl_id, {"FF_Sales_Project__c": "SMB ROE"})
            writer.writerow([
                pl_id, pl_names[pl_id], "FF_Sales_Project__c",
                "null", "SMB ROE", SOURCE, timestamp, "update"
            ])
            print(f"  Flagged {pl_id}  {pl_names[pl_id]}")

    print(f"\nDone. Audit log: {log_path}")


if __name__ == "__main__":
    main()
