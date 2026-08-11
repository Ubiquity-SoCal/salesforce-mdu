"""
Link the 3 SMB (Business_ROE) COMPLETED IronClad ROEs that have a matching existing
Opportunity (verified by same street address + city) but no Agreement__c record.

Creates one ROE Agreement__c per Opp, populated from the IronClad workflow and linked
via IronClad_Record__c (lookup) + IronClad_ID__c (text). Follows the standard signed-date
rule: Signed_Date__c = Agreement Date (only because all three are Completed).

Mapping is HARDCODED (verified 2026-07-01, see _probes/2026-07-01-smb-roe-final-match.py) --
no fuzzy matching in the write path. The other 21 SMB completed ROEs have no existing Opp
and are intentionally left for an Opp-backfill decision.

PREVIEW by default. Run with --apply to write.
Audit: SalesForce/data/output/audit_logs/link_smb_roes_<ts>.csv
"""
import sys, csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv

# IronClad Id -> Opportunity Id  (verified same-address matches)
MAP = {
    "IC-3754": "006WR000011kjHLYAY",  # 535 W Iron Ave, Mesa AZ
    "IC-4027": "006WR000011kit8YAA",  # 2202 US-380, Bridgeport TX
    "IC-4034": "006WR000011kjJ7YAI",  # 900 N Austin Ave, Georgetown TX
}

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

ids_str = "','".join(MAP)
ic = {r["IronClad_Id__c"]: r for r in sf.query_all(
    f"SELECT Id, IronClad_Id__c, Stage_IC__c, Agreement_Date__c, Effective_Date__c, "
    f"Expiration_Date__c, Workflow_Completed_Date__c, Counterparty_Name__c "
    f"FROM IronClad__c WHERE IronClad_Id__c IN ('{ids_str}')")["records"]}
opp_ids_str = "','".join(MAP.values())
opps = {o["Id"]: o for o in sf.query_all(
    f"SELECT Id, Name, StageName FROM Opportunity WHERE Id IN ('{opp_ids_str}')")["records"]}

# Safety: confirm none of these Opps already has an Agreement (avoid duplicates)
existing = sf.query_all("SELECT Id, Opportunity__c FROM Agreement__c WHERE Opportunity__c IN ('"
                        + "','".join(MAP.values()) + "')")["records"]
existing_by_opp = {}
for a in existing:
    existing_by_opp.setdefault(a["Opportunity__c"], []).append(a["Id"])

to_create = []
for ic_id, opp_id in MAP.items():
    r = ic[ic_id]
    if existing_by_opp.get(opp_id):
        print(f"  SKIP {ic_id}: Opp {opp_id} already has Agreement(s) {existing_by_opp[opp_id]} -- not creating a duplicate")
        continue
    if (r.get("Stage_IC__c") or "").lower() != "completed":
        print(f"  SKIP {ic_id}: IronClad stage is '{r.get('Stage_IC__c')}', not completed")
        continue
    signed = r.get("Agreement_Date__c") or r.get("Effective_Date__c")
    body = {
        "Opportunity__c": opp_id,
        "Agreement_Type__c": "ROE",
        "Status__c": "Completed",
        "Signed_Date__c": signed,
        "IronClad_ID__c": ic_id,
        "IronClad_Record__c": r["Id"],
    }
    if r.get("Expiration_Date__c"):
        body["Expiration_Date__c"] = r["Expiration_Date__c"]
    to_create.append((ic_id, opp_id, body))

print(f"\nWill create {len(to_create)} ROE Agreement(s):")
for ic_id, opp_id, body in to_create:
    print(f"  {ic_id}  ->  {opps[opp_id]['Name']}  [{opps[opp_id]['StageName']}]  signed={body['Signed_Date__c']}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"link_smb_roes_{ts}.csv"
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Action", "IronClad_Id", "Opportunity_Id", "Opp_Name", "Agreement_Type",
                "Status", "Signed_Date", "New_Agreement_Id", "Timestamp"])
    for ic_id, opp_id, body in to_create:
        w.writerow([("CREATE" if APPLY else "PREVIEW"), ic_id, opp_id, opps[opp_id]["Name"],
                    "ROE", "Completed", body["Signed_Date__c"], "", datetime.now().isoformat()])
print(f"\nAudit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to create.")
    sys.exit(0)

ok = fail = 0
created = []
for ic_id, opp_id, body in to_create:
    try:
        res = sf.Agreement__c.create(body)
        created.append((ic_id, opp_id, res.get("id")))
        ok += 1
        print(f"  created {res.get('id')} for {ic_id} -> {opps[opp_id]['Name']}")
    except Exception as e:
        fail += 1
        print(f"  ! {ic_id}: {e}")
# rewrite audit with created ids
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Action", "IronClad_Id", "Opportunity_Id", "Opp_Name", "Agreement_Type",
                "Status", "Signed_Date", "New_Agreement_Id", "Timestamp"])
    cmap = {ic_id: new_id for ic_id, _, new_id in created}
    for ic_id, opp_id, body in to_create:
        w.writerow(["CREATE", ic_id, opp_id, opps[opp_id]["Name"], "ROE", "Completed",
                    body["Signed_Date__c"], cmap.get(ic_id, ""), datetime.now().isoformat()])
print(f"\nCreated: ok={ok} fail={fail}\nAudit: {audit}")
