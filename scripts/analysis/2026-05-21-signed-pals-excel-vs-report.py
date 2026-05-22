"""
Compare the requester's 'Signed PALs 4.23.26.xlsx' against the new SF report.
Checks: column coverage, population overlap (matched by normalized name/address),
and value fidelity on PAL Signed Date / Category / State for matched rows.
"""
import re, requests
from datetime import datetime
import openpyxl
from simple_salesforce import Salesforce

XLSX = r"C:\Users\cass\OneDrive - Ubiquity Management\Desktop\Signed PALs 4.23.26.xlsx"
sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
hdr = {'Authorization': f'Bearer {sf.session_id}'}


def norm(s):
    if s is None: return ""
    return re.sub(r'[^a-z0-9]', '', str(s).lower())

def to_date(v):
    if v is None or v == "": return None
    if isinstance(v, datetime): return v.date().isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(s, fmt).date().isoformat()
        except: pass
    return s

# ---- load Excel ----
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
xl_rows = []
for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    for r in rows[2:]:  # row0 title, row1 header
        if r and r[0]:
            xl_rows.append({"sheet": ws.title, "name": r[0], "status_proj": r[1], "units": r[2],
                            "address": r[3], "category": r[4], "type": r[5], "build": r[6],
                            "lead": r[7], "prosp": r[8], "conf": r[9], "state": r[10],
                            "pal_date": to_date(r[11]), "activation": r[12], "status": r[13]})
xl_by_name = {}
for x in xl_rows:
    xl_by_name.setdefault(norm(x["name"]), x)
print(f"Excel rows: {len(xl_rows)}  (Core+National)  | unique names: {len(xl_by_name)}")
for ws in wb.worksheets:
    n = sum(1 for x in xl_rows if x['sheet']==ws.title)
    print(f"   sheet {ws.title}: {n} rows")

# ---- pull SF report ----
rid = sf.query("SELECT Id FROM Report WHERE DeveloperName='Signed_PALs'")['records'][0]['Id']
res = requests.get(sf.base_url + f"analytics/reports/{rid}?includeDetails=true", headers=hdr).json()
cols = [res['reportExtendedMetadata']['detailColumnInfo'][c]['label'] for c in res['reportMetadata']['detailColumns']]
sf_rows = []
for row in res['factMap']['T!T']['rows']:
    cells = [c.get('label','') for c in row['dataCells']]
    d = dict(zip(cols, cells))
    sf_rows.append(d)
sf_by_name = {}
for s in sf_rows:
    sf_by_name.setdefault(norm(s['Opportunity Name']), s)
print(f"\nSF report rows: {len(sf_rows)} | unique names: {len(sf_by_name)}")

# ---- column coverage ----
xl_cols = ["Name","Overall Project Status","Units","Address","Category","MDU/SFU/MHP","Build Type",
           "ISP/SAQ/Ubiquity Lead","Prospective ISP(s)","Confirmed ISP(s)","State","PAL Signed Date",
           "Activation Date","Status"]
mapping = {
 "Name":"Opportunity Name","Overall Project Status":"Stage","Units":"Living Units","Address":"Property Address",
 "Category":"Category","MDU/SFU/MHP":"MISSING (deferred -> Record Type)","Build Type":"Build Type",
 "ISP/SAQ/Ubiquity Lead":"MISSING (no SF field)","Prospective ISP(s)":"Prospective ISP","Confirmed ISP(s)":"Confirmed ISP",
 "State":"Property State","PAL Signed Date":"Signed Date","Activation Date":"MISSING (needs ST surfacing)","Status":"Stage Status"}
print("\n=== COLUMN COVERAGE ===")
for c in xl_cols:
    print(f"   {c:<24} -> {mapping[c]}")

# ---- population overlap ----
xn, sn = set(xl_by_name), set(sf_by_name)
both = xn & sn
only_xl = xn - sn
only_sf = sn - xn
print(f"\n=== POPULATION OVERLAP (by normalized name) ===")
print(f"   in BOTH: {len(both)}")
print(f"   only in HER Excel (not in SF report): {len(only_xl)}")
print(f"   only in SF report (extra): {len(only_sf)}")

print(f"\n   Sample of HER rows NOT matched in SF report ({min(15,len(only_xl))} of {len(only_xl)}):")
for k in list(only_xl)[:15]:
    print(f"      - {xl_by_name[k]['name']}  ({xl_by_name[k]['state']}, PAL {xl_by_name[k]['pal_date']})")

# ---- value fidelity on matched ----
date_match = date_mismatch = 0
mismatches = []
for k in both:
    xd, sd = xl_by_name[k]['pal_date'], to_date(sf_by_name[k]['Signed Date'])
    if xd and sd:
        if xd == sd: date_match += 1
        else:
            date_mismatch += 1
            if len(mismatches) < 12: mismatches.append((xl_by_name[k]['name'], xd, sd))
print(f"\n=== PAL SIGNED DATE fidelity (matched rows) ===")
print(f"   same date: {date_match}   different: {date_mismatch}")
for n, xd, sd in mismatches:
    print(f"      {n[:34]:<34} excel={xd}  sf={sd}")
