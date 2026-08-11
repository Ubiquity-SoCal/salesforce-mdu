"""Weekly Wednesday forecast-gap review.

Pairs with the forward-looking view (Opps forecasted 30-90 days out, which Koa
filters directly in SF). This is the inverse: open Opps that people are actually
WORKING but that are missing or breaking their forecast.

Signal note: in this org `LastActivityDate` is always empty (Tasks/Events are not
logged) and `LastModifiedDate` is polluted by bulk syncs, so neither is a reliable
"someone is working this" signal. The only trustworthy signal is the manually typed
`Next_Action__c` field. Every flag below keys off that.

Pursuit Status (`Substatus__c`) is the team's authoritative "we already know it is
stuck" picklist (Owner Unresponsive / Bulk-Marketing Rejected / ISP or Funding Needed
/ etc.). A classified Opp is NOT an unattended gap, so the gap flags exclude it and it
collects in A2 instead. Do not re-detect stalls from Next Action text when this field
exists.

The Core 5 flags:
  A1  Live work, NO forecast      -> active stage + Next Action + no projected close,
                                     next step not stale -> add a date.
  A2  Aging & UNCLASSIFIED        -> active stage + no forecast + next step >45d old but
                                     no Pursuit Status -> classify it or close it.
  B   Forecast in the past        -> Projected_Close_Date < today, still open.
  E   Agreement, stage lagging    -> a signed agreement / IronClad link exists but the
                                     stage never advanced past Contract Negotiations.
  F   Next Action overdue         -> the committed Next_Action_Date is in the past.
  Any Opp with a Pursuit Status is dropped from ALL flags (count reported separately).

Read-only. Terminal output only (no files written). Logic is exposed as functions
(`connect`, `fetch`, `classify`) so the email generator can reuse it.
Usage:  python forecast_gap_review.py [Owner Name] [Owner Name] ...
        (no args = Brett Spivey, Bill Holick, Melissa Baker)
"""
import re
import sys, io
from datetime import date
from collections import defaultdict
from simple_salesforce import Salesforce

# ---------------------------------------------------------------- config
CREDS_PATH = r'C:\Users\cass\Work_Projects\SalesForce\api\Salesforce_Credentials.txt'
DEFAULT_OWNERS = ['Brett Spivey', 'Bill Holick', 'Melissa Baker']
ACTIVE_STAGES = {'Prospecting', 'Engaged', 'Proposal Sent', 'Contract Negotiations',
                 'PAL/ROE Complete', 'Marketing/Bulk In Progress'}
PRE_SECURED = {'Prospecting', 'Engaged', 'Proposal Sent', 'Contract Negotiations'}
STALE_NEXT_ACTION_DAYS = 45  # a committed next step older than this reads as abandoned

# Next_Action__c is this org's only trustworthy "a human is tracking this" signal, which makes
# it fragile: anything SCRIPTED into the field impersonates that signal. On 2026-07-24 a
# backfill stamped 167 revived Opps with a movement note (see
# SalesForce/scripts/fix/2026-07-24-backfill-next-action-on-revived-opps.py). Those are history,
# not intent - nobody has picked the property up, and per Koa no forecast date is owed until
# someone actually puts it on the radar. Left alone they would have turned A1 from 6 into ~173.
# Matched here rather than in a single flag so every present and future consumer of the signal
# inherits the exclusion. Extend this tuple if another script ever writes to the field.
SYSTEM_STAMP_RES = (
    re.compile(r'^Moved from .+ to (?:Prospects|Closed Lost) per \d{1,2}/\d{1,2}/\d{4} call$'),
)


def is_system_stamp(na):
    """True if Next_Action__c was written by a script, so it is NOT evidence of human work."""
    na = (na or '').strip()
    return any(rx.match(na) for rx in SYSTEM_STAMP_RES)

LABELS = [
    ('A1', 'Live work, NO forecast (add a date)'),
    ('A2', 'Aging & UNCLASSIFIED, no forecast (set a Pursuit Status or close)'),
    ('B',  'Forecast date is in the past, still open'),
    ('E',  'Agreement/IronClad exists, stage stuck pre-PAL/ROE'),
    ('F',  'Committed Next Action date is overdue'),
]


# ---------------------------------------------------------------- data access
def connect():
    creds = {}
    with open(CREDS_PATH, encoding='utf-8') as f:
        for line in f:
            if ':' in line:
                k, v = line.split(':', 1)
                creds[k.strip().lower()] = v.strip()
    return Salesforce(username=creds['username'], password=creds['password'],
                      security_token=creds['security token'])


def fetch(sf, owners):
    owner_clause = "(" + " OR ".join(f"Owner.Name = '{o}'" for o in owners) + ")"
    return sf.query_all(f"""
        SELECT Id, Name, Owner.Name, StageName, RecordType.Name,
               Projected_Close_Date__c, Next_Action__c, Next_Action_Date__c,
               Substatus__c, Agreement_Count__c, IronClad_URL__c, Units__c,
               Property_City__c, Property_State__c
        FROM Opportunity
        WHERE IsClosed = false AND {owner_clause}
        ORDER BY Owner.Name, StageName
    """)['records']


# ---------------------------------------------------------------- classify
def classify(recs, today):
    """Return flags: {flag_key: {owner: [row dict, ...]}}."""
    def days_past(dstr):
        if not dstr:
            return None
        return (today - date.fromisoformat(dstr[:10])).days

    flags = defaultdict(lambda: defaultdict(list))

    def add(flag, r, note=""):
        owner = (r.get('Owner') or {}).get('Name', '?')
        flags[flag][owner].append({
            'owner': owner, 'name': r['Name'], 'stage': r['StageName'],
            'pcd': r.get('Projected_Close_Date__c') or '-',
            'pcd_past': days_past(r.get('Projected_Close_Date__c')),
            'na': (r.get('Next_Action__c') or '').strip(),
            'nad': r.get('Next_Action_Date__c') or '',
            'nad_past': days_past(r.get('Next_Action_Date__c')),
            'substatus': r.get('Substatus__c') or '',
            'agr': r.get('Agreement_Count__c') or 0,
            'units': r.get('Units__c') or '',
            'city': r.get('Property_City__c') or '', 'state': r.get('Property_State__c') or '',
            'note': note,
        })

    for r in recs:
        stage = r['StageName']
        pcd = r.get('Projected_Close_Date__c')
        pcd_past = days_past(pcd)
        # a scripted stamp reads as NO next action for signal purposes. It still shows in the
        # detail rows (see add(), which uses the raw field) so the reader can see what happened.
        na = '' if is_system_stamp(r.get('Next_Action__c')) else (r.get('Next_Action__c') or '').strip()
        nad = r.get('Next_Action_Date__c')
        nad_past = days_past(nad)
        agr = r.get('Agreement_Count__c') or 0
        has_ic = bool(r.get('IronClad_URL__c'))
        sub = r.get('Substatus__c') or ''        # Pursuit Status, authoritative
        has_pursuit = bool(sub)
        stale = nad_past is not None and nad_past > STALE_NEXT_ACTION_DAYS

        # A Pursuit Status means the team already classified why it is stuck. That is
        # NOT an unattended gap, so it is excluded from every flag below.
        if has_pursuit:
            continue

        # A1: live, no forecast, next step not stale -> just add a date
        if stage in ACTIVE_STAGES and na and pcd is None and not stale:
            add('A1', r, f"next due {nad}" if nad else "no date")

        # A2: aging & UNCLASSIFIED -> nobody set a Pursuit Status; classify it or close it
        if stage in ACTIVE_STAGES and pcd is None and stale:
            add('A2', r, f"next step {nad_past}d old")

        if pcd_past is not None and pcd_past > 0 and stage != 'On Hold':
            add('B', r, f"{pcd_past}d overdue")

        if (agr > 0 or has_ic) and stage in PRE_SECURED:
            add('E', r, f"agr={agr}{' +IC' if has_ic else ''}")

        if nad_past is not None and nad_past > 0:
            add('F', r, f"{nad_past}d overdue")

    return flags


# ---------------------------------------------------------------- report
def print_report(flags, owners, today, n_scanned, n_classified, n_stamped=0):
    print(f"\n=== Wednesday forecast-gap review  {today}  ===")
    print(f"owners: {', '.join(owners)}   |   open Opps scanned: {n_scanned}")
    print(f"excluded {n_classified} already-classified (Pursuit Status set, team knows)")
    if n_stamped:
        print(f"ignored {n_stamped} scripted Next Action stamps (revived Opps, nobody on them "
              f"yet, no forecast owed until someone picks one up)")
    print("signal = Next_Action__c (LastActivity/LastModified are unreliable here)\n")

    hdr = f"{'FLAG':56s}" + "".join(f"{o.split()[0]:>9}" for o in owners) + f"{'TOTAL':>8}"
    print(hdr)
    print("-" * len(hdr))
    for key, label in LABELS:
        counts = [len(flags[key].get(o, [])) for o in owners]
        print(f"{key + '. ' + label:56s}" + "".join(f"{c:>9}" for c in counts) + f"{sum(counts):>8}")

    for key, label in LABELS:
        total = sum(len(flags[key].get(o, [])) for o in owners)
        if not total:
            continue
        print(f"\n\n########## {key}. {label}  ({total}) ##########")
        for o in owners:
            rows = flags[key].get(o, [])
            if not rows:
                continue
            print(f"\n  ---- {o}  ({len(rows)}) ----")
            for x in sorted(rows, key=lambda z: z['stage']):
                loc = f"{x['city']},{x['state']}".strip(',')
                na = f"  | next: {x['na'][:55]}" if x['na'] else ""
                u = x['units']
                u = str(int(u)) if isinstance(u, (int, float)) and float(u) == int(u) else u
                print(f"    [{x['stage']}] {x['name']}  ({x['note']}) | agr={x['agr']} "
                      f"| u={u} | {loc}{na}")
    print()


def main():
    owners = sys.argv[1:] or DEFAULT_OWNERS
    today = date.today()
    sf = connect()
    recs = fetch(sf, owners)
    flags = classify(recs, today)
    n_classified = sum(1 for r in recs if r.get('Substatus__c'))
    n_stamped = sum(1 for r in recs
                    if not r.get('Substatus__c') and is_system_stamp(r.get('Next_Action__c')))
    print_report(flags, owners, today, len(recs), n_classified, n_stamped)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
