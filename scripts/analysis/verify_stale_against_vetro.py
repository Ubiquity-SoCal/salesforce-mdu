"""
Re-run the rewrite's stale-flagging logic, then for each stale Unit/PL look up
the actual current state in Vetro raw (no filters). Categorise:

  A. Truly gone        : ckta_id absent from Vetro entirely
  B. Status changed    : present but addrstatus != 'serviceable'
  C. FDH deactivated   : present + serviceable but projectid resolves to
                         a SiteTracker project with NULL fdh_activation_a_c
                         (or projectid null)
  D. Should be in pull : present + serviceable + FDH-active. Our flagging
                         logic / inclusion rules dropped it -- a bug to chase.

Output a category breakdown plus samples per category.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import Counter, defaultdict
from databricks import sql
from simple_salesforce import Salesforce

HOST = "adb-1444374860642533.13.azuredatabricks.net"
PATH = "/sql/1.0/warehouses/9116e9c573d36d1c"
STATES = ('TX','NE','AZ','CA')

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984',
                security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

def clean(v):
    if v is None: return ''
    s = str(v).strip()
    return '' if s.lower() in ('nan','null','none','') else s
def upper(v): return clean(v).upper()
def derive_bba(hn, pre, sn, suf, post, c, s):
    parts = [upper(x) for x in (hn, pre, sn, post, suf, c, s)]
    parts = [p for p in parts if p]
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()

# ───────── 1. Re-derive what the rewrite would consider non-stale ─────────
print("[1/4] Re-deriving target set from Vetro+SiteTracker (same logic as rewrite)...")
state_clause = "','".join(STATES)
DB_QUERY = f"""
WITH vetro AS (
  SELECT
    `properties.ckta_id`     AS circuit_id,
    `properties.housenum`    AS housenum, `properties.predirect` AS predirect,
    `properties.streetname`  AS streetname, `properties.streetsuff` AS streetsuff,
    `properties.postdirect`  AS postdirect, `properties.city` AS city,
    `properties.state`       AS state, `properties.addtype` AS addtype,
    `properties.agreename`   AS agreename, `properties.projectid` AS projectid
  FROM hive_metastore.default.vetro_external_table
  WHERE `properties.addrstatus` = 'serviceable'
    AND trim(`properties.state`) IN ('{state_clause}')
    AND `properties.ckta_id` IS NOT NULL
    AND (
      `properties.addtype` IN ('bus', 'mdu', 'mtu')
      OR (`properties.addtype` = 'sfu'
          AND lower(trim(coalesce(`properties.agreename`, ''))) NOT IN ('', 'nan', 'null', 'none'))
    )
),
proj_act AS (
  SELECT p.name AS proj_name, MAX(lf.fdh_activation_a_c) AS act
  FROM salesforce_sitetracker_bronze.sitetracker_project_c p
  LEFT JOIN salesforce_sitetracker_bronze.lit_fiber_c lf
    ON lf.project_c = p.id AND lf.is_deleted = false
  WHERE p.is_deleted = false
  GROUP BY p.name
)
SELECT v.* FROM vetro v
LEFT JOIN proj_act pa ON pa.proj_name = v.projectid
WHERE pa.act IS NOT NULL
"""
target_cids = set()
target_bbas = set()
target_agrees = set()
with sql.connect(server_hostname=HOST, http_path=PATH, auth_type='databricks-oauth') as conn:
    with conn.cursor() as cur:
        cur.execute(DB_QUERY)
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            cid = clean(d.get('circuit_id'))
            if cid: target_cids.add(cid)
            at = clean(d.get('addtype')).lower()
            if at == 'bus':
                bba = derive_bba(d['housenum'], d['predirect'], d['streetname'],
                                 d['streetsuff'], d['postdirect'], d['city'], d['state'])
                if bba: target_bbas.add(bba)
            elif at in ('mdu','sfu','mtu'):
                agree = clean(d.get('agreename'))
                if agree: target_agrees.add(agree)

print(f"  target circuits: {len(target_cids):,}  bus BBAs: {len(target_bbas):,}  agreement names: {len(target_agrees):,}")

# ───────── 2. Pull current SF state ─────────
print("\n[2/4] Pulling SF stale candidates...")
sf_pls = sf.query_all("""
  SELECT Id, Business_Base_Address__c, Agreement_Name__c, State__c, Import_Delete_Property__c
  FROM Property_Location__c
""")['records']
sf_units = sf.query_all("""
  SELECT Id, Circuit_ID__c, Property_Location__r.Business_Base_Address__c, Import_Delete_Unit__c
  FROM Property_Unit__c
""")['records']

# Stale PLs: in SF active, neither BBA nor AgreeName in target sets
stale_pls = []
for p in sf_pls:
    if p.get('Import_Delete_Property__c'): continue
    bba = clean(p.get('Business_Base_Address__c'))
    agree = clean(p.get('Agreement_Name__c'))
    state = upper(p.get('State__c'))
    if state and state not in STATES: continue
    if bba and bba in target_bbas: continue
    if agree and agree in target_agrees: continue
    if not bba and not agree: continue
    stale_pls.append(p)

stale_units = [u for u in sf_units
               if u.get('Circuit_ID__c') and u['Circuit_ID__c'] not in target_cids
               and not u.get('Import_Delete_Unit__c')]
print(f"  stale PLs: {len(stale_pls):,}   stale Units: {len(stale_units):,}")

# ───────── 3. Look up stale Units in Vetro raw (no filters) ─────────
stale_cids = [u['Circuit_ID__c'] for u in stale_units]
print(f"\n[3/4] Looking up {len(stale_cids):,} stale circuits in Vetro RAW (no filters)...")

raw_states = {}    # cid -> dict of (addrstatus, addtype, projectid, has_fdh_act, region, state_v)
if stale_cids:
    # Chunk lookup -- IN list with thousands works on Databricks but easier in chunks
    chunk = 500
    with sql.connect(server_hostname=HOST, http_path=PATH, auth_type='databricks-oauth') as conn:
        with conn.cursor() as cur:
            for i in range(0, len(stale_cids), chunk):
                batch = stale_cids[i:i+chunk]
                quoted = "','".join(c.replace("'", "''") for c in batch)
                cur.execute(f"""
                  WITH v AS (
                    SELECT `properties.ckta_id` AS cid,
                           `properties.addrstatus` AS addrstatus,
                           `properties.addtype`    AS addtype,
                           `properties.projectid`  AS projectid,
                           `properties.region`     AS region,
                           trim(`properties.state`) AS state
                    FROM hive_metastore.default.vetro_external_table
                    WHERE `properties.ckta_id` IN ('{quoted}')
                  ),
                  pa AS (
                    SELECT p.name AS proj_name, MAX(lf.fdh_activation_a_c) AS act
                    FROM salesforce_sitetracker_bronze.sitetracker_project_c p
                    LEFT JOIN salesforce_sitetracker_bronze.lit_fiber_c lf
                      ON lf.project_c = p.id AND lf.is_deleted = false
                    WHERE p.is_deleted = false
                    GROUP BY p.name
                  )
                  SELECT v.cid,
                         FIRST(v.addrstatus) AS addrstatus,
                         FIRST(v.addtype)    AS addtype,
                         FIRST(v.projectid)  AS projectid,
                         FIRST(v.region)     AS region,
                         FIRST(v.state)      AS state,
                         MAX(pa.act IS NOT NULL) AS has_fdh_act
                  FROM v LEFT JOIN pa ON pa.proj_name = v.projectid
                  GROUP BY v.cid
                """)
                for r in cur.fetchall():
                    raw_states[r[0]] = {
                        'addrstatus': r[1], 'addtype': r[2], 'projectid': r[3],
                        'region': r[4], 'state': r[5], 'has_fdh_act': bool(r[6]),
                    }

# ───────── 4. Categorise ─────────
print("\n[4/4] Categorising stale Units...")
cats = Counter()
samples = defaultdict(list)
for u in stale_units:
    cid = u['Circuit_ID__c']
    raw = raw_states.get(cid)
    if not raw:
        cat = 'A_truly_gone'
    elif clean(raw['addrstatus']).lower() != 'serviceable':
        cat = f"B_status_{clean(raw['addrstatus']) or 'null'}"
    elif not raw['has_fdh_act']:
        cat = 'C_fdh_deactivated_or_null'
    else:
        # In Vetro, serviceable, FDH-active -- should be in our pull but isn't
        # Likely sfu without agreename (excluded by inclusion rule)
        cat = 'D_excluded_by_our_rules'
    cats[cat] += 1
    if len(samples[cat]) < 5:
        pl_bba = ((u.get('Property_Location__r') or {}).get('Business_Base_Address__c') or '')[:40]
        samples[cat].append((cid, pl_bba, raw))

print(f"\n=== STALE UNIT CATEGORISATION ({len(stale_units):,} total) ===")
for cat, n in cats.most_common():
    print(f"  {cat:<30} {n:>6,}  ({100*n/max(len(stale_units),1):5.1f}%)")
print(f"\n=== Samples per category ===")
for cat, items in samples.items():
    print(f"\n  {cat}:")
    for cid, pl_bba, raw in items:
        if raw:
            print(f"    {cid:<30} pl={pl_bba:<40} addtype={raw['addtype']!r} addrstatus={raw['addrstatus']!r} fdh={raw['has_fdh_act']}")
        else:
            print(f"    {cid:<30} pl={pl_bba:<40} (not in Vetro at all)")

# ───────── PL stale categorisation (lighter check) ─────────
print(f"\n=== STALE PLs ({len(stale_pls):,}) ===")
print("  These are PLs whose BBA/AgreeName is no longer in our target set.")
print("  Sample:")
for p in stale_pls[:10]:
    label = clean(p.get('Business_Base_Address__c')) or clean(p.get('Agreement_Name__c'))
    print(f"    state={p.get('State__c'):<3} {label[:60]}")
