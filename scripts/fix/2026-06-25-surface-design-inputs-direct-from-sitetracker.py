"""STOPGAP (2026-06-25): unblock Taylor's Design Inputs / Ready-for-Engineering
report columns WITHOUT the stalled mirror columns.

The org-wide field-provisioning stall (instance USA780) left the two mirror
source columns (SiteTracker_Project__c.Desktop_Design_Inputs_A__c,
Ready_for_Engineering__c) unqueryable, so surface_to_opportunity.py guard-skips
them and writes nothing -- even though the Opp targets (ST_Design_Inputs_Received__c,
ST_Ready_for_Engineering__c) provisioned fine.

This bypasses the dead mirror columns: it reads the two values straight from the
real source, MDU_Fiber__c in the SiteTracker org, and joins to the Opportunity via
the mirror's already-live link (SiteTracker_Record_Id__c -> Opportunity__c). It
reuses surface's exact "most-advanced project per Opp" rule so values stay
consistent with the other ST_* milestone columns.

Safe stopgap: produces the same values the normal sync+surface path will once the
mirror columns provision -- at which point surface resumes and overwrites identically.
No new fields, no metadata operations.

Default = DRY RUN. Pass --apply to write.
"""
import argparse
from simple_salesforce import Salesforce

sf_main = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984',
                     security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')
sf_st = Salesforce(username='cass@ubiquitygp.com', password='Hawaiian84',
                   security_token='fe2pen6ceQeqGhWXhBeOIjqP')

# Same ranking surface_to_opportunity.py uses to pick the primary project per Opp.
RANK = {
    "4. Project - Completed": 5,
    "3. Project - Construction Phase": 4,
    "2. Project - Design Phase": 3,
    "2. Project - Up Next": 2,
    "1. Project - PAL/ROE Signed": 1,
    "5. Project - Pending Business Case Approval": 0,
}


def query_all(sf, soql):
    res = sf.query(soql)
    recs = res['records']
    while not res['done']:
        res = sf.query_more(res['nextRecordsUrl'], True)
        recs.extend(res['records'])
    return recs


def as_date(v):
    """Opp target is a Date; MDU_Fiber source may be Date or DateTime."""
    if v and 'T' in str(v):
        return str(v)[:10]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Write changes (default: dry run)')
    args = ap.parse_args()

    # 1. Mirror rows that ARE linked to an Opp -> pick most-advanced per Opp (surface's rule)
    mirror = query_all(sf_main, """
        SELECT Opportunity__c, Build_Status__c, LastModifiedDate, SiteTracker_Record_Id__c
        FROM SiteTracker_Project__c
        WHERE Opportunity__c != null AND SiteTracker_Record_Id__c != null
    """)
    byopp = {}
    for m in mirror:
        byopp.setdefault(m['Opportunity__c'], []).append(m)
    primary_by_opp = {}   # Opp Id -> MDU_Fiber Id of the most-advanced project
    for oid, projs in byopp.items():
        p = sorted(projs, key=lambda x: (RANK.get(x['Build_Status__c'], -1),
                                         x['LastModifiedDate'] or ''), reverse=True)[0]
        primary_by_opp[oid] = p['SiteTracker_Record_Id__c'][:15]
    print(f"[INFO] {len(mirror)} linked mirror rows across {len(primary_by_opp)} Opportunities")

    # 2. Pull the two handoff values from the REAL source (ST org), for the primary fibers only
    fiber_ids = set(primary_by_opp.values())
    fiber_vals = {}  # MDU_Fiber Id(15) -> (design_inputs_date, ready_for_eng_bool)
    fibers = query_all(sf_st, """
        SELECT Id, Desktop_Design_Inputs_A__c, Ready_for_Engineering__c FROM MDU_Fiber__c
    """)
    for f in fibers:
        fid = f['Id'][:15]
        if fid in fiber_ids:
            fiber_vals[fid] = (as_date(f.get('Desktop_Design_Inputs_A__c')),
                               bool(f.get('Ready_for_Engineering__c')))
    print(f"[INFO] resolved {len(fiber_vals)}/{len(fiber_ids)} primary fibers from SiteTracker")

    # 3. Desired Opp values
    desired = {}
    for oid, fid in primary_by_opp.items():
        di, rfe = fiber_vals.get(fid, (None, False))
        desired[oid] = {'ST_Design_Inputs_Received__c': di, 'ST_Ready_for_Engineering__c': rfe}

    # 4. Only write Opps whose value actually changes
    cur = {o['Id']: o for o in query_all(sf_main,
        "SELECT Id, ST_Design_Inputs_Received__c, ST_Ready_for_Engineering__c "
        "FROM Opportunity WHERE Id IN ('" + "','".join(desired) + "')")}
    updates = []
    for oid, vals in desired.items():
        c = cur.get(oid, {})
        if (c.get('ST_Design_Inputs_Received__c') != vals['ST_Design_Inputs_Received__c']
                or bool(c.get('ST_Ready_for_Engineering__c')) != vals['ST_Ready_for_Engineering__c']):
            updates.append({'Id': oid, **vals})

    n_di = sum(1 for u in updates if u['ST_Design_Inputs_Received__c'])
    n_rfe = sum(1 for u in updates if u['ST_Ready_for_Engineering__c'])
    print(f"[INFO] {len(updates)} Opps need updating "
          f"({n_di} get a Design-Inputs date, {n_rfe} get Ready-for-Eng=true)")

    for u in updates[:25]:
        print(f"  {'[SET] ' if args.apply else '[WOULD SET] '}{u['Id']} -> "
              f"DesignInputs={u['ST_Design_Inputs_Received__c']} "
              f"ReadyForEng={u['ST_Ready_for_Engineering__c']}")
    if len(updates) > 25:
        print(f"  ... +{len(updates) - 25} more")

    if not args.apply:
        print("[DRY-RUN] No writes performed. Re-run with --apply to commit.")
        return
    if not updates:
        print("[SUCCESS] Nothing to update.")
        return

    res = sf_main.bulk.Opportunity.update(updates)
    ok = sum(1 for r in res if r.get('success'))
    errs = [r for r in res if not r.get('success')]
    print(f"[APPLY DONE] Updated: {ok}, Errors: {len(errs)}")
    for e in errs[:5]:
        print("  ERR:", e)


if __name__ == '__main__':
    main()
