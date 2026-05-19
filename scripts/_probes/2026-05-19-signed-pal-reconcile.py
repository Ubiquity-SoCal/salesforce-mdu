"""Read-only reconciliation: do the 313 Opps we just stamped with MDU Categorization
actually reflect 'signed PAL' status in SF?

Joins the latest mapping preview (opp_id <-> site_name) to the source workbook
(PAL Status, PAL date, Project Status) and to SF (Opp StageName + Agreement__c PALs).
No writes.
"""
import csv
import glob
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from simple_salesforce import Salesforce

ROOT = Path(__file__).resolve().parents[2]
SRC = r"C:\Users\cass\Downloads\Signed MDU Agreement Analysis V1.xlsx"

# --- source: site_name -> pal info ---
wb = openpyxl.load_workbook(SRC, data_only=True)
ws = wb["Signed MDUs"]
src = {}
for r in ws.iter_rows(min_row=2, values_only=True):
    if not any(v is not None for v in r):
        continue
    sn = (str(r[3]).strip() if r[3] else "")
    src[sn] = {
        "proj_status": (str(r[7]).strip() if r[7] else ""),
        "pal_status": (str(r[9]).strip() if r[9] else ""),
        "pal_date": r[17],
        "roe_date": r[18],
    }

# --- preview: opp_id -> site_name ---
pf = sorted(glob.glob(str(ROOT / "data/output/mdu_categorization_preview_*.csv")))[-1]
opp_site = {}
for row in csv.DictReader(open(pf, encoding="utf-8")):
    if row["opp_id"]:
        opp_site[row["opp_id"]] = row["site_name"]
opp_ids = list(opp_site)
print(f"[INFO] {len(opp_ids)} unique Opps from preview {Path(pf).name}")

# --- SF ---
c = {}
for line in (ROOT / "api/Salesforce_Credentials.txt").read_text().splitlines():
    if ":" in line:
        k, v = line.split(":", 1)
        c[k.strip().lower()] = v.strip()
sf = Salesforce(username=c["username"], password=c["password"], security_token=c["security token"])


def chunks(lst, n=200):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# Opp stages
stage = {}
for ch in chunks(opp_ids):
    ids = "','".join(ch)
    for r in sf.query_all(f"SELECT Id, StageName FROM Opportunity WHERE Id IN ('{ids}')")["records"]:
        stage[r["Id"]] = r["StageName"]

# Agreements for these opps
pal_by_opp = defaultdict(list)   # opp_id -> list of (status, signed_date)
any_agr = set()
for ch in chunks(opp_ids):
    ids = "','".join(ch)
    q = ("SELECT Opportunity__c, Agreement_Type__c, Status__c, Signed_Date__c, Is_Signed_Status__c "
         f"FROM Agreement__c WHERE Opportunity__c IN ('{ids}')")
    for r in sf.query_all(q)["records"]:
        oid = r["Opportunity__c"]
        any_agr.add(oid)
        if r["Agreement_Type__c"] == "PAL":
            pal_by_opp[oid].append((r["Status__c"], r["Signed_Date__c"], r["Is_Signed_Status__c"]))

# --- analysis ---
print("\n=== Opp StageName distribution (313 mapped) ===")
for k, v in Counter(stage.get(o, "(missing)") for o in opp_ids).most_common():
    print(f"   {k}: {v}")

has_pal = sum(1 for o in opp_ids if pal_by_opp.get(o))
signed_pal = 0
for o in opp_ids:
    pals = pal_by_opp.get(o, [])
    if any(st == "Completed" or sd or sig for st, sd, sig in pals):
        signed_pal += 1
print("\n=== PAL agreement coverage (SF side) ===")
print(f"   Opps with >=1 Agreement of any type: {len(any_agr)}/{len(opp_ids)}")
print(f"   Opps with >=1 PAL agreement:         {has_pal}/{len(opp_ids)}")
print(f"   Opps with a SIGNED/Completed PAL:    {signed_pal}/{len(opp_ids)}")

# Cross-ref: source PAL date present vs SF signed PAL
src_pal = {o for o in opp_ids if (src.get(opp_site.get(o, ""), {}).get("pal_date"))}
sf_signed = {o for o in opp_ids
             if any(st == "Completed" or sd or sig for st, sd, sig in pal_by_opp.get(o, []))}
print("\n=== Source PAL date  vs  SF signed PAL ===")
print(f"   Source has PAL date:                 {len(src_pal)}")
print(f"   ...and SF has a signed PAL:          {len(src_pal & sf_signed)}")
print(f"   Source PAL date but NO signed PAL SF:{len(src_pal - sf_signed)}")
print(f"   SF signed PAL but NO source PAL date:{len(sf_signed - src_pal)}")

# Early-stage Opps that the source says have a PAL (potential data lag)
early = {"Prospects", "Prospecting", "Engaged", "On Hold", "Closed Lost"}
lag = [o for o in src_pal if stage.get(o) in early]
print(f"\n=== Source-signed-PAL Opps still at an early/hold/lost SF stage: {len(lag)} ===")
for o in lag[:40]:
    s = src.get(opp_site.get(o, ""), {})
    print(f"   {opp_site.get(o,'?')[:48]:48} | SF stage={stage.get(o):22} | src PAL status={s.get('pal_status','')!r}")
