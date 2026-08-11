"""
Backfill IronClad_ID__c on the 17 Killeen ROE Agreements from the
"ROEs_Missing IC#_enriched.xlsx" enrichment Koa provided (2026-06-22).

Matches Agreement__c by Name (AGR-####). Sets ONLY IronClad_ID__c (text).
Does NOT touch Status__c / Signed_Date__c (already populated upstream).
Linking IronClad_ID__c -> IronClad_Record__c is a SEPARATE step:
run sync/link_orphan_ironclad_agreements.py --apply afterward (this script
reports whether the IronClad__c parents exist so you know if linking is possible).

AGR-1378 (KILLEEN_MDU_4308 Zephyr Rdt_APTS) is intentionally EXCLUDED:
its source value was the free-text "PAL executed", not an IC-#### id.

PREVIEW only by default. Run with --apply to write.
Audit: SalesForce/data/output/audit_logs/set_killeen_ironclad_ids_<TS>.csv
"""
import sys
import csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = _SF["username"]
PASSWORD = _SF["password"]
SECURITY_TOKEN = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
SOURCE = "2026-06-22-set-killeen-ironclad-ids.py"

# AGR Name -> (expected Opp name for sanity, IronClad Id to set)
MAPPING = {
    "AGR-1390": ("Killeen_MDU_East Gate Apartments", "IC-2797"),
    "AGR-1368": ("Killeen_MDU_Villa Del North", "IC-2583"),
    "AGR-1369": ("Killeen_MDU_1015-1017 Parmer Ave", "IC-2586"),
    "AGR-1372": ("Killeen_MDU_201 W Green Ave", "IC-2719"),
    "AGR-1373": ("Killeen_MDU_209 E Dean Ave", "IC-2720"),
    "AGR-1374": ("Killeen_MDU_Magnolia Heights", "IC-2794"),
    "AGR-1377": ("Killeen_MDU_425 N Gilmer St", "IC-2721"),
    "AGR-1379": ("Killeen_MDU_5 W Rancier Ave", "IC-2729"),
    "AGR-1380": ("Killeen_MDU_511 N Gilmer & 512 Wyoming St", "IC-2810"),
    "AGR-1381": ("Killeen_MDU_601 Harbour Ave", "IC-2722"),
    "AGR-1382": ("Killeen_MDU_602 N 2nd St", "IC-2723"),
    "AGR-1383": ("Killeen_MDU_Downtown Manor", "IC-2611"),
    "AGR-1384": ("Killeen_MDU_Stringer St Apts", "IC-2676"),
    "AGR-1385": ("Killeen_MDU_The Links Apts", "IC-2855"),
    "AGR-1386": ("Killeen_MDU_703 Gilmer Street Apartments", "IC-2724"),
    "AGR-1388": ("Killeen_MDU_813 N Park St Apartments", "IC-2811"),
}
# Excluded on purpose (not a valid IronClad id):
EXCLUDED = {"AGR-1378": ("KILLEEN_MDU_4308 Zephyr Rdt_APTS", "PAL executed")}

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

names = list(MAPPING.keys())
names_str = "','".join(names)
recs = sf.query_all(
    f"""SELECT Id, Name, IronClad_ID__c, IronClad_Record__c, Status__c,
               Opportunity__r.Name
        FROM Agreement__c WHERE Name IN ('{names_str}')"""
)['records']
by_name = {r['Name']: r for r in recs}

# Which IronClad__c parents already exist for the target IC ids?
ic_ids = [ic for _, ic in MAPPING.values()]
ic_str = "','".join(ic_ids)
parents = sf.query_all(
    f"SELECT Id, IronClad_Id__c, Agreement__c FROM IronClad__c WHERE IronClad_Id__c IN ('{ic_str}')"
)['records']
parent_by_id = {p['IronClad_Id__c']: p for p in parents}

to_set, no_change, conflict, missing, name_mismatch = [], [], [], [], []
for agr, (exp_opp, ic) in MAPPING.items():
    r = by_name.get(agr)
    if not r:
        missing.append((agr, ic))
        continue
    opp = (r.get('Opportunity__r') or {}).get('Name')
    if opp and exp_opp and opp.strip().lower() != exp_opp.strip().lower():
        name_mismatch.append((agr, exp_opp, opp))
    cur = r.get('IronClad_ID__c')
    if cur == ic:
        no_change.append((agr, ic))
    elif cur and cur != ic:
        conflict.append((agr, cur, ic, r))
    else:
        to_set.append((agr, ic, r))

print(f"Target agreements in mapping: {len(MAPPING)}  (excluded: {list(EXCLUDED)})")
print(f"Found in SF: {len(recs)}/{len(MAPPING)}")
print(f"\n  WILL SET (currently blank):   {len(to_set)}")
for agr, ic, r in to_set:
    has_parent = "parent OK" if ic in parent_by_id else "NO IronClad__c parent"
    print(f"    {agr}  ->  {ic}   [{has_parent}]   ({(r.get('Opportunity__r') or {}).get('Name')})")
print(f"\n  ALREADY SET (no change):      {len(no_change)}  {[a for a,_ in no_change]}")
print(f"  CONFLICT (different id set):   {len(conflict)}")
for agr, cur, ic, r in conflict:
    print(f"    {agr}  has {cur}  but mapping says {ic}  -> SKIPPED, review")
print(f"  NOT FOUND in SF:              {len(missing)}  {missing}")
print(f"  NAME MISMATCH (sanity):       {len(name_mismatch)}")
for agr, exp, got in name_mismatch:
    print(f"    {agr}  expected '{exp}'  got '{got}'")

linkable = sum(1 for _, ic, _ in to_set if ic in parent_by_id)
print(f"\n  IronClad__c parents present for {linkable}/{len(to_set)} to-set ids.")
print(f"  Missing-parent ids: {[ic for _, ic, _ in to_set if ic not in parent_by_id]}")

# Audit
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"set_killeen_ironclad_ids_{ts}.csv"
with open(audit, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(["Action", "SF_Id", "Name", "Field", "Before", "After", "Parent_Exists", "Source", "Timestamp"])
    act = "UPDATE" if APPLY else "PREVIEW"
    for agr, ic, r in to_set:
        w.writerow([act, r['Id'], agr, "IronClad_ID__c", r.get('IronClad_ID__c') or "", ic,
                    ic in parent_by_id, SOURCE, datetime.now().isoformat()])
    for agr, cur, ic, r in conflict:
        w.writerow(["CONFLICT", r['Id'], agr, "IronClad_ID__c", cur, ic, ic in parent_by_id, SOURCE, datetime.now().isoformat()])
    for agr, ic in missing:
        w.writerow(["NOT_FOUND", "", agr, "IronClad_ID__c", "", ic, "", SOURCE, datetime.now().isoformat()])
print(f"\nAudit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to write.")
    sys.exit(0)

import requests

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

headers = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
url = f'{sf.base_url}composite/sobjects'
records = [{'attributes': {'type': 'Agreement__c'}, 'Id': r['Id'], 'IronClad_ID__c': ic}
           for agr, ic, r in to_set]
ok = fail = 0
for i in range(0, len(records), 200):
    chunk = records[i:i+200]
    resp = requests.patch(url, headers=headers, json={'allOrNone': False, 'records': chunk}, timeout=120)
    if resp.status_code == 200:
        for res in resp.json():
            if res.get('success'):
                ok += 1
            else:
                fail += 1
                print(f"  ! {res.get('errors')}")
    else:
        fail += len(chunk)
        print(f"  ! HTTP {resp.status_code}: {resp.text[:300]}")
print(f"\nSet IronClad_ID__c: ok={ok} fail={fail}")
print("Next: run sync/link_orphan_ironclad_agreements.py --apply to link parents where present.")
