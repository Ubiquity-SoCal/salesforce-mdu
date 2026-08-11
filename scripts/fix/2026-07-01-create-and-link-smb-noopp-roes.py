"""
Create a Business_ROE Opportunity for each SMB COMPLETED ROE that has NO existing Opp,
then create + link its ROE Agreement__c (via IronClad_Record__c + IronClad_ID__c).

Naming convention matches the existing SMB ROE Opps: "ROE - <ADDRESS CITY STATE>".
Opp: RecordType=Business_ROE, StageName='PAL/ROE Complete' (all are completed ROEs),
CloseDate=IronClad Agreement Date. Address/City/State/Zip carried from IronClad.
Agreement: Type=ROE, Status=Completed, Signed_Date=Agreement Date, IC link populated.

Scope = the 21 SMB completed ROE gaps with no SF Opp (24 SMB completed minus the 3 that
already had an Opp and were linked in 2026-07-01-link-smb-completed-roes-to-opps.py).

PREVIEW by default. Run with --apply to write. Audit: audit_logs/create_link_smb_roes_<ts>.csv
"""
import sys, csv, re
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv

BUSINESS_ROE_RT = "012WR00000VunSPYAZ"
ALREADY_LINKED = {"IC-3754", "IC-4027", "IC-4034"}

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# Rebuild the SMB completed gap set from the latest gap CSV, minus already-linked
import glob

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

f = sorted(glob.glob("SalesForce/data/output/ironclad_roe_pal_coverage_gap_*.csv"))[-1]
gap_ids = {r["IronClad_Id"] for r in csv.DictReader(open(f, encoding="utf-8"))
           if r["Is_ROE_PAL"] == "True" and r["Stage"] == "completed" and r["MDU_or_BUS"] == "BUS"} - ALREADY_LINKED
ids_str = "','".join(sorted(gap_ids))
ic = sf.query_all(
    f"SELECT Id, IronClad_Id__c, Stage_IC__c, Counterparty_Name__c, Property_Address__c, "
    f"Property_City__c, Property_State__c, Property_Postcode__c, Agreement_Date__c, "
    f"Effective_Date__c, Expiration_Date__c FROM IronClad__c WHERE IronClad_Id__c IN ('{ids_str}')")["records"]

# Guard: don't create a second Opp if one already exists at this exact address (safety net
# against re-runs / anything the earlier match missed).
existing_opps = sf.query_all("SELECT Id, Property_Address__c, Property_City__c FROM Opportunity "
                             "WHERE Property_Address__c != null")["records"]
def akey(addr, city):
    line = str(addr or "").split(",")[0].splitlines()[0].lower()
    line = re.sub(r"[^a-z0-9]+", "", line)
    return line + "|" + re.sub(r"[^a-z]", "", str(city or "").lower())
existing_keys = {akey(o.get("Property_Address__c"), o.get("Property_City__c")) for o in existing_opps}

US_STATE = {"nebraska": "NE", "texas": "TX", "arizona": "AZ", "ne": "NE", "tx": "TX", "az": "AZ"}

# Records whose IronClad city/state fields are blank AND don't parse cleanly from the
# address string. Verified by hand from the ROE address.
OVERRIDES = {
    "IC-265": {"city": "Azle", "state": "TX", "zip": "76020"},  # 100-248 Park St, Azle TX
}

def derive_city_state(r):
    ov = OVERRIDES.get(r["IronClad_Id__c"])
    if ov:
        return ov["city"], ov["state"]
    city = r.get("Property_City__c"); state = r.get("Property_State__c")
    if not (city and state):  # e.g. IC-265 has city/state only inside the address string
        parts = [p.strip() for p in str(r.get("Property_Address__c") or "").replace("\n", ",").split(",") if p.strip()]
        # last two comma parts are usually "City" , "State ZIP"
        if len(parts) >= 2:
            city = city or parts[-2]
            tail = parts[-1]
            m = re.match(r"([A-Za-z ]+)", tail)
            if m and not state:
                state = m.group(1).strip()
    st = US_STATE.get(str(state or "").strip().lower(), str(state or "").strip()[:2].upper())
    return city, st

plan = []
for r in sorted(ic, key=lambda x: x["IronClad_Id__c"]):
    if (r.get("Stage_IC__c") or "").lower() != "completed":
        continue
    addr_line = str(r.get("Property_Address__c") or "").split(",")[0].splitlines()[0].strip()
    city, st = derive_city_state(r)
    if akey(r.get("Property_Address__c"), city) in existing_keys:
        print(f"  SKIP {r['IronClad_Id__c']}: an Opp already exists at {addr_line}, {city}")
        continue
    name = re.sub(r"\s+", " ", f"ROE - {addr_line} {city or ''} {st or ''}").strip().upper()[:120]
    signed = r.get("Agreement_Date__c") or r.get("Effective_Date__c")
    zipc = r.get("Property_Postcode__c") or (OVERRIDES.get(r["IronClad_Id__c"], {}).get("zip"))
    plan.append({
        "ic_id": r["IronClad_Id__c"], "ic_sfid": r["Id"], "name": name,
        "addr": addr_line, "city": city, "state": st, "zip": zipc,
        "signed": signed, "expiration": r.get("Expiration_Date__c"),
        "counterparty": r.get("Counterparty_Name__c"),
    })

print(f"\nWill create {len(plan)} Business_ROE Opp(s) + linked ROE Agreement(s):\n")
for p in plan:
    print(f"  {p['ic_id']:<8} {p['name'][:60]:<60} zip={p['zip'] or '?':<6} signed={p['signed']}")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"create_link_smb_roes_{ts}.csv"

def write_audit(rows):
    with open(audit, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Action", "IronClad_Id", "Opp_Name", "New_Opp_Id", "New_Agreement_Id",
                    "City", "State", "Signed_Date", "Counterparty", "Timestamp"])
        for row in rows:
            w.writerow(row)

if not APPLY:
    write_audit([["PREVIEW", p["ic_id"], p["name"], "", "", p["city"], p["state"],
                  p["signed"], p["counterparty"], datetime.now().isoformat()] for p in plan])
    print(f"\nAudit: {audit}\nPREVIEW only. Re-run with --apply to create {len(plan)} Opp+Agreement pairs.")
    sys.exit(0)

rows = []
ok = fail = 0
for p in plan:
    try:
        opp_body = {
            "Name": p["name"], "RecordTypeId": BUSINESS_ROE_RT, "StageName": "PAL/ROE Complete",
            "CloseDate": p["signed"] or datetime.utcnow().strftime("%Y-%m-%d"),
            "Property_Address__c": p["addr"], "Property_City__c": p["city"],
            "Property_State__c": p["state"], "Property_Zip__c": p["zip"],
        }
        opp_id = sf.Opportunity.create(opp_body)["id"]
        agr_body = {
            "Opportunity__c": opp_id, "Agreement_Type__c": "ROE", "Status__c": "Completed",
            "Signed_Date__c": p["signed"], "IronClad_ID__c": p["ic_id"], "IronClad_Record__c": p["ic_sfid"],
        }
        if p["expiration"]:
            agr_body["Expiration_Date__c"] = p["expiration"]
        agr_id = sf.Agreement__c.create(agr_body)["id"]
        ok += 1
        rows.append(["CREATE", p["ic_id"], p["name"], opp_id, agr_id, p["city"], p["state"],
                     p["signed"], p["counterparty"], datetime.now().isoformat()])
        print(f"  ok {p['ic_id']} -> Opp {opp_id} + Agr {agr_id}")
    except Exception as e:
        fail += 1
        rows.append(["ERROR", p["ic_id"], p["name"], "", "", p["city"], p["state"],
                     p["signed"], p["counterparty"], str(e)[:200]])
        print(f"  ! {p['ic_id']}: {e}")
write_audit(rows)
print(f"\nCreated: ok={ok} fail={fail}\nAudit: {audit}")
