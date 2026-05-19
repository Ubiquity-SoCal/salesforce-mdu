"""Read-only probe: assess match coverage for mapping MDU Categorization
from 'Signed MDU Agreement Analysis V1.xlsx' (sheet 'Signed MDUs') into SF.

Checks how the source rows match against:
  - SiteTracker_Project__c (by Name == source Site Name, by Monday_Name__c == source Monday name)
  - Opportunity (by Agreement_Name__c / Name == source Monday name, and via ST link)
Also reports whether an MDU Categorization field already exists on either object.
No writes.
"""
import sys
from pathlib import Path
import openpyxl
from simple_salesforce import Salesforce

sys.stdout.reconfigure(line_buffering=True)

SRC = r"C:\Users\cass\Downloads\Signed MDU Agreement Analysis V1.xlsx"

print("[INFO] Loading source rows...")
wb = openpyxl.load_workbook(SRC, data_only=True)
ws = wb["Signed MDUs"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
rows = [r for r in rows if any(v is not None for v in r)]
# col idx: 0 ProjectID, 3 SiteName, 8 MDUCat, 13 MondayName
src = []
for r in rows:
    src.append({
        "project_id": (r[0] or "").strip() if r[0] else "",
        "site_name": (r[3] or "").strip() if r[3] else "",
        "mdu_cat": (r[8] or "").strip() if r[8] else "",
        "monday_name": (r[13] or "").strip() if r[13] else "",
    })
print(f"[INFO] {len(src)} source rows")

print("[INFO] Connecting to Salesforce...")
def load_creds():
    creds = {}
    p = Path(__file__).resolve().parents[2] / "api" / "Salesforce_Credentials.txt"
    for line in p.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            creds[k.strip().lower()] = v.strip()
    return creds
_c = load_creds()
sf = Salesforce(
    username=_c['username'],
    password=_c['password'],
    security_token=_c['security token']
)

# --- Existing field check ---
def field_names(obj):
    desc = getattr(sf, obj).describe()
    return {f['name']: f['type'] for f in desc['fields']}

opp_fields = field_names('Opportunity')
st_fields = field_names('SiteTracker_Project__c')
print("\n[FIELD CHECK] Opportunity fields matching categor/mdu/net:")
for n, t in opp_fields.items():
    if any(k in n.lower() for k in ['categor', 'onnet', 'offnet', 'nearnet', 'mdu_cat']):
        print(f"   {n} ({t})")
print("[FIELD CHECK] SiteTracker_Project__c fields matching categor/mdu/net:")
for n, t in st_fields.items():
    if any(k in n.lower() for k in ['categor', 'onnet', 'offnet', 'nearnet', 'mdu_cat']):
        print(f"   {n} ({t})")

# --- Pull SiteTracker projects ---
print("\n[INFO] Pulling SiteTracker projects...")
st = sf.query_all("SELECT Id, Name, Monday_Name__c, Opportunity__c, Opportunity__r.Name, Opportunity__r.Agreement_Name__c FROM SiteTracker_Project__c")
st_recs = st['records']
print(f"[INFO] {len(st_recs)} SiteTracker projects")
st_by_name = {}
st_by_monday = {}
for s in st_recs:
    if s.get('Name'):
        st_by_name[s['Name'].strip().lower()] = s
    if s.get('Monday_Name__c'):
        st_by_monday[s['Monday_Name__c'].strip().lower()] = s

# --- Pull Opportunities ---
print("[INFO] Pulling Opportunities...")
opps = sf.query_all("SELECT Id, Name, Agreement_Name__c FROM Opportunity")
opp_recs = opps['records']
print(f"[INFO] {len(opp_recs)} Opportunities")
opp_by_agr = {}
opp_by_name = {}
for o in opp_recs:
    if o.get('Agreement_Name__c'):
        opp_by_agr[o['Agreement_Name__c'].strip().lower()] = o
    if o.get('Name'):
        opp_by_name[o['Name'].strip().lower()] = o

# --- Match analysis ---
st_hit_name = st_hit_monday = 0
opp_hit_via_st = opp_hit_agr = opp_hit_name = 0
opp_resolved = 0
st_resolved = 0
unmatched_st = []
unmatched_opp = []

for row in src:
    sn = row['site_name'].lower()
    mn = row['monday_name'].lower()
    # SiteTracker match
    st_match = st_by_name.get(sn) or st_by_monday.get(mn)
    if st_by_name.get(sn):
        st_hit_name += 1
    elif st_by_monday.get(mn):
        st_hit_monday += 1
    if st_match:
        st_resolved += 1
    else:
        unmatched_st.append(row)
    # Opportunity match: via ST link first, then direct
    opp_id = None
    if st_match and st_match.get('Opportunity__c'):
        opp_id = st_match['Opportunity__c']
        opp_hit_via_st += 1
    elif opp_by_agr.get(mn):
        opp_id = opp_by_agr[mn]['Id']
        opp_hit_agr += 1
    elif opp_by_name.get(mn):
        opp_id = opp_by_name[mn]['Id']
        opp_hit_name += 1
    if opp_id:
        opp_resolved += 1
    else:
        unmatched_opp.append(row)

print("\n========== MATCH SUMMARY ==========")
print(f"Source rows: {len(src)}")
print(f"\nSiteTracker resolved: {st_resolved}/{len(src)}")
print(f"   via Site Name:   {st_hit_name}")
print(f"   via Monday name: {st_hit_monday}")
print(f"\nOpportunity resolved: {opp_resolved}/{len(src)}")
print(f"   via ST link:        {opp_hit_via_st}")
print(f"   via Agreement_Name: {opp_hit_agr}")
print(f"   via Opp Name:       {opp_hit_name}")

print(f"\nUnmatched to SiteTracker: {len(unmatched_st)}")
for r in unmatched_st[:30]:
    print(f"   {r['project_id']:>10} | {r['site_name']} | monday={r['monday_name']!r}")
print(f"\nUnmatched to Opportunity: {len(unmatched_opp)}")
for r in unmatched_opp[:40]:
    print(f"   {r['project_id']:>10} | {r['site_name']} | monday={r['monday_name']!r} | cat={r['mdu_cat']}")
