"""
List MDU/SFU Opportunities with a Projected_Close_Date__c that are NOT Cat 1.

Built 2026-05-13 alongside the InsideSalesDashboard Cat 1 filter. These Opps
silently disappear from the boss's Lane Forecast panel once the filter ships,
so this script makes the outliers visible for periodic review.

Two follow-up paths typically apply:
  - Blank/missing category -> rerun the serviceability lookup, may simply be a
    geocode failure that the tool can recover with a manual address fix.
  - Cat 2 / Cat 3 with a real projected date -> either the forecast is wrong
    (out-of-network deal being chased) or the categorization is wrong.

Output:
  SalesForce/data/output/projected-date-non-cat1-review-<date>.csv

Usage:
  python projected_date_non_cat1_review.py
"""
import csv
import sys
from datetime import date
from pathlib import Path

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

OUT_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output")
OUT_PATH = OUT_DIR / f"projected-date-non-cat1-review-{date.today().isoformat()}.csv"

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)


def main():
    soql = """
    SELECT Id, Name, StageName, Substatus__c,
           Property_Category__c, Property_Address__c, Property_City__c,
           Property_State__c, Property_Zip__c,
           Projected_Close_Date__c, CloseDate, Units__c, Amount,
           Owner.Name, LastActivityDate
    FROM Opportunity
    WHERE RecordType.DeveloperName IN ('MDU','SFU')
      AND IsClosed = false
      AND Projected_Close_Date__c != null
      AND (Property_Category__c != 'Cat 1' OR Property_Category__c = null)
    ORDER BY Projected_Close_Date__c ASC
    """
    res = sf.query(soql)
    rows = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        rows.extend(res['records'])

    print(f"[INFO] {len(rows)} MDU/SFU Opps with projected date but not Cat 1")
    if not rows:
        print("[INFO] Nothing to review.")
        return

    # Print summary to console
    from collections import Counter
    print("\n  By Property_Category:")
    for k, v in Counter(r['Property_Category__c'] for r in rows).most_common():
        print(f"    {(k or '(blank)'):<12} {v:>4}")
    print("\n  By Stage:")
    for k, v in Counter(r['StageName'] for r in rows).most_common():
        print(f"    {k:<30} {v:>4}")
    print("\n  By Owner:")
    for k, v in Counter(r['Owner']['Name'] for r in rows).most_common():
        print(f"    {k:<30} {v:>4}")

    # Write CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        'Id', 'Name', 'StageName', 'Substatus__c',
        'Property_Category__c', 'Property_Address__c', 'Property_City__c',
        'Property_State__c', 'Property_Zip__c',
        'Projected_Close_Date__c', 'CloseDate', 'Units__c', 'Amount',
        'OwnerName', 'LastActivityDate',
    ]
    with OUT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({
                'Id': r['Id'],
                'Name': r['Name'],
                'StageName': r['StageName'],
                'Substatus__c': r.get('Substatus__c'),
                'Property_Category__c': r.get('Property_Category__c'),
                'Property_Address__c': r.get('Property_Address__c'),
                'Property_City__c': r.get('Property_City__c'),
                'Property_State__c': r.get('Property_State__c'),
                'Property_Zip__c': r.get('Property_Zip__c'),
                'Projected_Close_Date__c': r.get('Projected_Close_Date__c'),
                'CloseDate': r.get('CloseDate'),
                'Units__c': r.get('Units__c'),
                'Amount': r.get('Amount'),
                'OwnerName': (r.get('Owner') or {}).get('Name'),
                'LastActivityDate': r.get('LastActivityDate'),
            })
    print(f"\n[RESULT] Wrote {len(rows)} rows -> {OUT_PATH}")


if __name__ == '__main__':
    main()
