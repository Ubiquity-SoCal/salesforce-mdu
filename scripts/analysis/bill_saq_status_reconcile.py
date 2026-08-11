"""Phase A (read-only): reconcile Bill's MDU SAQ master list against current SF
Opportunity stages. Splits into a PUSH set (safe to write) and a QUARANTINE set
(flagged for human review). No SF writes.

Decisions (2026-06-24, see spec):
  - all 389 rows; target = StageName (+reason)
  - Closed - Contact Info -> Closed Lost / No Contact Info
  - Proposal Review -> Contract Negotiations
  - match by Agreement_Name__c, then exact name+state fallback (tagged name-matched)
  - quarantine: secured-site closes, mid-flight closes, regressions, reopens, SF dups
Spec: SalesForce/docs/superpowers/specs/2026-06-24-bill-saq-status-sf-sync-design.md
"""
import csv
import datetime as dt
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
from simple_salesforce import Salesforce

SRC = r'C:\Users\cass\Downloads\Master List MDU Assignments.xlsm'
CREDS = r'C:\Users\cass\Work_Projects\SalesForce\api\Salesforce_Credentials.txt'
OUTDIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\data\output\bill-saq-reconcile')

# --- mapping -------------------------------------------------------------------

STATUS_MAP = {
    'Engaged':               ('Engaged', None, None),
    'Proposal Sent':         ('Proposal Sent', None, None),
    'Proposal Review':       ('Contract Negotiations', None, None),
    'Pending Signature':     ('Contract Negotiations', None, None),
    'Completed':             ('PAL/ROE Complete', None, None),
    'Hold':                  ('On Hold', 'Hold_Reason__c', None),
    'Closed - Lost':         ('Closed Lost', 'Loss_Reason__c', None),
    'Closed - Contact Info': ('Closed Lost', 'Loss_Reason__c', 'No Contact Info'),
    'Data Issue':            (None, None, None),
}

STAGE_ORDER = {
    'Prospects': 1, 'Prospecting': 2, 'Engaged': 3, 'Proposal Sent': 4,
    'Contract Negotiations': 5, 'PAL/ROE Complete': 6, 'Under Contract': 6,
    'ROE Secured': 7, 'Ready for Engineering': 7, 'Marketing/Bulk In Progress': 7,
    'Under Construction': 8, 'Marketing/Bulk Complete': 8, 'Activation': 9, 'Closed Won': 10,
}
SECURED = {'PAL/ROE Complete', 'Under Contract', 'Closed Won', 'Marketing/Bulk Complete'}
MIDFLIGHT = {'Contract Negotiations', 'Marketing/Bulk In Progress'}

PUSH_CLASSES = {'no-change', 'advance', 'to-closed-lost', 'to-hold', 'activate-from-hold'}
QUARANTINE_CLASSES = {'reopen-needed', 'close-midflight', 'regress', 'reopen-from-closed',
                      'review', 'ambiguous-multi', 'dup-in-sf', 'unmatched', 'name-fuzzy'}

LOSS_KEYWORDS = [
    ('competitor', 'Lost to Competitor'), ('existing fiber', 'Existing Fiber'),
    ('has fiber', 'Existing Fiber'), ('cox', 'Existing Fiber'),
    ('exclusiv', 'Existing Contract'), ('existing contract', 'Existing Contract'),
    ('under contract', 'Existing Contract'), ('not interested', 'Not Interested'),
    ('no interest', 'Not Interested'), ('rejected', 'Rejected by Owner'),
    ('declined', 'Rejected by Owner'), ('budget', 'No Budget / Lost Funding'),
    ('funding', 'No Budget / Lost Funding'), ('price', 'Price'), ('cost', 'Price'),
    ('contact info', 'No Contact Info'), ('no contact', 'No Contact Info'),
    ("can't reach", 'No Contact Info'),
]

STOP = re.compile(r'\b(apartments?|apts?|the|at|of|mhp|llc|homes?|community|'
                  r'condos?|townhomes?|senior|housing|village|estates?)\b')


def norm(s):
    s = STOP.sub(' ', (s or '').lower())
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def st2(s):
    s = (s or '').strip().lower()
    return {'texas': 'tx', 'arizona': 'az', 'nebraska': 'ne', 'california': 'ca',
            'washington': 'wa'}.get(s, s[:2])


def derive_loss_reason(notes):
    t = (notes or '').lower()
    for kw, reason in LOSS_KEYWORDS:
        if kw in t:
            return reason
    return 'No Decision / Non-Responsive'


def target_for(saq_status, closed_notes):
    if saq_status not in STATUS_MAP:
        return (None, None, None)
    stage, rfield, fixed = STATUS_MAP[saq_status]
    if stage is None:
        return (None, None, None)
    if rfield == 'Loss_Reason__c':
        reason = fixed or derive_loss_reason(closed_notes)
    elif rfield == 'Hold_Reason__c':
        reason = fixed
    else:
        reason = None
    return (stage, rfield, reason)


def classify(current, target):
    if current == target:
        return 'no-change'
    if target == 'Closed Lost':
        if current in SECURED:
            return 'reopen-needed'
        if current in MIDFLIGHT:
            return 'close-midflight'
        return 'to-closed-lost'
    if target == 'On Hold':
        return 'to-hold'
    if current == 'Closed Lost':
        return 'reopen-from-closed'
    if current == 'On Hold':
        return 'activate-from-hold'
    co, to = STAGE_ORDER.get(current), STAGE_ORDER.get(target)
    if co is None or to is None:
        return 'review'
    return 'advance' if to > co else 'regress' if to < co else 'no-change'


def _selftest():
    assert target_for('Closed - Contact Info', 'x') == ('Closed Lost', 'Loss_Reason__c', 'No Contact Info')
    assert target_for('Closed - Lost', 'lost to competitor') == ('Closed Lost', 'Loss_Reason__c', 'Lost to Competitor')
    assert target_for('Closed - Lost', 'spinning wheels') == ('Closed Lost', 'Loss_Reason__c', 'No Decision / Non-Responsive')
    assert target_for('Proposal Review', '') == ('Contract Negotiations', None, None)
    assert target_for('Data Issue', '') == (None, None, None)
    assert classify('Engaged', 'Proposal Sent') == 'advance'
    assert classify('Proposal Sent', 'Engaged') == 'regress'
    assert classify('Contract Negotiations', 'Contract Negotiations') == 'no-change'
    assert classify('PAL/ROE Complete', 'Closed Lost') == 'reopen-needed'
    assert classify('Contract Negotiations', 'Closed Lost') == 'close-midflight'
    assert classify('Prospects', 'Closed Lost') == 'to-closed-lost'
    assert classify('Closed Lost', 'Engaged') == 'reopen-from-closed'


# --- io ------------------------------------------------------------------------

def load_sheet():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb['Opportunities']
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    h = rows[0]
    cols = ['Name', 'AgreeName', 'Units', 'State', 'City', 'SAQ Status',
            'Closed Date', 'Closed Bucket', 'Closed Notes']
    idx = {c: h.index(c) for c in cols}
    return [{c: r[i] for c, i in idx.items()}
            for r in rows[1:] if any(c is not None and str(c).strip() for c in r)]


def connect():
    creds = {}
    for line in open(CREDS, encoding='utf-8'):
        if ':' in line:
            k, v = line.split(':', 1)
            creds[k.strip()] = v.strip()
    return Salesforce(username=creds['Username'], password=creds['Password'],
                      security_token=creds['Security Token'])


def main():
    _selftest()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    today = dt.date(2026, 6, 24).isoformat()
    sheet = load_sheet()
    print(f'Sheet rows: {len(sheet)}')

    sf = connect()
    allopps = sf.query_all(
        "SELECT Id, Name, Agreement_Name__c, StageName, Owner.Name, RecordType.Name, "
        "Property_State_Display__c, Loss_Reason__c, Hold_Reason__c FROM Opportunity"
    )['records']
    print(f'SF Opps: {len(allopps)}')
    by_key, by_norm = defaultdict(list), defaultdict(list)
    for o in allopps:
        if o['Agreement_Name__c']:
            by_key[o['Agreement_Name__c']].append(o)
        nn = norm(o['Name'])
        if nn:
            by_norm[nn].append(o)

    def match(row):
        """Return (method, [opps], note)."""
        key = (row['AgreeName'] or '').strip() or None
        if key and key in by_key:
            opps = by_key[key]
            return ('key', opps, '') if len(opps) == 1 else ('key-multi', opps, 'key->multi')
        # name+state fallback
        nq = norm(row['Name'])
        rstate = st2(row['State'])
        exact = by_norm.get(nq, [])
        exact_state = [o for o in exact if st2(o.get('Property_State_Display__c')) == rstate]
        if len(exact) == 1:
            return ('name', exact, 'recovered (no/!key in sheet)')
        if len(exact_state) == 1:
            return ('name', exact_state, 'recovered via state')
        if len(exact) > 1:
            return ('dup', (exact_state or exact), 'multiple SF records')
        # fuzzy
        fz = sorted(((SequenceMatcher(None, nq, norm(o['Name'])).ratio(), o)
                     for o in allopps if st2(o.get('Property_State_Display__c')) == rstate),
                    key=lambda x: -x[0])
        if fz and fz[0][0] >= 0.86 and (len(fz) == 1 or fz[0][0] - fz[1][0] >= 0.06):
            return ('name-fuzzy', [fz[0][1]], f'fuzzy {fz[0][0]:.2f}')
        return ('none', [], 'no SF match')

    results = []
    for r in sheet:
        stage, rfield, rval = target_for(r['SAQ Status'], r['Closed Notes'])
        rec = {'sheet_name': r['Name'], 'agree_name': (r['AgreeName'] or '').strip(),
               'state': r['State'], 'units': r['Units'], 'saq_status': (r['SAQ Status'] or '').strip(),
               'target_stage': stage or '', 'reason_field': rfield or '', 'reason_value': rval or '',
               'closed_date': str(r['Closed Date'])[:10] if r['Closed Date'] else ''}
        if stage is None:
            rec.update(klass='data-issue-skip', match='skip', sf_id='', sf_name='',
                       owner='', current_stage='', note='Data Issue')
            results.append(rec)
            continue
        method, opps, note = match(r)
        if method in ('none',):
            rec.update(klass='unmatched', match=method, sf_id='', sf_name='', owner='',
                       current_stage='', note=note)
        elif method in ('dup', 'key-multi'):
            rec.update(klass='dup-in-sf', match=method,
                       sf_id=';'.join(o['Id'] for o in opps),
                       sf_name=' | '.join(o['Name'] for o in opps), owner='',
                       current_stage=' | '.join(o['StageName'] or '' for o in opps), note=note)
        else:
            o = opps[0]
            cur = o['StageName'] or ''
            rec.update(klass=classify(cur, stage), match=method, sf_id=o['Id'], sf_name=o['Name'],
                       owner=(o.get('Owner') or {}).get('Name', ''), current_stage=cur, note=note)
        results.append(rec)

    push = [r for r in results if r['klass'] in PUSH_CLASSES and r['klass'] != 'no-change']
    nochange = [r for r in results if r['klass'] == 'no-change']
    quarantine = [r for r in results if r['klass'] in QUARANTINE_CLASSES]
    skipped = [r for r in results if r['klass'] == 'data-issue-skip']

    cols = ['klass', 'match', 'state', 'sheet_name', 'agree_name', 'sf_name', 'owner', 'units',
            'saq_status', 'current_stage', 'target_stage', 'reason_field', 'reason_value',
            'closed_date', 'note', 'sf_id']

    def write_csv(path, rows):
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, '') for c in cols})

    write_csv(OUTDIR / f'push-{today}.csv', push)
    write_csv(OUTDIR / f'quarantine-{today}.csv', quarantine + skipped)
    write_csv(OUTDIR / f'all-{today}.csv', results)

    # markdown
    by_class = Counter(r['klass'] for r in results)
    name_recov = sum(1 for r in results if r['match'] in ('name', 'name-fuzzy'))
    md = [f'# Bill SAQ -> SF reconcile ({today})', '',
          f'{len(results)} sheet rows. PUSH={len(push)}  no-change={len(nochange)}  '
          f'QUARANTINE={len(quarantine)}  skip={len(skipped)}.  '
          f'Name-recovered matches folded in: {name_recov}.', '',
          '## Classes', '', '| Class | Count | Bucket |', '|---|---|---|']
    for cls, n in by_class.most_common():
        bucket = ('PUSH' if cls in PUSH_CLASSES and cls != 'no-change'
                  else 'no-change' if cls == 'no-change'
                  else 'skip' if cls == 'data-issue-skip' else 'QUARANTINE')
        md.append(f'| {cls} | {n} | {bucket} |')

    md += ['', '## QUARANTINE detail (not written)', '']
    for cls in ['reopen-needed', 'close-midflight', 'reopen-from-closed', 'regress',
                'dup-in-sf', 'unmatched', 'name-fuzzy', 'review', 'ambiguous-multi']:
        sel = [r for r in quarantine if r['klass'] == cls]
        if not sel:
            continue
        md.append(f'### {cls} ({len(sel)})')
        md.append('| State | Property | SAQ | SF now | -> Target | Owner | Note |')
        md.append('|---|---|---|---|---|---|---|')
        for r in sel:
            md.append(f"| {r['state']} | {r['sheet_name']} | {r['saq_status']} | "
                      f"{r['current_stage']} | {r['target_stage']} | {r['owner']} | {r['note']} |")
        md.append('')

    md += ['## PUSH summary by target stage', '',
           '| Target stage | Count |', '|---|---|']
    for stg, n in Counter(r['target_stage'] for r in push).most_common():
        md.append(f'| {stg} | {n} |')
    md += ['', '## PUSH: Closed Lost reasons', '', '| Loss Reason | Count |', '|---|---|']
    for rsn, n in Counter(r['reason_value'] for r in push
                          if r['target_stage'] == 'Closed Lost').most_common():
        md.append(f'| {rsn} | {n} |')

    (OUTDIR / f'reconcile-{today}.md').write_text('\n'.join(md), encoding='utf-8')

    print('\n=== CLASS COUNTS ===')
    for cls, n in by_class.most_common():
        print(f'  {n:5}  {cls}')
    print(f'\nPUSH={len(push)}  no-change={len(nochange)}  QUARANTINE={len(quarantine)}  '
          f'skip={len(skipped)}  name-recovered={name_recov}')
    print(f'Outputs in {OUTDIR}')


if __name__ == '__main__':
    main()
