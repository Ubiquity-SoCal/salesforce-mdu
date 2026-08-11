"""Phase B: apply Bill's SAQ -> SF stage push set to the prod org.

Reads the approved push CSV from the reconcile, re-fetches authoritative current
values, computes minimal field diffs, and (with --apply) writes them with a full
audit log. Quarantine rows are NOT in the push CSV and are never touched here.

Safety:
  - dry-run by default; --apply to commit; --limit N for a canary batch.
  - re-reads live values (never trusts the CSV snapshot); skips already-current rows.
  - clears Sales_Status__c when advancing past Engaged (Sales_Status_Stage_Scope rule).
  - On Hold rows get Hold_Reason = 'Other' when the sheet gives none (validation safety).
  - per-row try/except: a validation failure logs and continues, never aborts the batch.

Spec: SalesForce/docs/superpowers/specs/2026-06-24-bill-saq-status-sf-sync-design.md
"""
import argparse
import csv
import datetime as dt
from pathlib import Path

from simple_salesforce import Salesforce

OUTDIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\data\output\bill-saq-reconcile')
PUSH_CSV = OUTDIR / 'push-2026-06-24.csv'
CREDS = r'C:\Users\cass\Work_Projects\SalesForce\api\Salesforce_Credentials.txt'
AUDIT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\data\output\audit_logs')

SALES_STATUS_OK = {'Prospects', 'Prospecting', 'Engaged'}  # stages where Sales_Status may stay


def connect():
    creds = {}
    for line in open(CREDS, encoding='utf-8'):
        if ':' in line:
            k, v = line.split(':', 1)
            creds[k.strip()] = v.strip()
    return Salesforce(username=creds['Username'], password=creds['Password'],
                      security_token=creds['Security Token'])


def plan_changes(row, cur):
    """Return dict of {field: new_value} (minimal diff) for one push row."""
    changes = {}
    target = row['target_stage']
    if (cur.get('StageName') or '') != target:
        changes['StageName'] = target
    if target == 'Closed Lost':
        rv = row['reason_value'] or 'No Decision / Non-Responsive'
        if (cur.get('Loss_Reason__c') or '') != rv:
            changes['Loss_Reason__c'] = rv
        cd = row['closed_date']
        if cd and (str(cur.get('CloseDate') or '')[:10]) != cd:
            changes['CloseDate'] = cd
    if target == 'On Hold':
        hr = row['reason_value'] or 'Other'
        if (cur.get('Hold_Reason__c') or '') != hr:
            changes['Hold_Reason__c'] = hr
    # clear Sales Status if advancing past the allowed stages (validation rule)
    if target not in SALES_STATUS_OK and (cur.get('Sales_Status__c') or ''):
        changes['Sales_Status__c'] = None
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='commit to the org (default: dry-run)')
    ap.add_argument('--limit', type=int, default=0, help='process only first N rows (canary)')
    args = ap.parse_args()

    rows = list(csv.DictReader(open(PUSH_CSV, encoding='utf-8-sig')))
    rows = [r for r in rows if r.get('sf_id')]
    if args.limit:
        rows = rows[:args.limit]
    print(f'Push rows: {len(rows)}  mode: {"APPLY" if args.apply else "DRY-RUN"}')

    sf = connect()
    ids = [r['sf_id'] for r in rows]
    cur_by_id = {}
    for i in range(0, len(ids), 200):
        batch = ids[i:i + 200]
        q = ("SELECT Id, Name, StageName, Sales_Status__c, Loss_Reason__c, Hold_Reason__c, "
             "CloseDate FROM Opportunity WHERE Id IN ('" + "','".join(batch) + "')")
        for rec in sf.query_all(q)['records']:
            cur_by_id[rec['Id']] = rec

    planned, skipped, missing = [], 0, 0
    for r in rows:
        cur = cur_by_id.get(r['sf_id'])
        if cur is None:
            missing += 1
            continue
        ch = plan_changes(r, cur)
        if not ch:
            skipped += 1
            continue
        planned.append((r, cur, ch))

    # summary
    from collections import Counter
    stg = Counter(r['target_stage'] for r, _, _ in planned)
    clears = sum(1 for _, _, ch in planned if 'Sales_Status__c' in ch)
    print(f'To write: {len(planned)}   already-current: {skipped}   missing-in-SF: {missing}')
    print(f'Sales_Status clears bundled: {clears}')
    for s, n in stg.most_common():
        print(f'   {n:4}  -> {s}')

    ts = dt.datetime.now().isoformat(timespec='seconds')
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = AUDIT_DIR / f'2026-06-24_bill_saq_status_push{"" if args.apply else "_DRYRUN"}.csv'
    afields = ['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action']
    ok = fail = 0
    with audit_path.open('w', newline='', encoding='utf-8-sig') as af:
        aw = csv.DictWriter(af, fieldnames=afields)
        aw.writeheader()
        for r, cur, ch in planned:
            action = 'DRY-RUN'
            if args.apply:
                try:
                    sf.Opportunity.update(r['sf_id'], ch)
                    action = 'UPDATED'
                    ok += 1
                except Exception as e:
                    action = 'FAIL: ' + str(e)[:160]
                    fail += 1
            for field, after in ch.items():
                aw.writerow({
                    'SF_Id': r['sf_id'], 'Name': cur.get('Name', ''), 'Field': field,
                    'Before': cur.get(field, ''), 'After': '' if after is None else after,
                    'Source': 'Bill Master List MDU Assignments.xlsm', 'Timestamp': ts,
                    'Action': action,
                })

    print(f'\nAudit log: {audit_path}')
    if args.apply:
        print(f'APPLIED: {ok} ok, {fail} failed')
    else:
        print('DRY-RUN only. Re-run with --apply (optionally --limit 5 first) to commit.')


if __name__ == '__main__':
    main()
