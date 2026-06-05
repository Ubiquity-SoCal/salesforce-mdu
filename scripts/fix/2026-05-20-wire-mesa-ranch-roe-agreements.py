"""
Wire up Tanya's 3 Mesa Ranch ROE agreements (created 2026-05-20) so they are
sync-managed and will auto-populate the SMB Secured list once IronClad marks the
shared ROE (IC-2952) Complete.

Context:
- 1116 S Stapley (AGR-1572), 1134 S Stapley (AGR-1571), 1142 E Southern (AGR-1573)
  are all covered by ONE ROE: IC-2952 (Mesa Ranch 24 LP), currently at stage 'sign'.
- Tanya typed IC-2952 as TEXT only (IronClad_ID__c) with the lookup (IronClad_Record__c)
  empty and Status blank. The refresh sync only touches agreements with the lookup set,
  so as-is these would never sync.

This script (preview by default, --apply to write):
  1. Sets IronClad_Record__c -> IC-2952 record on all 3  (makes them sync-managed)
  2. Sets Status__c='Sign' + Signed_Date__c=2026-03-19 (current IronClad truth; harmless,
     stays off the Secured list until IC-2952 reaches 'completed', then sync flips to Completed)
  3. Adds the 1142 E Southern Opp to the SMB campaign (it had none; needed so it shows
     alongside the two Stapley Opps when secured)

Rollback snapshot + audit -> SalesForce/data/output/audit_logs/
"""
import sys
import csv
import json
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Hawaiian1984"
SECURITY_TOKEN = "IBSKT6CFUpSUJWxq1CMm0HkFC"
LOG_DIR = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv

SMB_CAMPAIGN = "701WR00001Fot1rYAB"      # ROE - 8+ SMB Project
IC_TEXT = "IC-2952"
SIGNED_DATE = "2026-03-19"               # IC-2952 executed date
AGR_NAMES = ["AGR-1571", "AGR-1572", "AGR-1573"]
OPP_1142 = "006WR000015bWdRYAU"          # 1142 E Southern Ave (no campaign)

sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)

# IC-2952 record id
icr = sf.query(f"SELECT Id, IronClad_Id__c, Stage_IC__c FROM IronClad__c WHERE IronClad_Id__c='{IC_TEXT}'")["records"]
if not icr:
    print(f"FATAL: {IC_TEXT} not found in IronClad__c. Import the latest export first.")
    sys.exit(1)
ic_id = icr[0]["Id"]
print(f"{IC_TEXT} -> IronClad__c {ic_id} (stage={icr[0].get('Stage_IC__c')})")

# Current agreement + opp state (snapshot)
ags = sf.query(
    "SELECT Id, Name, Status__c, Signed_Date__c, IronClad_ID__c, IronClad_Record__c, "
    "Opportunity__r.Name FROM Agreement__c WHERE Name IN ('%s')" % "','".join(AGR_NAMES)
)["records"]
opp = sf.query(f"SELECT Id, Name, CampaignId FROM Opportunity WHERE Id='{OPP_1142}'")["records"][0]

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
snap = LOG_DIR / f"2026-05-20-mesa-ranch-wire-snapshot-{ts}.json"
snap.write_text(json.dumps({"agreements": ags, "opp_1142": opp}, indent=2, default=str), encoding="utf-8")
print(f"Snapshot: {snap}")

print("\n=== PLANNED CHANGES ===")
agr_updates = []
for a in ags:
    body = {}
    if a.get("IronClad_Record__c") != ic_id:
        body["IronClad_Record__c"] = ic_id
    if a.get("Status__c") != "Sign":
        body["Status__c"] = "Sign"
    if a.get("Signed_Date__c") != SIGNED_DATE:
        body["Signed_Date__c"] = SIGNED_DATE
    agr_updates.append((a, body))
    print(f"  {a['Name']} ({(a.get('Opportunity__r') or {}).get('Name')})")
    print(f"     lookup: {a.get('IronClad_Record__c')} -> {ic_id}")
    print(f"     status: {a.get('Status__c')} -> Sign   signed: {a.get('Signed_Date__c')} -> {SIGNED_DATE}")

opp_body = {}
if opp.get("CampaignId") != SMB_CAMPAIGN:
    opp_body["CampaignId"] = SMB_CAMPAIGN
print(f"\n  Opp {opp['Name']} CampaignId: {opp.get('CampaignId')} -> {SMB_CAMPAIGN}"
      if opp_body else f"\n  Opp {opp['Name']} already on SMB campaign")

# Audit
audit = LOG_DIR / f"2026-05-20-mesa-ranch-wire-{ts}.csv"
with open(audit, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Action", "Timestamp"])
    action = "UPDATE" if APPLY else "PREVIEW"
    now = datetime.now().isoformat()
    src = "2026-05-20-wire-mesa-ranch-roe-agreements.py"
    for a, body in agr_updates:
        for fld, after in body.items():
            w.writerow([a["Id"], a["Name"], fld, a.get(fld), after, src, action, now])
    for fld, after in opp_body.items():
        w.writerow([opp["Id"], opp["Name"], fld, opp.get(fld), after, src, action, now])
print(f"Audit: {audit}")

if not APPLY:
    print("\nPREVIEW only. Re-run with --apply to write.")
    sys.exit(0)

ok = fail = 0
for a, body in agr_updates:
    if not body:
        continue
    try:
        sf.Agreement__c.update(a["Id"], body)
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  ! {a['Name']}: {e}")
if opp_body:
    try:
        sf.Opportunity.update(opp["Id"], opp_body)
        ok += 1
    except Exception as e:
        fail += 1
        print(f"  ! {opp['Name']}: {e}")
print(f"\nApplied: ok={ok} fail={fail}")
