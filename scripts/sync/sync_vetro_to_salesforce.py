"""
Sync Vetro (Databricks) -> Salesforce Property_Location__c and Property_Unit__c.

All data comes from Databricks bronze (no cross-org SF API):
  - hive_metastore.default.vetro_external_table       Vetro inventory + circuits
  - salesforce_sitetracker_bronze.sitetracker_project_c   Project rollup names
  - salesforce_sitetracker_bronze.sitetracker_site_c       FDH/MDU site names
  - salesforce_sitetracker_bronze.lit_fiber_c              FDH activation dates

Inclusion rules (mirrors PowerBI):
  - addrstatus = 'serviceable'
  - state IN ('TX','NE','AZ','CA')
  - ckta_id IS NOT NULL
  - FDH-active gate: Vetro.properties.projectid -> SiteTracker project name
                     -> lit_fiber_c.fdh_activation_a_c IS NOT NULL
  - addtype:
       'bus'       -> always include
       'mdu','mtu' -> always include
       'sfu'       -> only when properties.agreename has a real value
                      (not null, '', 'nan', 'null', 'none')

Property_Location keying (the "grouping" model):
  - bus      : 1 PL per Business_Base_Address__c (BBA). Existing convention.
  - mdu/sfu/mtu: 1 PL per Agreement_Name__c. Vetro Agreement spans multiple
                 buildings (e.g. RV resorts) -> they collapse into 1 PL with many
                 Property_Unit children. PL.Name = AgreeName. PL.Business_Base_Address__c
                 left blank (no single physical address represents the agreement).

Field bug fixes vs prior version:
  - Market__c sourced from properties.region (not properties.market, which is the state code)
  - FDH_Name__c sourced from SiteTracker site name via projectid join (not composed)
  - FDH_Activated_Date__c via projectid join (not Vetro areaid prefix-match against
    sitetracker_site_c.name with parent walk)
  - BBA derivation puts postdirect BEFORE streetsuff to match PBI + existing SF format
    (e.g. "FORT CROOK N RD" not "FORT CROOK RD N")
  - Diff only includes a field when the new value is non-empty AND differs from
    existing -- never overwrite SF data with null/empty
  - Property_Unit__c.Coho__c populated from ckta_insvc (Cohort Map Legend)

Stale flagging (Import_Delete_*) preserved unchanged.

Usage:
  python sync_vetro_to_salesforce.py             # preview
  python sync_vetro_to_salesforce.py --apply     # writes + audit log
"""
import os, sys, io, re, csv, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from datetime import date, datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict
from databricks import sql
from simple_salesforce import Salesforce

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
ap.add_argument('--states', default='TX,NE,AZ,CA')
args = ap.parse_args()
APPLY = args.apply
STATES = tuple(s.strip().upper() for s in args.states.split(','))

SCRIPT_NAME = 'sync_vetro_to_salesforce.py'
TS = datetime.now().isoformat(timespec='seconds')
NOW_UTC = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
TODAY = datetime.now().date()
STALE_NOTE = f'Not in Vetro (serviceable, FDH-activated) as of {TODAY.month}/{TODAY.day}/{TODAY.year}. Flagged for review.'
AUDIT_DIR = Path(os.environ.get('VETRO_SYNC_AUDIT_DIR',
                                 r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs'))
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

DBX_SERVER = os.environ.get('DATABRICKS_SERVER_HOSTNAME',
                             'adb-1444374860642533.13.azuredatabricks.net')
DBX_HTTP_PATH = os.environ.get('DATABRICKS_HTTP_PATH',
                                '/sql/1.0/warehouses/9116e9c573d36d1c')

# Salesforce credentials - read from env vars; raise clearly if missing.
def _need(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"[ERROR] Missing env var: {name}. See README for setup.")
    return v

sf = Salesforce(
    username=_need('SF_MAIN_USERNAME'),
    password=_need('SF_MAIN_PASSWORD'),
    security_token=_need('SF_MAIN_TOKEN'),
)

AGREEMENT_ADDTYPES = {'mdu', 'sfu'}          # PL keyed by AgreeName
BBA_ADDTYPES       = {'bus'}                 # PL keyed by BBA
# 'mtu' was 1 stray Vetro record, never surfaced by PowerBI -- excluded.

# Vetro addtype -> SF Address_Type__c picklist value
ADDRESS_TYPE_LABEL = {'bus': 'Business', 'mdu': 'MDU', 'sfu': 'SFU'}


# ─────────────────────────────────────────────────────────────────────────────
#  Normalisation
# ─────────────────────────────────────────────────────────────────────────────
def clean(v):
    """Vetro stores literal 'nan' for null fields; this strips them out."""
    if v is None: return ''
    s = str(v).strip()
    return '' if s.lower() in ('nan', 'null', 'none', '') else s

def upper(v): return clean(v).upper()

def derive_bba(housenum, predirect, streetname, streetsuff, postdirect, city, state):
    # Order matches PowerBI + existing SF data: postdirect comes BEFORE streetsuff.
    # E.g. "909 FORT CROOK N RD BELLEVUE NE" not "909 FORT CROOK RD N BELLEVUE NE".
    parts = [upper(housenum), upper(predirect), upper(streetname),
             upper(postdirect), upper(streetsuff), upper(city), upper(state)]
    parts = [p for p in parts if p]
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()

def is_real_agreename(v):
    """Reject Vetro junk agreement names that aren't real agreements:
       - '0' (literal zero)
       - 'BUS', 'MDU', 'SFU', 'MTU' (someone typed addtype as agreement)
       - bare project-area codes like 'PA01', 'PB12' (suffix only, not full name)
    """
    s = clean(v)
    if not s: return False
    u = s.upper()
    if u in {'0', 'BUS', 'MDU', 'SFU', 'MTU', 'TBD', '-', '--', 'TEST'}: return False
    if re.match(r'^P[A-Z]\d+$', u): return False    # PA01, PB12, etc.
    return True

def map_activated(ckta_insvc):
    return 'Yes' if clean(ckta_insvc).lower() == 'active customer' else 'No'

def map_deactivated(ckta_insvc):
    return 'Yes' if clean(ckta_insvc).lower() == 'de-activated customer' else 'No'

def map_coho(ckta_insvc):
    """Vetro ckta_insvc -> SF Coho__c picklist (Cohort Map Legend semantics)."""
    v = clean(ckta_insvc).lower()
    if v == 'active customer':       return 'Activated'
    if v == 'drop completed':        return 'Drop Completed'
    if v == 'de-activated customer': return 'De-Activated'
    return 'Serviceable'

def fmt_date(v):
    if v in (None, ''): return None
    if isinstance(v, datetime): return v.date().isoformat()
    if isinstance(v, date): return v.isoformat()
    s = str(v).strip()
    if s.endswith(' 00:00:00'): s = s[:-9]
    return s or None

def pick_dominant(values):
    """Return most-common non-empty value among an iterable, or None."""
    c = Counter(v for v in values if v)
    return c.most_common(1)[0][0] if c else None


# ─────────────────────────────────────────────────────────────────────────────
#  1. Pull Vetro + SiteTracker FDH activation in one query
# ─────────────────────────────────────────────────────────────────────────────
print(f'[1/5] Pulling Vetro + SiteTracker FDH activations from Databricks (states={STATES})...')
state_clause = "','".join(STATES)
DB_QUERY = f"""
WITH vetro AS (
  -- A-circuit only (ckta_id). B-circuit (cktb_id) is the Ting secondary ISP, deliberately
  -- excluded from SF. Old SF imports included some B-circuits; those will get flagged stale.
  SELECT
    `properties.ckta_id`     AS circuit_id,
    `properties.address`     AS address,
    `properties.housenum`    AS housenum,
    `properties.predirect`   AS predirect,
    `properties.streetname`  AS streetname,
    `properties.streetsuff`  AS streetsuff,
    `properties.postdirect`  AS postdirect,
    `properties.city`        AS city,
    `properties.state`       AS state,
    `properties.zipcode`     AS zipcode,
    `properties.region`      AS region,
    `properties.servarea`    AS servarea,
    `properties.areaid`      AS areaid,
    `properties.buildingid`  AS buildingid,
    `properties.ckta_insvc`  AS ckta_insvc,
    `properties.addtype`     AS addtype,
    `properties.projectid`   AS projectid,
    `properties.agreename`   AS agreename,
    `properties.unitnum`     AS unitnum
  FROM hive_metastore.default.vetro_external_table
  WHERE `properties.addrstatus` = 'serviceable'
    AND trim(`properties.state`) IN ('{state_clause}')
    AND `properties.ckta_id` IS NOT NULL
    AND (
      `properties.addtype` IN ('bus', 'mdu')
      OR (
        `properties.addtype` = 'sfu'
        AND lower(trim(coalesce(`properties.agreename`, ''))) NOT IN ('', 'nan', 'null', 'none', '0', 'sfu', 'bus', 'mdu', 'mtu', 'tbd', '-', '--', 'test')
        AND NOT regexp_like(upper(trim(`properties.agreename`)), '^P[A-Z][0-9]+$')
      )
    )
),
proj_act AS (
  SELECT p.name AS proj_name, s.name AS site_name,
         MAX(lf.fdh_activation_a_c) AS act_date
  FROM salesforce_sitetracker_bronze.sitetracker_project_c p
  LEFT JOIN salesforce_sitetracker_bronze.sitetracker_site_c s
    ON s.id = p.sitetracker_site_c AND s.is_deleted = false
  LEFT JOIN salesforce_sitetracker_bronze.lit_fiber_c lf
    ON lf.project_c = p.id AND lf.is_deleted = false
  WHERE p.is_deleted = false
  GROUP BY p.name, s.name
)
SELECT v.*, pa.act_date AS fdh_activated_date, pa.site_name AS site_fdh_name
FROM vetro v
LEFT JOIN proj_act pa ON pa.proj_name = v.projectid
WHERE pa.act_date IS NOT NULL
"""
with sql.connect(server_hostname=DBX_SERVER, http_path=DBX_HTTP_PATH, auth_type='databricks-oauth') as conn:
    with conn.cursor() as cur:
        cur.execute(DB_QUERY)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
print(f'  Raw rows pulled (post FDH-active gate): {len(rows):,}')


# ─────────────────────────────────────────────────────────────────────────────
#  2. Deduplicate by ckta_id and build target records
# ─────────────────────────────────────────────────────────────────────────────
print('\n[2/5] Building target Property_Location + Unit records...')

# Per-circuit (deduped by ckta_id) target unit data
units_by_cid = {}
for r in rows:
    d = dict(zip(cols, r))
    cid = clean(d.get('circuit_id'))
    if not cid or cid in units_by_cid:
        continue
    units_by_cid[cid] = d

# Group circuits to PLs by addtype-specific keying
pl_groups = defaultdict(list)        # pl_key -> list of unit dicts
pl_kind   = {}                        # pl_key -> 'bus' or 'agreement'
for cid, d in units_by_cid.items():
    addtype = clean(d.get('addtype')).lower()
    if addtype in BBA_ADDTYPES:
        bba = derive_bba(d['housenum'], d['predirect'], d['streetname'],
                         d['streetsuff'], d['postdirect'], d['city'], d['state'])
        if not bba: continue
        key = ('bus', bba)
        pl_kind[key] = 'bus'
    elif addtype in AGREEMENT_ADDTYPES:
        agree = clean(d.get('agreename'))
        if not agree: continue   # sfu enforces this; defensive for mdu/mtu
        key = ('agreement', agree)
        pl_kind[key] = 'agreement'
    else:
        continue
    pl_groups[key].append(d)

print(f'  Distinct PLs by kind:')
for k_kind, n in Counter(pl_kind.values()).items():
    print(f'    {k_kind:<10} {n:,}')
print(f'  Total unique units (circuits): {len(units_by_cid):,}')

# Build PL target records
target_pls = {}      # pl_key -> dict of fields
for key, members in pl_groups.items():
    kind = pl_kind[key]
    # Representative values across the group (most common non-empty)
    rep_market   = pick_dominant(clean(m.get('region'))     for m in members)
    rep_state    = pick_dominant(upper(m.get('state'))      for m in members)
    rep_city     = pick_dominant(upper(m.get('city'))       for m in members)
    rep_fdh      = pick_dominant(clean(m.get('site_fdh_name')) for m in members)
    rep_sa       = pick_dominant(clean(m.get('servarea'))   for m in members)
    rep_fdh_date = pick_dominant(fmt_date(m.get('fdh_activated_date')) for m in members)
    rep_bid      = pick_dominant(clean(m.get('buildingid')) for m in members)

    # All members of a PL share the same addtype (group key derived from it),
    # so dominant-pick is unambiguous.
    rep_addtype = pick_dominant(clean(m.get('addtype')).lower() for m in members)
    addr_type_label = ADDRESS_TYPE_LABEL.get(rep_addtype)
    if kind == 'bus':
        bba = key[1]
        # Only adopt agreement names that pass the junk filter
        agree = pick_dominant(clean(m.get('agreename')) for m in members
                              if is_real_agreename(m.get('agreename')))
        target_pls[key] = {
            'Business_Base_Address__c': bba,
            'Name': bba[:80],
            'Address_Type__c': addr_type_label,
            'Agreement_Name__c': agree,            # informational for bus
            'Market__c': rep_market,
            'State__c': rep_state,
            'City__c': rep_city,
            'Business_Building_Id__c': rep_bid,
            'FDH_Name__c': rep_fdh,
            'Serving_Area__c': rep_sa,
            'FDH_Activated_Date__c': rep_fdh_date,
            'Import_DateTime__c': NOW_UTC,
        }
    else:                                          # agreement-keyed
        agree = key[1]
        target_pls[key] = {
            'Business_Base_Address__c': None,      # agreement spans many buildings
            'Name': agree[:80],
            'Address_Type__c': addr_type_label,
            'Agreement_Name__c': agree,
            'Market__c': rep_market,
            'State__c': rep_state,
            'City__c': rep_city,
            'Business_Building_Id__c': None,       # not meaningful at agreement level
            'FDH_Name__c': rep_fdh,
            'Serving_Area__c': rep_sa,
            'FDH_Activated_Date__c': rep_fdh_date,
            'Import_DateTime__c': NOW_UTC,
        }

# Build Unit target records
target_units = {}
for cid, d in units_by_cid.items():
    addtype = clean(d.get('addtype')).lower()
    if addtype in BBA_ADDTYPES:
        bba = derive_bba(d['housenum'], d['predirect'], d['streetname'],
                         d['streetsuff'], d['postdirect'], d['city'], d['state'])
        if not bba: continue
        parent_key = ('bus', bba)
    elif addtype in AGREEMENT_ADDTYPES:
        agree = clean(d.get('agreename'))
        if not agree: continue
        parent_key = ('agreement', agree)
    else:
        continue

    target_units[cid] = {
        'Circuit_ID__c': cid,
        'Name': (clean(d.get('address')) or '')[:80],
        'Unit__c': clean(d.get('unitnum')) or None,
        'Activated__c': map_activated(d.get('ckta_insvc')),
        'Address_Deactivated__c': map_deactivated(d.get('ckta_insvc')),
        'Coho__c': map_coho(d.get('ckta_insvc')),
        'AreaId__c': clean(d.get('areaid')) or None,
        '_parent_key': parent_key,
        'Import_DateTime__c': NOW_UTC,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  3. Pull current SF state
# ─────────────────────────────────────────────────────────────────────────────
print('\n[3/5] Pulling current SF state...')

PL_FIELDS = ['Id', 'Business_Base_Address__c', 'Agreement_Name__c', 'Address_Type__c',
             'Name', 'Market__c', 'State__c', 'City__c', 'FDH_Name__c', 'Serving_Area__c',
             'FDH_Activated_Date__c', 'Business_Building_Id__c', 'Import_Delete_Property__c']
sf_pls = sf.query_all(f"SELECT {', '.join(PL_FIELDS)} FROM Property_Location__c")['records']
# Index two ways: by BBA (for bus) and by AgreeName (for agreement-keyed).
# IMPORTANT: BBA index keys are uppercase. SF historically stored some BBAs in
# mixed case (e.g. "3203 Valencia DR KILLEEN TX") but SF's uniqueness constraint
# is case-insensitive. Without uppercasing the index keys, our pull's
# all-uppercase BBA misses the existing record -> duplicate-create attempt fails
# AND the existing record gets incorrectly marked stale. Same for AgreeName.
sf_pl_by_bba   = {}
sf_pl_by_agree = {}
for p in sf_pls:
    bba   = clean(p.get('Business_Base_Address__c')).upper()
    agree = clean(p.get('Agreement_Name__c')).upper()
    if bba:   sf_pl_by_bba.setdefault(bba, p)
    if agree: sf_pl_by_agree.setdefault(agree, p)
print(f'  SF PLs: {len(sf_pls):,}  (by BBA={len(sf_pl_by_bba):,}, by AgreeName={len(sf_pl_by_agree):,})')

UNIT_FIELDS = ['Id', 'Name', 'Circuit_ID__c', 'Unit__c', 'Activated__c',
               'Address_Deactivated__c', 'Coho__c', 'AreaId__c',
               'Property_Location__c', 'Property_Location__r.Business_Base_Address__c',
               'Property_Location__r.Agreement_Name__c', 'Import_Delete_Unit__c']
sf_units = sf.query_all(f"SELECT {', '.join(UNIT_FIELDS)} FROM Property_Unit__c")['records']
sf_unit_by_cid = {u['Circuit_ID__c']: u for u in sf_units if u.get('Circuit_ID__c')}
print(f'  SF Units: {len(sf_units):,}')


# ─────────────────────────────────────────────────────────────────────────────
#  4. Compute diff
# ─────────────────────────────────────────────────────────────────────────────
print('\n[4/5] Computing diff...')

PL_DIFF_FIELDS   = ['Agreement_Name__c', 'Address_Type__c', 'Market__c', 'State__c',
                    'City__c', 'FDH_Name__c', 'Serving_Area__c', 'FDH_Activated_Date__c',
                    'Business_Building_Id__c']
UNIT_DIFF_FIELDS = ['Name', 'Unit__c', 'Activated__c', 'Address_Deactivated__c',
                    'Coho__c', 'AreaId__c']

def field_diff(sp, tp, fields):
    """Compute updates: only include a field when the NEW value is non-empty AND differs.
       Never wipe SF data with null/empty."""
    diffs = {}
    for k in fields:
        old, new = sp.get(k), tp.get(k)
        # Treat empty-ish equally
        old_n = '' if old in (None, '') else str(old)
        new_n = '' if new in (None, '') else str(new)
        if new_n == '': continue   # never push null/empty
        if old_n == new_n: continue
        diffs[k] = (old, new)
    return diffs

new_pls, pl_updates = [], []
for key, tp in target_pls.items():
    kind = pl_kind[key]
    if kind == 'bus':
        sp = sf_pl_by_bba.get(key[1])
    else:
        sp = sf_pl_by_agree.get(key[1])
    if not sp:
        new_pls.append({'key': key, 'kind': kind, 'tp': tp})
        continue
    diffs = field_diff(sp, tp, PL_DIFF_FIELDS)
    if diffs:
        pl_updates.append({'Id': sp['Id'], 'key': key, 'kind': kind,
                           'identifier': key[1], 'diffs': diffs, 'tp': tp})

new_units, unit_updates, reparent_units = [], [], []
for cid, tu in target_units.items():
    su = sf_unit_by_cid.get(cid)
    if not su:
        new_units.append(tu); continue
    diffs = field_diff(su, tu, UNIT_DIFF_FIELDS)
    # Re-parent check: compare unit's current parent (BBA or AgreeName) to its target parent_key
    # Old SF data sometimes had broken BBAs (e.g. duplicated predirect "NW NW RADIAL"). Our new
    # derivation produces a clean BBA. Without re-parenting, the unit stays attached to the
    # broken stale PL while we create an empty new PL. Catch and fix that here.
    cur_parent = su.get('Property_Location__r') or {}
    cur_bba   = clean(cur_parent.get('Business_Base_Address__c')).upper()
    cur_agree = clean(cur_parent.get('Agreement_Name__c')).upper()
    target_kind, target_id = tu['_parent_key']     # e.g. ('bus', '1101 NW RADIAL HWY OMAHA NE')
    if target_kind == 'bus':
        if cur_bba != target_id:                    # parent BBA changed
            reparent_units.append({'Id': su['Id'], 'cid': cid,
                                   'target_key': tu['_parent_key'],
                                   'cur_label': cur_bba or cur_agree or su['Id']})
    elif target_kind == 'agreement':
        if cur_agree != target_id:                  # parent Agreement changed
            reparent_units.append({'Id': su['Id'], 'cid': cid,
                                   'target_key': tu['_parent_key'],
                                   'cur_label': cur_agree or cur_bba or su['Id']})
    if diffs:
        unit_updates.append({'Id': su['Id'], 'cid': cid, 'diffs': diffs, 'tu': tu})

# Stale: in SF active, not in target. Compare uppercased to dodge case-mismatch
# false-stale flagging (existing SF records with mixed-case BBAs).
target_pl_bbas   = {k[1] for k in target_pls if pl_kind[k] == 'bus'}        # already upper
target_pl_agrees = {k[1] for k in target_pls if pl_kind[k] == 'agreement'}  # already upper
sf_only_pls = []
for p in sf_pls:
    if p.get('Import_Delete_Property__c'): continue
    bba = clean(p.get('Business_Base_Address__c')).upper()
    agree = clean(p.get('Agreement_Name__c')).upper()
    state_val = upper(p.get('State__c'))
    if state_val and state_val not in STATES: continue
    if bba:
        if bba in target_pl_bbas: continue
        sf_only_pls.append(p)
    elif agree:
        if agree in target_pl_agrees: continue
        sf_only_pls.append(p)
    else:
        # PL with neither bba nor agree -- legacy data, leave alone
        continue

sf_only_units = [u for u in sf_units
                 if u.get('Circuit_ID__c') not in target_units
                 and not u.get('Import_Delete_Unit__c')]


# ─────────────────────────────────────────────────────────────────────────────
#  5. Summary
# ─────────────────────────────────────────────────────────────────────────────
print('\n' + '=' * 70)
print('VETRO -> SF SYNC PLAN (PREVIEW)')
print('=' * 70)
print(f'  New PLs to create:                   {len(new_pls):,}')
new_by_kind = Counter(p['kind'] for p in new_pls)
for k, n in new_by_kind.most_common():
    print(f'    of which {k:<10} {n:,}')
print(f'  PLs with field updates:              {len(pl_updates):,}')
print(f'  New Units to create:                 {len(new_units):,}')
print(f'  Units with field updates:            {len(unit_updates):,}')
print(f'  Units to re-parent (FK move):        {len(reparent_units):,}')
print(f'  Newly-stale PLs (flag with note):    {len(sf_only_pls):,}')
print(f'  Newly-stale Units (flag with note):  {len(sf_only_units):,}')

# Field-update breakdown
print(f'\n  PL update field breakdown:')
fc = Counter()
for u in pl_updates:
    for k in u['diffs']: fc[k] += 1
for k, c in fc.most_common():
    print(f'    {c:5,d}  {k}')

print(f'\n  Unit update field breakdown:')
fc = Counter()
for u in unit_updates:
    for k in u['diffs']: fc[k] += 1
for k, c in fc.most_common():
    print(f'    {c:5,d}  {k}')

print(f'\n  Sample new PLs (first 8):')
for p in new_pls[:8]:
    tp = p['tp']
    label = tp.get('Agreement_Name__c') or tp.get('Business_Base_Address__c') or '<?>'
    print(f'    [{p["kind"]:<9}] {tp.get("State__c") or "?"} {label[:60]}')

print(f'\n  Sample PL updates (first 5):')
for u in pl_updates[:5]:
    summary = {k: v[1] for k, v in u['diffs'].items()}
    print(f'    [{u["kind"]:<9}] {u["identifier"][:50]}: {summary}')

if not APPLY:
    print(f'\n[Preview only — re-run with --apply to write]')
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
#  6. Apply
# ─────────────────────────────────────────────────────────────────────────────
print('\n' + '=' * 70)
print('APPLYING')
print('=' * 70)
audit_rows = []

def log(sf_id, name, field, before, after, action, note=''):
    audit_rows.append({'SF_Id': sf_id, 'Name': name, 'Field': field,
                       'Before': before, 'After': after, 'Source': SCRIPT_NAME,
                       'Timestamp': TS, 'Action': action, 'Note': note})

# Insert new PLs
print(f'\n[A] Creating {len(new_pls):,} new PLs')
new_pl_id_by_key = {}
if new_pls:
    payload = []
    keys_in_order = []
    for p in new_pls:
        rec = {k: v for k, v in p['tp'].items() if v is not None}
        payload.append(rec)
        keys_in_order.append((p['key'], p['kind'], p['tp']))
    for i in range(0, len(payload), 200):
        batch = payload[i:i+200]
        meta  = keys_in_order[i:i+200]
        res = sf.bulk.Property_Location__c.insert(batch)
        for r, (key, kind, tp) in zip(res, meta):
            label = tp.get('Agreement_Name__c') or tp.get('Business_Base_Address__c') or ''
            if r.get('success'):
                new_pl_id_by_key[key] = r['id']
                log(r['id'], label, '(created)', '', f'PL created ({kind})', 'CREATE',
                    note=f'kind={kind}; from Vetro sync')
            else:
                print(f"   FAIL: {label[:60]} - {r.get('errors', r)}")

# Update PLs
print(f'\n[B] Updating {len(pl_updates):,} PLs')
for i in range(0, len(pl_updates), 200):
    batch = pl_updates[i:i+200]
    rec = []
    for u in batch:
        d = {'Id': u['Id']}
        for k in u['diffs']: d[k] = u['diffs'][k][1]
        rec.append(d)
    res = sf.bulk.Property_Location__c.update(rec)
    for r, u in zip(res, batch):
        if r.get('success'):
            for k, (old, new) in u['diffs'].items():
                log(u['Id'], u['identifier'], k, old, new, 'UPDATE',
                    note=f'kind={u["kind"]}; from Vetro sync')
        else:
            print(f"   FAIL: {u['identifier'][:60]} - {r.get('errors', r)}")

# Insert new Units
print(f'\n[C] Creating {len(new_units):,} new Units')
for i in range(0, len(new_units), 200):
    batch = new_units[i:i+200]
    payload = []
    meta    = []
    for u in batch:
        parent_key = u['_parent_key']
        parent_id = new_pl_id_by_key.get(parent_key)
        if not parent_id:
            kind = pl_kind.get(parent_key)
            if kind == 'bus':
                sp = sf_pl_by_bba.get(parent_key[1])
            else:
                sp = sf_pl_by_agree.get(parent_key[1])
            if sp: parent_id = sp['Id']
        if not parent_id:
            print(f"   skip Unit {u['Circuit_ID__c']}: no parent PL for {parent_key!r}")
            continue
        rec = {k: v for k, v in u.items() if not k.startswith('_') and v is not None}
        rec['Property_Location__c'] = parent_id
        payload.append(rec)
        meta.append(u)
    if payload:
        res = sf.bulk.Property_Unit__c.insert(payload)
        for r, u in zip(res, meta):
            if r.get('success'):
                log(r['id'], u['Circuit_ID__c'], '(created)', '', 'Unit created', 'CREATE',
                    note=f'parent_key={u["_parent_key"]!r}; from Vetro sync')
            else:
                print(f"   FAIL: {u['Circuit_ID__c']} - {r.get('errors', r)}")

# Update Units
print(f'\n[D] Updating {len(unit_updates):,} Units')
for i in range(0, len(unit_updates), 200):
    batch = unit_updates[i:i+200]
    rec = [{'Id': u['Id'], **{k: u['diffs'][k][1] for k in u['diffs']}} for u in batch]
    res = sf.bulk.Property_Unit__c.update(rec)
    for r, u in zip(res, batch):
        if r.get('success'):
            for k, (old, new) in u['diffs'].items():
                log(u['Id'], u['cid'], k, old, new, 'UPDATE', note='from Vetro sync')
        else:
            print(f"   FAIL: {u['cid']} - {r.get('errors', r)}")

# Re-parent Units whose target PL changed (broken-BBA cleanup)
print(f'\n[D2] Re-parenting {len(reparent_units):,} Units')
for i in range(0, len(reparent_units), 200):
    batch = reparent_units[i:i+200]
    payload = []
    meta = []
    for u in batch:
        target_key = u['target_key']
        new_parent_id = new_pl_id_by_key.get(target_key)
        if not new_parent_id:
            kind = target_key[0]
            if kind == 'bus':
                sp = sf_pl_by_bba.get(target_key[1])
            else:
                sp = sf_pl_by_agree.get(target_key[1])
            if sp: new_parent_id = sp['Id']
        if not new_parent_id:
            print(f"   skip reparent Unit {u['cid']}: no target PL for {target_key!r}")
            continue
        payload.append({'Id': u['Id'], 'Property_Location__c': new_parent_id})
        meta.append((u, new_parent_id))
    if payload:
        res = sf.bulk.Property_Unit__c.update(payload)
        for r, (u, new_parent_id) in zip(res, meta):
            if r.get('success'):
                log(u['Id'], u['cid'], 'Property_Location__c',
                    u['cur_label'], f"{u['target_key'][0]}:{u['target_key'][1]}",
                    'REPARENT', note='from Vetro sync (BBA/AgreeName cleanup)')
            else:
                print(f"   FAIL reparent {u['cid']} - {r.get('errors', r)}")

# Flag stale PLs
print(f'\n[E] Flagging {len(sf_only_pls):,} newly-stale PLs')
if sf_only_pls:
    rec = [{'Id': p['Id'], 'Import_Delete_Property__c': True,
            'Import_Delete_Note__c': STALE_NOTE} for p in sf_only_pls]
    for i in range(0, len(rec), 200):
        batch_rec = rec[i:i+200]
        batch_p   = sf_only_pls[i:i+200]
        res = sf.bulk.Property_Location__c.update(batch_rec)
        for r, p in zip(res, batch_p):
            label = p.get('Business_Base_Address__c') or p.get('Agreement_Name__c') or p['Id']
            if r.get('success'):
                log(p['Id'], label, 'Import_Delete_Property__c', False, True,
                    'FLAG_STALE', note=STALE_NOTE)
            else:
                print(f"   FAIL: {label[:60]} - {r.get('errors', r)}")

# Flag stale Units
print(f'\n[F] Flagging {len(sf_only_units):,} newly-stale Units')
if sf_only_units:
    rec = [{'Id': u['Id'], 'Import_Delete_Unit__c': True,
            'Import_Delete_Note__c': STALE_NOTE} for u in sf_only_units]
    for i in range(0, len(rec), 200):
        batch_rec = rec[i:i+200]
        batch_u   = sf_only_units[i:i+200]
        res = sf.bulk.Property_Unit__c.update(batch_rec)
        for r, u in zip(res, batch_u):
            if r.get('success'):
                log(u['Id'], u['Circuit_ID__c'], 'Import_Delete_Unit__c', False, True,
                    'FLAG_STALE', note=STALE_NOTE)
            else:
                print(f"   FAIL: {u['Circuit_ID__c']} - {r.get('errors', r)}")

# Audit log
audit_path = AUDIT_DIR / f'vetro_sync_{TS.replace(":", "-")}.csv'
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['SF_Id', 'Name', 'Field', 'Before', 'After',
                                       'Source', 'Timestamp', 'Action', 'Note'])
    w.writeheader()
    w.writerows(audit_rows)
print(f'\nAudit log: {audit_path} ({len(audit_rows):,} rows)')
