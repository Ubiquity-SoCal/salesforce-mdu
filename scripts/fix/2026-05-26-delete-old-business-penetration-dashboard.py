"""Delete the standalone Business Penetration dashboard (01ZWR000004X6if2AC)
now that the Market Penetration tab on InsideSalesDashboard.page covers it.

Default = dry-run + snapshot only. Pass --apply to actually delete.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

DRY_RUN = "--apply" not in sys.argv
DASHBOARD_ID = "01ZWR000004X6if2AC"

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)

# 1. Snapshot dashboard metadata as rollback ref
result = sf.restful(f"sobjects/Dashboard/{DASHBOARD_ID}", method="GET")
OUT = Path("C:/Users/cass/Work_Projects/SalesForce/data/output/audit_logs")
OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
snap = OUT / f"business_penetration_dashboard_snapshot_{ts}.json"
snap.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"[INFO] Snapshot: {snap}")
print(f"[INFO] Dashboard: {result.get('DeveloperName')} / {result.get('Title')}")

if DRY_RUN:
    print("\nDRY RUN. Re-run with --apply to delete.")
    sys.exit(0)

# 2. Delete
deleted = sf.restful(f"sobjects/Dashboard/{DASHBOARD_ID}", method="DELETE")
print(f"[INFO] Delete response: {deleted}")
print("[SUCCESS] Dashboard deleted.")
