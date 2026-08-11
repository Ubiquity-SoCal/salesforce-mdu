"""Audit MDU RT Opps in EMA/Bulk In Progress stage.
Per methodology: literally an EMA/Bulk Agreement being negotiated (NOT post-PAL construction).
Should have an EMA/Bulk/NEMA/MSA Agreement child in Review/Sign/Paused (active negotiation).
Apply 3-signal rule (Next_Action / Projected_Close_Date / IronClad linkage)."""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

EMA_BULK_TYPES = {'EMA','Bulk','NEMA','2nd ISP MSA Addendum','MSA','EMA Addendum','Bulk Addendum'}
PAL_ROE_TYPES = {'PAL','ROE','PAL Addendum','PAL/ROE','ROE Addendum'}
COMPLETED_STATUS = {'Completed','Signed','Active','Executed'}

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']

opps = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name, Sales_Status__c,
           Projected_Close_Date__c, CloseDate, Next_Action__c, Next_Action_Date__c,
           Notes_Count__c, Agreement_Count__c, CreatedDate, LastModifiedDate
    FROM Opportunity
    WHERE StageName = 'EMA/Bulk In Progress' AND RecordTypeId = '{rt}'
    ORDER BY Owner.Name, Name
""")['records']
print(f"MDU EMA/Bulk In Progress Opps: {len(opps)}")
ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)

agr_by_opp = defaultdict(list)
for r in sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c, Signed_Date__c,
           IronClad_ID__c, IronClad_Stage__c, IronClad_Contract_Status__c
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
""")['records']:
    agr_by_opp[r['Opportunity__c']].append(r)

# SiteTracker projects
st_by_opp = defaultdict(list)
desc = sf.SiteTracker_Project__c.describe()
st_fields = [f['name'] for f in desc['fields']]
opp_fk = next((f for f in st_fields if f in ('Opportunity__c','Opp__c')), None)
build_fld = next((f for f in st_fields if f in ('Build_Status__c','BuildStatus__c','Status__c')), None)
if opp_fk:
    st_q = sf.query_all(f"""
        SELECT Id, Name, {opp_fk}, {build_fld if build_fld else 'Id'}
        FROM SiteTracker_Project__c WHERE {opp_fk} IN ('{ids_str}')
    """)
    for r in st_q['records']:
        st_by_opp[r[opp_fk]].append({'Id': r['Id'], 'Name': r['Name'], 'Build_Status': r.get(build_fld)})

clean = []
auto_bump_complete = []   # all EMA/Bulk completed -> EMA/Bulk Complete
auto_bump_palroe = []      # no EMA/Bulk activity -> PAL/ROE Complete
review = []                # no 3-signal or other oddity
stats = Counter()

for o in opps:
    agrs = agr_by_opp[o['Id']]
    sts = st_by_opp[o['Id']]
    emabulk_agrs = [a for a in agrs if a.get('Agreement_Type__c') in EMA_BULK_TYPES]
    palroe_agrs  = [a for a in agrs if a.get('Agreement_Type__c') in PAL_ROE_TYPES]
    eb_active = [a for a in emabulk_agrs if a.get('Status__c') not in ('Cancelled',) and a.get('Status__c') not in COMPLETED_STATUS]
    eb_completed = [a for a in emabulk_agrs if a.get('Status__c') in COMPLETED_STATUS or a.get('Signed_Date__c')]
    eb_cancelled = [a for a in emabulk_agrs if a.get('Status__c') == 'Cancelled']
    has_ic_link = any(a.get('IronClad_ID__c') for a in agrs)
    has_signal = bool(o.get('Next_Action__c') or o.get('Projected_Close_Date__c') or has_ic_link)

    flags = []
    if not emabulk_agrs:
        flags.append('NO EMA/Bulk Agreement child (only PAL/ROE or none)')
    elif eb_completed and not eb_active:
        flags.append(f'All EMA/Bulk Completed ({len(eb_completed)}) — should be EMA/Bulk Complete')
    elif eb_cancelled and not eb_active and not eb_completed:
        flags.append('All EMA/Bulk Cancelled — likely back to PAL/ROE Complete or Closed Lost')
    if not has_signal:
        flags.append('NO 3-signal (no Next_Action, no Projected, no IC link)')

    stats['total'] += 1
    if not flags:
        stats['clean'] += 1
        clean.append((o, agrs, sts))
    elif any('All EMA/Bulk Completed' in f for f in flags):
        stats['auto_bump_complete'] += 1
        auto_bump_complete.append((o, agrs, sts, flags))
    elif any('NO EMA/Bulk Agreement child' in f for f in flags):
        stats['no_emabulk_child'] += 1
        review.append((o, agrs, sts, flags, 'no_emabulk_child'))
    elif any('All EMA/Bulk Cancelled' in f for f in flags):
        stats['all_cancelled'] += 1
        review.append((o, agrs, sts, flags, 'all_cancelled'))
    else:
        stats['review_other'] += 1
        review.append((o, agrs, sts, flags, 'other'))

print()
print(f"Stats: {dict(stats)}")
print()

print("=" * 100)
print(f"AUTO-BUMP -> EMA/Bulk Complete (all EMA/Bulk children Completed/Signed) — {len(auto_bump_complete)}")
print("=" * 100)
for o, agrs, sts, flags in auto_bump_complete:
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}  Next_Action: {o.get('Next_Action__c')}")
    for a in agrs:
        print(f"    Agr {a['Name']} Type={a.get('Agreement_Type__c')} Status={a.get('Status__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")

print()
print("=" * 100)
print(f"REVIEW — {len(review)}")
print("=" * 100)
by_owner = defaultdict(list)
for o, agrs, sts, flags, bucket in review:
    by_owner[o['Owner']['Name']].append((o, agrs, sts, flags, bucket))
for owner, items in sorted(by_owner.items()):
    print(f"\n--- {owner} ({len(items)}) ---")
    for o, agrs, sts, flags, bucket in items:
        print(f"  {o['Name']}  Id={o['Id']}  [{bucket}]")
        print(f"    Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}")
        print(f"    Next_Action: {o.get('Next_Action__c')}")
        for a in agrs:
            print(f"      Agr {a['Name']} Type={a.get('Agreement_Type__c')} Status={a.get('Status__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")
        if sts:
            for s in sts:
                print(f"      ST: {s['Name']}  Build_Status={s.get('Build_Status')}")
        print(f"    FLAGS: {', '.join(flags)}")

print()
print("=" * 100)
print(f"CLEAN — {len(clean)}")
print("=" * 100)
clean_by_owner = Counter(o['Owner']['Name'] for o, *_ in clean)
for owner, n in sorted(clean_by_owner.items(), key=lambda x: -x[1]):
    print(f"  {owner}: {n}")
