"""
Record the 2 confirmed completed MDU ROEs that Vetro's agreename matched to existing Opps:
  IC-2667 (Vance)         -> LINK the Opp's existing unlinked ROE (AGR-1371) to IronClad.
  IC-2816 (Indian Hills)  -> CREATE a ROE under the Opp (has a PAL, no ROE). Guarded: skip if a ROE already exists.

Held (duplicate risk, same pattern -- Opp already has a completed ROE under a different IC):
  IC-2671 Ellington (vs IC-2115),  IC-1823 Rose Apartments (vs IC-1817).
Truly-new MDU (need new Opps, Taylor): IC-1723 (4750 Lafayette), IC-2819/2820/2821 (Indian Hills "-2").

PREVIEW by default. --apply to write. Audit: audit_logs/completed_mdu_vetro_<ts>.csv
"""
import sys, csv
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME="cass1@ubiquitygp.com"; PASSWORD="Hawaiian1984"; SECURITY_TOKEN="IBSKT6CFUpSUJWxq1CMm0HkFC"
LOG=Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs"); LOG.mkdir(parents=True, exist_ok=True)
APPLY="--apply" in sys.argv
sf=Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# ic -> (opp_id, mode)
ACTIONS = {
    "IC-2667": ("006WR00000xvW9GYAU", "link"),    # Taylor_MDU_Vance Apartments (unlinked ROE AGR-1371)
    "IC-2816": ("006WR00000wkBTuYAM", "create"),   # Indian Hills Village Apartments (PAL only, no ROE)
}
ic={r["IronClad_Id__c"]: r for r in sf.query_all(
    "SELECT Id, IronClad_Id__c, Stage_IC__c, Agreement_Date__c, Effective_Date__c, Expiration_Date__c "
    "FROM IronClad__c WHERE IronClad_Id__c IN ('IC-2667','IC-2816')")["records"]}
opp_ids="','".join(o for o,_ in ACTIONS.values())
opps={o["Id"]: o for o in sf.query_all(f"SELECT Id, Name, StageName FROM Opportunity WHERE Id IN ('{opp_ids}')")["records"]}
existing={}
for a in sf.query_all(f"SELECT Id, Name, Agreement_Type__c, Status__c, IronClad_Record__c, Opportunity__c "
                      f"FROM Agreement__c WHERE Opportunity__c IN ('{opp_ids}')")["records"]:
    existing.setdefault(a["Opportunity__c"], []).append(a)

plan=[]
for icid,(opp_id,mode) in ACTIONS.items():
    r=ic[icid]; signed=r.get("Agreement_Date__c") or r.get("Effective_Date__c")
    if (r.get("Stage_IC__c") or "").lower()!="completed":
        print(f"  SKIP {icid}: stage {r.get('Stage_IC__c')} != completed"); continue
    if mode=="link":
        cand=[a for a in existing.get(opp_id,[]) if a["Agreement_Type__c"]=="ROE" and not a.get("IronClad_Record__c")]
        if not cand: print(f"  SKIP {icid}: no unlinked ROE on {opps[opp_id]['Name']}"); continue
        plan.append({"ic":icid,"mode":"link","opp":opp_id,"agr":cand[0]["Id"],"agr_name":cand[0]["Name"],
                     "ic_sfid":r["Id"],"signed":signed,"exp":r.get("Expiration_Date__c")})
    else:
        if any(a["Agreement_Type__c"]=="ROE" for a in existing.get(opp_id,[])):
            print(f"  SKIP {icid}: Opp {opps[opp_id]['Name']} already has a ROE (dup guard)"); continue
        plan.append({"ic":icid,"mode":"create","opp":opp_id,"ic_sfid":r["Id"],
                     "signed":signed,"exp":r.get("Expiration_Date__c")})

print(f"\nPlan ({len(plan)}):")
for p in plan:
    tgt=f"link {p['agr_name']}" if p["mode"]=="link" else "create ROE"
    print(f"  {p['ic']:<8} {p['mode']:<6} -> {opps[p['opp']]['Name'][:38]:<38} [{opps[p['opp']]['StageName']}] signed={p['signed']} ({tgt})")

ts=datetime.now().strftime("%Y%m%d-%H%M%S"); audit=LOG/f"completed_mdu_vetro_{ts}.csv"
def wa(rows):
    with open(audit,"w",newline="",encoding="utf-8") as fh:
        w=csv.writer(fh); w.writerow(["Action","IC","Mode","Opp","Opp_Name","Agreement_Id","Signed","Timestamp"])
        for row in rows: w.writerow(row)
if not APPLY:
    wa([["PREVIEW",p["ic"],p["mode"],p["opp"],opps[p["opp"]]["Name"],p.get("agr",""),p["signed"],datetime.now().isoformat()] for p in plan])
    print(f"\nAudit: {audit}\nPREVIEW only. --apply to write."); sys.exit(0)

rows=[]; ok=fail=0
for p in plan:
    try:
        if p["mode"]=="link":
            body={"IronClad_Record__c":p["ic_sfid"],"IronClad_ID__c":p["ic"],"Status__c":"Completed"}
            if p["signed"]: body["Signed_Date__c"]=p["signed"]
            if p["exp"]: body["Expiration_Date__c"]=p["exp"]
            sf.Agreement__c.update(p["agr"],body); aid=p["agr"]
        else:
            body={"Opportunity__c":p["opp"],"Agreement_Type__c":"ROE","Status__c":"Completed",
                  "Signed_Date__c":p["signed"],"IronClad_ID__c":p["ic"],"IronClad_Record__c":p["ic_sfid"]}
            if p["exp"]: body["Expiration_Date__c"]=p["exp"]
            aid=sf.Agreement__c.create(body)["id"]
        ok+=1; rows.append([p["mode"].upper(),p["ic"],p["mode"],p["opp"],opps[p["opp"]]["Name"],aid,p["signed"],datetime.now().isoformat()])
        print(f"  ok {p['ic']} {p['mode']} -> {aid}")
    except Exception as e:
        fail+=1; rows.append(["ERROR",p["ic"],p["mode"],p["opp"],opps[p["opp"]]["Name"],"",p["signed"],str(e)[:200]])
        print(f"  ! {p['ic']}: {e}")
wa(rows); print(f"\nDone: ok={ok} fail={fail}\nAudit: {audit}")
