"""
Sanity check for business_penetration.py + reconciliation against Salesforce.

Two jobs:
  A. MISS CHECK (Databricks): are we dropping any genuinely-lit business buildings?
     The penetration pull filters addrstatus='serviceable'. A unit can have an
     ACTIVE or DE-ACTIVATED customer at a NON-'serviceable' addrstatus (e.g.
     'serviceable_on_demand'); that building is lit but our filter drops it.
     Also checks whether active/deactivated business customers hide under a
     non-'bus' addtype.
  B. SF COMPARE: count what SF actually holds for business serviceability
     (Property_Location/Unit) + business Opportunity Property_Category__c (Cat 1),
     to see how the Vetro pull lines up.

Read-only. No writes anywhere.
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from collections import defaultdict, Counter
from databricks import sql
from simple_salesforce import Salesforce

STATES = ('TX', 'NE', 'AZ', 'CA')
state_clause = "','".join(STATES)
DBX_SERVER = 'adb-1444374860642533.13.azuredatabricks.net'
DBX_HTTP_PATH = '/sql/1.0/warehouses/9116e9c573d36d1c'


def clean(v):
    if v is None: return ''
    s = str(v).strip()
    return '' if s.lower() in ('nan', 'null', 'none', '') else s

def upper(v): return clean(v).upper()

def derive_bba(housenum, predirect, streetname, streetsuff, postdirect, city, state):
    parts = [upper(housenum), upper(predirect), upper(streetname),
             upper(postdirect), upper(streetsuff), upper(city), upper(state)]
    parts = [p for p in parts if p]
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()


def run_dbx():
    print('=' * 68)
    print('A. MISS CHECK (current Vetro, Databricks)')
    print('=' * 68)

    # Q1: full landscape for addtype='bus' -> addrstatus x ckta_insvc (distinct units)
    q1 = f"""
    SELECT `properties.addrstatus` AS addrstatus,
           lower(trim(`properties.ckta_insvc`)) AS insvc,
           count(DISTINCT `properties.ckta_id`) AS units
    FROM hive_metastore.default.vetro_external_table
    WHERE `properties.addtype`='bus'
      AND trim(`properties.state`) IN ('{state_clause}')
      AND `properties.ckta_id` IS NOT NULL
    GROUP BY 1, 2
    """

    # Q2: raw LIT business units (active/deactivated) at ANY addrstatus + addr parts
    q2 = f"""
    SELECT `properties.ckta_id` AS circuit_id,
           `properties.addrstatus` AS addrstatus,
           lower(trim(`properties.ckta_insvc`)) AS insvc,
           `properties.housenum` AS housenum, `properties.predirect` AS predirect,
           `properties.streetname` AS streetname, `properties.streetsuff` AS streetsuff,
           `properties.postdirect` AS postdirect, `properties.city` AS city,
           `properties.state` AS state
    FROM hive_metastore.default.vetro_external_table
    WHERE `properties.addtype`='bus'
      AND trim(`properties.state`) IN ('{state_clause}')
      AND `properties.ckta_id` IS NOT NULL
      AND lower(trim(`properties.ckta_insvc`)) IN ('active customer','de-activated customer')
    """

    # Q3: active/deactivated by addtype (are business customers hiding under mdu/sfu?)
    q3 = f"""
    SELECT `properties.addtype` AS addtype,
           lower(trim(`properties.ckta_insvc`)) AS insvc,
           count(DISTINCT `properties.ckta_id`) AS units
    FROM hive_metastore.default.vetro_external_table
    WHERE trim(`properties.state`) IN ('{state_clause}')
      AND `properties.ckta_id` IS NOT NULL
      AND lower(trim(`properties.ckta_insvc`)) IN ('active customer','de-activated customer')
    GROUP BY 1, 2
    """

    with sql.connect(server_hostname=DBX_SERVER, http_path=DBX_HTTP_PATH,
                     auth_type='databricks-oauth') as conn:
        with conn.cursor() as cur:
            cur.execute(q1); c1 = [d[0] for d in cur.description]; r1 = cur.fetchall()
            cur.execute(q2); c2 = [d[0] for d in cur.description]; r2 = cur.fetchall()
            cur.execute(q3); c3 = [d[0] for d in cur.description]; r3 = cur.fetchall()

    print('\n[Q1] addtype=bus  addrstatus x ckta_insvc (distinct units):')
    land = defaultdict(dict)
    for row in r1:
        d = dict(zip(c1, row))
        land[clean(d['addrstatus']) or '(blank)'][clean(d['insvc']) or '(blank)'] = d['units']
    for st in sorted(land):
        parts = ', '.join(f"{k}={v:,}" for k, v in sorted(land[st].items()))
        print(f'   {st:<24} {parts}')

    # Dedup lit units by circuit; a circuit counts as "captured" if ANY row is serviceable
    by_cid = defaultdict(list)
    for row in r2:
        by_cid[clean(dict(zip(c2, row))['circuit_id'])].append(dict(zip(c2, row)))
    captured_units = missed_units = 0
    missed_status = Counter()
    bba_has_serviceable_lit = defaultdict(bool)
    bba_has_missed_lit = defaultdict(bool)
    for cid, recs in by_cid.items():
        if not cid: continue
        has_serv = any(clean(r['addrstatus']) == 'serviceable' for r in recs)
        rep = next((r for r in recs if clean(r['addrstatus']) == 'serviceable'), recs[0])
        bba = derive_bba(rep['housenum'], rep['predirect'], rep['streetname'],
                         rep['streetsuff'], rep['postdirect'], rep['city'], rep['state'])
        if has_serv:
            captured_units += 1
            if bba: bba_has_serviceable_lit[bba] = True
        else:
            missed_units += 1
            missed_status[clean(rep['addrstatus']) or '(blank)'] += 1
            if bba: bba_has_missed_lit[bba] = True

    entirely_missed_bbas = [b for b in bba_has_missed_lit
                            if not bba_has_serviceable_lit.get(b)]
    print(f'\n[Q2] LIT business units (active/deactivated), dedup by circuit:')
    print(f'   total lit units (any addrstatus) : {captured_units + missed_units:,}')
    print(f'   captured (addrstatus=serviceable): {captured_units:,}')
    print(f'   MISSED  (other addrstatus)       : {missed_units:,}')
    if missed_units:
        for st, n in missed_status.most_common():
            print(f'      missed at addrstatus={st}: {n:,}')
    print(f'   buildings with a missed lit unit : {len(bba_has_missed_lit):,}')
    print(f'   ENTIRELY-missed lit buildings    : {len(entirely_missed_bbas):,}')
    for b in entirely_missed_bbas[:15]:
        print(f'      - {b}')

    print(f'\n[Q3] active/deactivated by addtype (distinct units):')
    for row in sorted(r3, key=lambda x: (str(x[0]), str(x[1]))):
        d = dict(zip(c3, row))
        print(f'   {(clean(d["addtype"]) or "(blank)"):<8} {clean(d["insvc"]):<22} {d["units"]:,}')

    return entirely_missed_bbas


def run_sf():
    print('\n' + '=' * 68)
    print('B. SF COMPARE (what Salesforce holds for business)')
    print('=' * 68)
    sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984',
                    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

    def agg(soql):
        return sf.query_all(soql)['records']

    print('\n[PL] Property_Location__c Address_Type__c=Business:')
    for r in agg("SELECT Import_Delete_Property__c stale, COUNT(Id) c "
                 "FROM Property_Location__c WHERE Address_Type__c='Business' "
                 "GROUP BY Import_Delete_Property__c"):
        print(f"   stale={r['stale']}: {r['c']:,}")

    print('\n[PU] Property_Unit__c under business PLs (non-stale), by Coho__c:')
    for r in agg("SELECT Coho__c coho, COUNT(Id) c FROM Property_Unit__c "
                 "WHERE Property_Location__r.Address_Type__c='Business' "
                 "AND Import_Delete_Unit__c=false GROUP BY Coho__c"):
        print(f"   {str(r['coho']):<16} {r['c']:,}")
    print('   --- by Activated__c ---')
    for r in agg("SELECT Activated__c a, COUNT(Id) c FROM Property_Unit__c "
                 "WHERE Property_Location__r.Address_Type__c='Business' "
                 "AND Import_Delete_Unit__c=false GROUP BY Activated__c"):
        print(f"   Activated={str(r['a']):<6} {r['c']:,}")
    print('   --- by Address_Deactivated__c ---')
    for r in agg("SELECT Address_Deactivated__c d, COUNT(Id) c FROM Property_Unit__c "
                 "WHERE Property_Location__r.Address_Type__c='Business' "
                 "AND Import_Delete_Unit__c=false GROUP BY Address_Deactivated__c"):
        print(f"   Deactivated={str(r['d']):<6} {r['c']:,}")

    print('\n[Opp] Property_Category__c by RecordType (open + closed):')
    for r in agg("SELECT RecordType.DeveloperName rt, Property_Category__c cat, COUNT(Id) c "
                 "FROM Opportunity GROUP BY RecordType.DeveloperName, Property_Category__c "
                 "ORDER BY RecordType.DeveloperName"):
        print(f"   {str(r['rt']):<14} {str(r['cat'] or '(blank)'):<10} {r['c']:,}")


if __name__ == '__main__':
    missed = run_dbx()
    run_sf()
