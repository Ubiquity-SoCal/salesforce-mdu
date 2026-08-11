"""Discover the report-type token for Opportunities+Agreements and list report folders,
so the Signed PALs report metadata deploy lands correctly."""
import requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USER=_SF["username"]; PW=_SF["password"]; TOK=_SF["token"]
sf = Salesforce(username=USER, password=PW, security_token=TOK)
base = sf.base_url  # .../services/data/vXX.X/
hdr = {"Authorization": f"Bearer {sf.session_id}"}

print("=== Report folders (Folder where Type=Report) ===")
for r in sf.query("SELECT Id, Name, DeveloperName FROM Folder WHERE Type='Report' ORDER BY Name")["records"]:
    print(f"   {str(r['DeveloperName']):<40} | {r['Name']}")

resp = requests.get(base + "analytics/reportTypes", headers=hdr)
data = resp.json() if resp.status_code == 200 else []
allrt = [(rt.get("type") or "", rt.get("label") or "", cat.get("label"))
         for cat in data for rt in cat.get("reportTypes", [])]
print(f"\n=== total report types: {len(allrt)} ===")

print("\n--- any token referencing Agreement__c (the real object) ---")
hit = [x for x in allrt if "Agreement__c" in x[0]]
for t, l, c in hit:
    print(f"   {t!r:<55} {l!r}")
if not hit:
    print("   NONE -> Agreement__c is not reportable (Allow Reports likely OFF) and/or no custom report type exists")

print("\n--- Opportunity-primary report types (label or token) ---")
for t, l, c in allrt:
    if t.startswith("Opportunity") or "opportunit" in l.lower():
        print(f"   {t!r:<55} {l!r}")

print("\n--- any token referencing SiteTracker_Project__c ---")
for t, l, c in allrt:
    if "SiteTracker_Project__c" in t:
        print(f"   {t!r:<55} {l!r}")
