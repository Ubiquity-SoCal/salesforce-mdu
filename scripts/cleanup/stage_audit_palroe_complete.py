"""Audit MDU RT Opps in PAL/ROE Complete stage.
Should have at least one Completed PAL or ROE Agreement child.
Flag if no Agreement / all Cancelled / has SiteTracker construction underway.
Apply Koa's 3-signal check: Next_Action / Projected / IronClad linkage."""
from simple_salesforce import Salesforce
from collections import defaultdict, Counter

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

BULK_DATES = {'2026-03-24','2026-03-31','2026-04-07','2026-04-21','2026-04-25','2026-04-29'}

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']

opps = sf.query_all(f"""
    SELECT Id, Name, OwnerId, Owner.Name, Sales_Status__c,
           Projected_Close_Date__c, CloseDate, Next_Action__c, Next_Action_Date__c,
           Notes_Count__c, Agreement_Count__c, CreatedDate, LastModifiedDate
    FROM Opportunity
    WHERE StageName = 'PAL/ROE Complete' AND RecordTypeId = '{rt}'
    ORDER BY Owner.Name, Name
""")['records']
print(f"MDU PAL/ROE Complete Opps: {len(opps)}")
ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)

# Agreements
agr_by_opp = defaultdict(list)
for r in sf.query_all(f"""
    SELECT Id, Name, Opportunity__c, Status__c, Agreement_Type__c, Signed_Date__c,
           IronClad_ID__c, IronClad_Stage__c, IronClad_Contract_Status__c
    FROM Agreement__c WHERE Opportunity__c IN ('{ids_str}')
""")['records']:
    agr_by_opp[r['Opportunity__c']].append(r)

# SiteTracker projects (lookup by Opportunity__c on SiteTracker_Project__c)
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

clean = 0
review = []
move_emabulk_inprog = []
move_closed_lost = []
stats = Counter()

for o in opps:
    agrs = agr_by_opp[o['Id']]
    sts = st_by_opp[o['Id']]
    types = Counter(a.get('Agreement_Type__c') for a in agrs)
    statuses = Counter(a.get('Status__c') for a in agrs)
    has_signed_pal_roe = any(
        (a.get('Status__c') in ('Completed','Signed','Active','Executed') or a.get('Signed_Date__c'))
        and a.get('Agreement_Type__c') in ('PAL','ROE','PAL Addendum','PAL/ROE')
        for a in agrs
    )
    has_signed_emabulk = any(
        (a.get('Status__c') in ('Completed','Signed','Active','Executed') or a.get('Signed_Date__c'))
        and a.get('Agreement_Type__c') in ('EMA','Bulk','NEMA','2nd ISP MSA Addendum','MSA')
        for a in agrs
    )
    all_cancelled = agrs and all(a.get('Status__c') == 'Cancelled' for a in agrs)
    has_ic_link = any(a.get('IronClad_ID__c') for a in agrs)
    has_signal = bool(o.get('Next_Action__c') or o.get('Projected_Close_Date__c') or has_ic_link)

    flags = []
    if not agrs:
        flags.append('NO Agreement child')
    if all_cancelled:
        flags.append('ALL Agreements Cancelled')
    if not has_signed_pal_roe and agrs and not all_cancelled:
        flags.append('No SIGNED PAL/ROE child')
    if has_signed_emabulk and sts:
        flags.append('Has signed EMA/Bulk + SiteTracker project — should be EMA/Bulk In Progress or Complete')
    elif has_signed_emabulk:
        flags.append('Has signed EMA/Bulk — should be EMA/Bulk In Progress (no ST project yet)')
    elif sts:
        flags.append(f'Has SiteTracker project ({len(sts)})')
    if not has_signal:
        flags.append('NO 3-signal (no Next_Action, no Projected, no IC link)')

    stats['total'] += 1
    if 'Has signed EMA/Bulk' in ''.join(flags):
        stats['move_emabulk'] += 1
        move_emabulk_inprog.append((o, agrs, sts, flags))
    elif all_cancelled or 'NO Agreement child' in flags:
        stats['review'] += 1
        if all_cancelled:
            move_closed_lost.append((o, agrs, sts, flags))
        else:
            review.append((o, agrs, sts, flags))
    elif flags:
        # has flags but doesn't auto-bucket
        if 'No SIGNED PAL/ROE' in ''.join(flags):
            stats['review'] += 1
            review.append((o, agrs, sts, flags))
        else:
            stats['clean_with_flags'] += 1
    else:
        stats['clean'] += 1

print()
print(f"Stats: {dict(stats)}")
print()

print("=" * 100)
print(f"REVIEW (no signed PAL/ROE or no Agreement) — {len(review)}")
print("=" * 100)
for o, agrs, sts, flags in review:
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
    print(f"  Sales_Status: {o.get('Sales_Status__c')}  Projected: {o.get('Projected_Close_Date__c')}")
    print(f"  Next_Action: {o.get('Next_Action__c')}")
    if agrs:
        for a in agrs:
            print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")
    print(f"  FLAGS: {', '.join(flags)}")

print()
print("=" * 100)
print(f"ALL AGREEMENTS CANCELLED — likely Closed Lost — {len(move_closed_lost)}")
print("=" * 100)
for o, agrs, sts, flags in move_closed_lost:
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}")
    for a in agrs:
        print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')}")

print()
print("=" * 100)
print(f"HAS SIGNED EMA/BULK — should advance to EMA/Bulk stages — {len(move_emabulk_inprog)}")
print("=" * 100)
for o, agrs, sts, flags in move_emabulk_inprog:
    has_st = bool(sts)
    suggested = 'EMA/Bulk In Progress' if not has_st else 'EMA/Bulk In Progress (or Complete depending on ST status)'
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={o['Id']}  -> {suggested}")
    for a in agrs:
        print(f"    Agr {a['Name']} Status={a.get('Status__c')} Type={a.get('Agreement_Type__c')} Signed={a.get('Signed_Date__c')} IC={a.get('IronClad_ID__c')}")
    if sts:
        for s in sts:
            print(f"    ST: {s['Name']}  Build_Status={s.get('Build_Status')}")
