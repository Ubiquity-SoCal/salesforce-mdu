"""
Re-audit ALL uncovered ROE/PAL gaps through Vetro's agreename (the cross-system key =
SF Opportunity.Agreement_Name__c) instead of fuzzy street/name matching.

Why: an IronClad ROE and its SF Opp can sit at DIFFERENT building addresses of the same
complex (e.g. Vance: ROE at 900 Vance St, Opp at 205 W 9th St). Street matching misses
those; Vetro's agreename unifies every building of a complex, so it finds the real Opp.

Flow:
  1. SF  -> uncovered IronClad ROE/PAL (not linked to any Agreement__c), with addresses.
  2. Vetro (Databricks) -> mdu/sfu address book: (housenum, street, state) -> agreename.
  3. Join gap address -> Vetro agreename.
  4. SF  -> Opp WHERE Agreement_Name__c = agreename.
  Result: gaps that actually HAVE an Opp (link, not create) vs genuinely new.

Read-only. Writes CSV to data/output.
"""
import re, csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from databricks import sql
from simple_salesforce import Salesforce

DBX_SERVER = 'adb-1444374860642533.13.azuredatabricks.net'
DBX_HTTP_PATH = '/sql/1.0/warehouses/9116e9c573d36d1c'
OUT = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output"); OUT.mkdir(parents=True, exist_ok=True)
sf = Salesforce(username="cass1@ubiquitygp.com", password="Hawaiian1984", security_token="IBSKT6CFUpSUJWxq1CMm0HkFC")

ROE_PAL = ('Right of Entry Agreement', 'Premises Access License')

# --- 1. covered set + uncovered ROE/PAL gaps ---
covered = set()
for a in sf.query_all("SELECT IronClad_ID__c, IronClad_Record__r.IronClad_Id__c FROM Agreement__c")["records"]:
    if a.get("IronClad_ID__c"): covered.add(str(a["IronClad_ID__c"]).strip())
    lk = (a.get("IronClad_Record__r") or {}).get("IronClad_Id__c")
    if lk: covered.add(str(lk).strip())

rt_in = "','".join(ROE_PAL)
gaps = [g for g in sf.query_all(
    f"SELECT IronClad_Id__c, Record_Type_IC__c, Stage_IC__c, MDU_or_BUS__c, Property_Address__c, "
    f"Property_City__c, Property_State__c, Counterparty_Name__c, Agreement_Date__c "
    f"FROM IronClad__c WHERE Record_Type_IC__c IN ('{rt_in}') AND Stage_IC__c NOT IN ('cancelled')")["records"]
    if g["IronClad_Id__c"] not in covered]
print(f"Uncovered ROE/PAL gaps (non-cancelled): {len(gaps)}")

def parse(addr):
    line = (str(addr or "").split(",")[0].splitlines() or [""])[0].lower()
    m = re.match(r"\s*(\d+)", line); n = m.group(1) if m else None
    line = re.sub(r"[.,]", " ", line)
    line = re.sub(r"\b(n|s|e|w|north|south|east|west|st|street|ave|avenue|rd|road|blvd|dr|drive|"
                  r"ln|lane|way|cir|circle|hwy|highway|us|unit|apt|pkwy|ste|suite)\b", " ", line)
    return n, {t for t in re.findall(r"[a-z0-9]+", line) if t != n and len(t) >= 2}

def st2(s):
    s = str(s or "").strip().upper()
    return {"NEBRASKA": "NE", "TEXAS": "TX", "ARIZONA": "AZ", "CALIFORNIA": "CA"}.get(s, s[:2])

# --- 2. Vetro mdu/sfu address book ---
print("Pulling Vetro mdu/sfu address book...")
with sql.connect(server_hostname=DBX_SERVER, http_path=DBX_HTTP_PATH, auth_type='databricks-oauth') as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT `properties.housenum` hn, `properties.streetname` sn,
                   upper(trim(`properties.state`)) st, `properties.addtype` addtype,
                   `properties.agreename` agreename
            FROM hive_metastore.default.vetro_external_table
            WHERE `properties.addtype` IN ('mdu','sfu')
              AND `properties.agreename` IS NOT NULL
              AND lower(trim(`properties.agreename`)) NOT IN ('nan','null','none','','0','mdu','sfu','bus','mtu')
        """)
        cols = [d[0] for d in cur.description]
        vrows = [dict(zip(cols, r)) for r in cur.fetchall()]
print(f"  Vetro mdu/sfu address rows: {len(vrows)}")

# index Vetro by (housenum, state) -> list of (streettokens, agreename, addtype)
vidx = defaultdict(list)
for v in vrows:
    n, toks = parse(str(v["hn"]) + " " + str(v["sn"]))
    vidx[(str(v["hn"]).strip(), v["st"])].append((toks, str(v["agreename"]).strip(), str(v["addtype"])))

def vetro_agreename(g):
    n, gt = parse(g.get("Property_Address__c")); st = st2(g.get("Property_State__c"))
    for toks, agn, addtype in vidx.get((n, st), []):
        if gt & toks:
            return agn, addtype
    return None, None

# --- 3+4. match to agreename, then Opp ---
for g in gaps:
    g["_agn"], g["_addtype"] = vetro_agreename(g)
agrenames = sorted({g["_agn"] for g in gaps if g["_agn"]})
opp_by_agn = defaultdict(list)
if agrenames:
    for i in range(0, len(agrenames), 200):
        chunk = agrenames[i:i+200]
        inlist = "','".join(a.replace("'", "\\'") for a in chunk)
        for o in sf.query_all(f"SELECT Id, Name, Agreement_Name__c, StageName FROM Opportunity "
                              f"WHERE Agreement_Name__c IN ('{inlist}')")["records"]:
            opp_by_agn[str(o.get("Agreement_Name__c") or "").strip()].append(o)

# --- classify ---
has_opp, new_via_vetro, no_vetro = [], [], []
for g in gaps:
    if g["_agn"] and opp_by_agn.get(g["_agn"]):
        g["_opp"] = opp_by_agn[g["_agn"]][0]; has_opp.append(g)
    elif g["_agn"]:
        new_via_vetro.append(g)          # Vetro knows it (agreename) but no Opp yet
    else:
        no_vetro.append(g)               # not found in Vetro mdu/sfu (BUS/SFU-no-agn/unbuilt)

print("\n" + "=" * 66)
print(f"HAS an existing Opp via Vetro agreename (LINK, not new): {len(has_opp)}")
print(f"Vetro agreename known but no Opp yet (truly new MDU/SFU): {len(new_via_vetro)}")
print(f"No Vetro mdu/sfu agreename match (BUS / unbuilt / other): {len(no_vetro)}")
print("=" * 66)

print("\n--- Gaps that ACTUALLY have an Opp (address matching would have called these NEW) ---")
for g in sorted(has_opp, key=lambda x: x["_agn"]):
    print(f"  {g['IronClad_Id__c']:<8} {str(g['Stage_IC__c'] or ''):<10} {str(g.get('Property_Address__c') or '').splitlines()[0][:26]:<26} "
          f"-> {g['_opp']['Name'][:34]} [{g['_opp']['StageName']}]")

ts = datetime.now().strftime("%Y%m%d-%H%M%S")
path = OUT / f"vetro_agreename_gap_reaudit_{ts}.csv"
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["IC", "Class", "Stage", "MDU_BUS", "Vetro_addtype", "Vetro_agreename",
                "Existing_Opp", "Opp_Stage", "Opp_Id", "Address", "City", "State", "Counterparty"])
    def cls(g): return "HAS_OPP" if g in has_opp else ("NEW_MDU_SFU" if g in new_via_vetro else "NO_VETRO_MATCH")
    for g in gaps:
        o = g.get("_opp") or {}
        w.writerow([g["IronClad_Id__c"], cls(g), g["Stage_IC__c"], g.get("MDU_or_BUS__c"),
                    g.get("_addtype"), g.get("_agn"), o.get("Name", ""), o.get("StageName", ""),
                    o.get("Id", ""), (str(g.get("Property_Address__c") or "").splitlines() or [""])[0],
                    g.get("Property_City__c"), g.get("Property_State__c"), g.get("Counterparty_Name__c")])
print(f"\nCSV: {path}")
