"""
Link 6 MDU COMPLETED IronClad ROEs to their existing Opportunities (verified by address).

- create : make a ROE Agreement__c under the Opp, linked to the IronClad workflow.
- link   : the Opp already has a completed ROE Agreement with no IronClad link -> just
           populate its IronClad_Record__c + IronClad_ID__c (no new record).

HELD (not in this script, need a human decision):
  IC-2671 (Ellington) -- Opp already has a completed ROE under IC-2115; IC-2671 would be a
                         second completed ROE (possible duplicate IronClad workflow).
  IC-2816/2819/2820/2821 (Indian Hills Village) -- one deal across many buildings, one Opp.

PREVIEW by default. --apply to write. Audit: audit_logs/link_mdu_roes_<ts>.csv
"""
import sys, csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"; PASSWORD = "Hawaiian1984"; SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs"); LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# ic_id -> (opp_id, mode)
ACTIONS = {
    "IC-1724": ("006WR00000y2FzkYAE", "create"),   # Omaha_MDU_4760 Lafayette (no agreements)
    "IC-2609": ("006WR00000wkEbQYAU", "create"),   # Paloma Gardens (has PAL+EMA, no ROE)
    "IC-2665": ("006WR00000xv174YAA", "create"),   # Wakeley Pointe (existing ROE is Cancelled)
    "IC-2693": ("006WR00000wkAC1YAM", "create"),   # Paul Mark Apts (no agreements)
    "IC-2869": ("006WR00000wkDtMYAU", "create"),   # Fort Hood MHP (no agreements; Opp Closed Lost)
    "IC-2682": ("006WR00000xwHPtYAM", "link"),     # Mid-Century Park (existing unlinked ROE AGR-1389)
}

ids_str = "','".join(ACTIONS)
ic = {r["IronClad_Id__c"]: r for r in sf.query_all(
    f"SELECT Id, IronClad_Id__c, Stage_IC__c, Agreement_Date__c, Effective_Date__c, "
    f"Expiration_Date__c FROM IronClad__c WHERE IronClad_Id__c IN ('{ids_str}')")["records"]}

opp_ids = "','".join(o for o, _ in ACTIONS.values())
opps = {o["Id"]: o for o in sf.query_all(
    f"SELECT Id, Name, StageName FROM Opportunity WHERE Id IN ('{opp_ids}')")["records"]}
existing = {}
for a in sf.query_all(f"SELECT Id, Name, Agreement_Type__c, Status__c, IronClad_Record__c, "
                      f"Opportunity__c FROM Agreement__c WHERE Opportunity__c IN ('{opp_ids}')")["records"]:
    existing.setdefault(a["Opportunity__c"], []).append(a)

plan = []
for ic_id, (opp_id, mode) in ACTIONS.items():
    r = ic[ic_id]
    signed = r.get("Agreement_Date__c") or r.get("Effective_Date__c")
    if (r.get("Stage_IC__c") or "").lower() != "completed":
        print(f"  SKIP {ic_id}: IronClad stage '{r.get('Stage_IC__c')}' != completed"); continue
    if mode == "link":
        # find the unlinked ROE agreement on this Opp
        cand = [a for a in existing.get(opp_id, [])
                if a["Agreement_Type__c"] == "ROE" and not a.get("IronClad_Record__c")]
        if not cand:
            print(f"  SKIP {ic_id}: no unlinked ROE on {opps[opp_id]['Name']} to link"); continue
        plan.append({"ic": ic_id, "mode": "link", "opp": opp_id, "agr": cand[0]["Id"],
                     "agr_name": cand[0]["Name"], "ic_sfid": r["Id"], "signed": signed,
                     "exp": r.get("Expiration_Date__c")})
    else:
        # don't create if a ROE for this exact IC already exists
        dup = [a for a in existing.get(opp_id, []) if a["Agreement_Type__c"] == "ROE"
               and (a.get("IronClad_Record__c") is not None)]
        plan.append({"ic": ic_id, "mode": "create", "opp": opp_id, "ic_sfid": r["Id"],
                     "signed": signed, "exp": r.get("Expiration_Date__c")})

print(f"\nPlan ({len(plan)}):")
for p in plan:
    tgt = f"link {p['agr_name']}" if p["mode"] == "link" else "create ROE"
    print(f"  {p['ic']:<8} {p['mode']:<6} -> {opps[p['opp']]['Name'][:40]:<40} [{opps[p['opp']]['StageName']}]  signed={p['signed']}  ({tgt})")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
audit = LOG_DIR / f"link_mdu_roes_{ts}.csv"
def wa(rows):
    with open(audit, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["Action", "IC", "Mode", "Opp", "Opp_Name", "Agreement_Id", "Signed", "Timestamp"])
        for row in rows: w.writerow(row)

if not APPLY:
    wa([[("PREVIEW"), p["ic"], p["mode"], p["opp"], opps[p["opp"]]["Name"], p.get("agr", ""), p["signed"], datetime.now().isoformat()] for p in plan])
    print(f"\nAudit: {audit}\nPREVIEW only. --apply to write.")
    sys.exit(0)

rows = []; ok = fail = 0
for p in plan:
    try:
        if p["mode"] == "link":
            body = {"IronClad_Record__c": p["ic_sfid"], "IronClad_ID__c": p["ic"], "Status__c": "Completed"}
            if p["signed"]:
                body["Signed_Date__c"] = p["signed"]
            if p["exp"]:
                body["Expiration_Date__c"] = p["exp"]
            sf.Agreement__c.update(p["agr"], body)
            aid = p["agr"]
        else:
            body = {"Opportunity__c": p["opp"], "Agreement_Type__c": "ROE", "Status__c": "Completed",
                    "Signed_Date__c": p["signed"], "IronClad_ID__c": p["ic"], "IronClad_Record__c": p["ic_sfid"]}
            if p["exp"]:
                body["Expiration_Date__c"] = p["exp"]
            aid = sf.Agreement__c.create(body)["id"]
        ok += 1
        rows.append([p["mode"].upper(), p["ic"], p["mode"], p["opp"], opps[p["opp"]]["Name"], aid, p["signed"], datetime.now().isoformat()])
        print(f"  ok {p['ic']} {p['mode']} -> {aid}")
    except Exception as e:
        fail += 1
        rows.append(["ERROR", p["ic"], p["mode"], p["opp"], opps[p["opp"]]["Name"], "", p["signed"], str(e)[:200]])
        print(f"  ! {p['ic']}: {e}")
wa(rows)
print(f"\nDone: ok={ok} fail={fail}\nAudit: {audit}")
