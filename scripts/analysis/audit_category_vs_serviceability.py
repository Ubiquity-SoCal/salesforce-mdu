"""
Audit current Property_Category__c against the serviceability lookup tool.

Pulls every open MDU/SFU Opportunity, geocodes addresses via Census batch,
looks up against the as-built Vetro point cloud, and writes a CSV showing:
  - current Property_Category__c
  - suggested category from the lookup
  - distance to nearest as-built fiber
  - nearest as-built fiber address

Output: SalesForce/data/output/category-audit-vs-serviceability.csv
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

# Pull in the Serviceability_Lookup modules
sys.path.insert(0, r"C:\Users\cass\Work_Projects\Serviceability_Lookup\scripts\lookup")
from serviceability import ServiceabilityIndex
from geocoder import geocode_batch

from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

OUT_PATH = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\category-audit-vs-serviceability.csv")

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)


def main():
    print("[INFO] Loading serviceability index...", flush=True)
    idx = ServiceabilityIndex.load()
    print(f"[INFO] Loaded {len(idx.df):,} as-built points.", flush=True)

    print("\n[INFO] Pulling open MDU/SFU Opps from SF...", flush=True)
    soql = """
    SELECT Id, Name, StageName, Property_Category__c, Franchise_Type__c,
           Property_Address__c, Property_City__c, Property_State__c, Property_Zip__c,
           OwnerId, Owner.Name, RecordType.DeveloperName
    FROM Opportunity
    WHERE RecordType.DeveloperName IN ('MDU','SFU')
      AND IsClosed = false
      AND Property_Address__c != null
    """
    res = sf.query(soql)
    opps = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        opps.extend(res['records'])
    print(f"[INFO] {len(opps):,} Opps to audit\n", flush=True)

    # Build geocoder batch input
    rows = []
    for o in opps:
        rows.append((
            o['Id'],
            o['Property_Address__c'] or '',
            o.get('Property_City__c') or '',
            o.get('Property_State__c') or '',
            o.get('Property_Zip__c') or '',
        ))

    print("[INFO] Batch geocoding via US Census...", flush=True)
    geocoded = geocode_batch(rows, chunk_size=1000)
    geo_by_id = {rid: (lat, lon, note) for rid, lat, lon, note in geocoded}
    n_geo_ok = sum(1 for _, lat, _, _ in geocoded if lat is not None)
    print(f"[INFO] Geocode success: {n_geo_ok:,} / {len(opps):,}\n", flush=True)

    print("[INFO] Running serviceability checks...", flush=True)
    out_rows = []
    for o in opps:
        lat, lon, gnote = geo_by_id.get(o['Id'], (None, None, "missing"))
        current_cat = o.get('Property_Category__c') or ''
        row = {
            'Id': o['Id'],
            'Name': o['Name'],
            'StageName': o['StageName'],
            'Owner': (o.get('Owner') or {}).get('Name', ''),
            'Property_Address': o['Property_Address__c'],
            'Property_City': o.get('Property_City__c', ''),
            'Property_State': o.get('Property_State__c', ''),
            'Property_Zip': o.get('Property_Zip__c', ''),
            'current_category': current_cat,
            'franchise_type': o.get('Franchise_Type__c') or '',
        }
        if lat is None or lon is None:
            row.update({
                'suggested_category': '',
                'distance_ft': '',
                'nearest_fiber_addr': '',
                'nearest_fdh': '',
                'via_optk': '',
                'change_type': 'geocode_failed',
                'geocode_note': gnote,
            })
        else:
            sres = idx.check_lat_lon(lat, lon)
            change = (
                'no_change' if sres.cat == current_cat
                else ('fill_blank' if not current_cat else 'change')
            )
            row.update({
                'suggested_category': sres.cat,
                'distance_ft': round(sres.distance_ft, 1),
                'nearest_fiber_addr': sres.nearest_addr,
                'nearest_fdh': sres.nearest_fdh or '',
                'via_optk': 'Y' if sres.via_optk else '',
                'change_type': change,
                'geocode_note': gnote,
            })
        out_rows.append(row)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # Summary
    print(f"\n[RESULT] Audit written: {OUT_PATH}\n", flush=True)
    print("Current x Suggested category:")
    grid = Counter((r['current_category'] or '(blank)', r['suggested_category'] or '(none)')
                   for r in out_rows)
    cats = ['Cat 1', 'Cat 2', 'Cat 3', '(blank)', '(none)']
    print(f"  {'current':<14} | {'->Cat 1':>8} {'->Cat 2':>8} {'->Cat 3':>8} {'->(none)':>10}")
    for c in cats:
        row = [grid.get((c, 'Cat 1'), 0), grid.get((c, 'Cat 2'), 0),
               grid.get((c, 'Cat 3'), 0), grid.get((c, '(none)'), 0)]
        if any(row):
            print(f"  {c:<14} | {row[0]:>8} {row[1]:>8} {row[2]:>8} {row[3]:>10}")

    print("\nChange-type breakdown:")
    for ct, n in Counter(r['change_type'] for r in out_rows).most_common():
        print(f"  {ct:<20} {n:>6,}")


if __name__ == '__main__':
    main()
