"""
Link 3 SiteTracker_Project__c records to their matching Opportunities.

Sourced from the 2026-05-13 review of MDU CX Update file
(`MDU CX Update 5-6-2026_2.xlsx`). All 56 CX projects were matched to ST in SF,
but 3 ST records had `Opportunity__c = null`. Candidate Opps verified by:
  - exact / near-exact site name match
  - same city + street fragment
  - confirmed by Koa 2026-05-13

  P-006862 -> 006WR00000wk9RtYAI  (117 and 121 E Avenue A Apartments)
              ST says W, Opp says E. Same number pair, same street, same city.
              Likely a directional typo on one side.
  P-006876 -> 006WR00000y2FzkYAE  (Omaha_MDU_4760 LAFAYETTE AVE)
              ST.Name says 4750. CX full address says 4760 (matches Opp).
              Typo is on the SiteTracker side.
  P-006899 -> 006WR00000xwF7xYAE  (Omaha_MDU_360 Skyview)
              ST suffix "-2" indicates Phase 2 ST project on the same property.

Usage:
  python 2026-05-13-sitetracker-opportunity-link.py            # dry-run
  python 2026-05-13-sitetracker-opportunity-link.py --execute  # push
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sys.stdout.reconfigure(line_buffering=True)

EXECUTE = '--execute' in sys.argv

AUDIT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs\2026-05-13-sitetracker-opportunity-link.csv")
SOURCE_LABEL = 'fix/2026-05-13-sitetracker-opportunity-link.py'

LINKS = [
    ('P-006862', '006WR00000wk9RtYAI', '117 and 121 E Avenue A Apartments'),
    ('P-006876', '006WR00000y2FzkYAE', 'Omaha_MDU_4760 LAFAYETTE AVE'),
    ('P-006899', '006WR00000xwF7xYAE', 'Omaha_MDU_360 Skyview'),
]

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)


def main():
    print(f"[INFO] Mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}\n")

    # Re-pull current state of the 3 ST records to confirm they're still unlinked
    pids = [l[0] for l in LINKS]
    quoted = ",".join(f"'{p}'" for p in pids)
    res = sf.query(
        f"SELECT Id, Name, Site_Name__c, Opportunity__c, Opportunity__r.Name "
        f"FROM SiteTracker_Project__c WHERE Name IN ({quoted})"
    )
    st_by_pid = {r['Name']: r for r in res['records']}

    plan = []  # (st_sf_id, pid, st_site_name, opp_id, opp_name, status)
    for pid, opp_id, opp_name in LINKS:
        st = st_by_pid.get(pid)
        if not st:
            plan.append((None, pid, '<missing>', opp_id, opp_name, 'SKIP-st-missing'))
            continue
        if st.get('Opportunity__c'):
            existing = (st.get('Opportunity__r') or {}).get('Name')
            plan.append((st['Id'], pid, st['Site_Name__c'], opp_id, opp_name, f'SKIP-already-linked-to-{existing}'))
        else:
            plan.append((st['Id'], pid, st['Site_Name__c'], opp_id, opp_name, 'READY'))

    print("Plan:")
    for row in plan:
        print(f"  {row[1]} ({row[2][:40]:<42}) -> {row[3]} {row[4][:40]}  [{row[5]}]")

    if not EXECUTE:
        print("\n[INFO] Dry-run. Re-run with --execute to push.")
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action', 'Provenance'])

    stamp = datetime.now().isoformat(timespec='seconds')
    ok = 0
    failed = 0
    skipped = 0
    with AUDIT_PATH.open('a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for st_id, pid, site, opp_id, opp_name, status in plan:
            if status != 'READY':
                skipped += 1
                w.writerow([st_id or '', pid, 'Opportunity__c', '', '', SOURCE_LABEL, stamp, status, ''])
                continue
            try:
                sf.SiteTracker_Project__c.update(st_id, {'Opportunity__c': opp_id})
                action = 'linked'
                ok += 1
            except Exception as e:
                action = f'FAILED: {type(e).__name__}: {str(e)[:120]}'
                failed += 1
                print(f"  FAIL {pid} -> {opp_id}: {action}")
            w.writerow([st_id, pid, 'Opportunity__c', '', opp_id, SOURCE_LABEL, stamp, action, f'opp_name={opp_name}'])

    print(f"\n[RESULT] {ok} linked, {failed} failed, {skipped} skipped.")
    print(f"[RESULT] Audit log: {AUDIT_PATH}")


if __name__ == '__main__':
    main()
