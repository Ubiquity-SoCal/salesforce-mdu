"""Populate Opportunity.Latest_Note_Date__c and Opportunity.Latest_Note_Snippet__c
from the most recent ContentNote linked to each MDU/Business Opp.

Format of Latest_Note_Snippet__c:
    [YYYY-MM-DD] Title — first ~4000 chars of plain-text body

Run modes:
    python sync_latest_note.py              # all open MDU + Business_ROE Opps
    python sync_latest_note.py --all-rt     # every Opp regardless of RT
    python sync_latest_note.py --opp-id 006WR00000xxx  # single Opp (debug)
"""
import argparse
import re
from html import unescape
from datetime import datetime, timezone
from simple_salesforce import Salesforce
from collections import defaultdict

import os as _os


def _sf_creds():
    """Credentials live in the gitignored SalesForce/api/ creds file.
    Never hardcode the password here: this file is tracked in git."""
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       "..", "..", "api", "Salesforce_Credentials.txt")
    _c = {}
    with open(_p) as _f:
        for _line in _f:
            if ":" in _line:
                _k, _v = _line.split(":", 1)
                _c[_k.strip()] = _v.strip()
    return _c


_SF = _sf_creds()
SF_USER = _SF["Username"]
SF_PASS = _SF["Password"]
SF_TOKEN = _SF["Security Token"]

SNIPPET_MAX = 4500          # leave headroom under 5000-char field cap
BODY_EXCERPT_MAX = 4000     # max body chars in snippet

TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')

def html_to_text(html):
    if not html:
        return ''
    txt = TAG_RE.sub(' ', html)
    txt = unescape(txt)
    txt = WS_RE.sub(' ', txt).strip()
    return txt

def build_snippet(date_iso, title, body_text):
    date_short = (date_iso or '')[:10]
    title = (title or '').strip() or '(untitled)'
    body = (body_text or '').strip()
    if len(body) > BODY_EXCERPT_MAX:
        body = body[:BODY_EXCERPT_MAX].rstrip() + '...'
    snippet = f'[{date_short}] {title} - {body}' if body else f'[{date_short}] {title}'
    if len(snippet) > SNIPPET_MAX:
        snippet = snippet[:SNIPPET_MAX].rstrip() + '...'
    return snippet

def fetch_opps(sf, args):
    where = []
    if args.opp_id:
        where.append(f"Id = '{args.opp_id}'")
    elif not args.all_rt:
        rt_q = sf.query("""
            SELECT Id FROM RecordType
            WHERE SobjectType='Opportunity'
              AND DeveloperName IN ('MDU','Business','Business_ROE')
        """)
        rt_ids = [r['Id'] for r in rt_q['records']]
        rt_in = "','".join(rt_ids)
        where.append(f"RecordTypeId IN ('{rt_in}')")
    soql = "SELECT Id, Name, Latest_Note_Date__c, Latest_Note_Snippet__c FROM Opportunity"
    if where:
        soql += ' WHERE ' + ' AND '.join(where)
    return sf.query_all(soql)['records']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all-rt', action='store_true')
    ap.add_argument('--opp-id', help='Single Opportunity Id (debug)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    sf = Salesforce(username=SF_USER, password=SF_PASS, security_token=SF_TOKEN)

    opps = fetch_opps(sf, args)
    print(f"Opps to scan: {len(opps)}")
    opp_ids = [o['Id'] for o in opps]

    # Pull ContentDocumentLinks for these opps -> ContentNote (only Notes, not files)
    notes_by_opp = defaultdict(list)
    BATCH = 200
    for i in range(0, len(opp_ids), BATCH):
        chunk = opp_ids[i:i+BATCH]
        ids_str = "','".join(chunk)
        cdl_q = sf.query_all(f"""
            SELECT LinkedEntityId, ContentDocumentId,
                   ContentDocument.LatestPublishedVersion.FileType,
                   ContentDocument.LatestPublishedVersion.Id,
                   ContentDocument.LatestPublishedVersion.Title,
                   ContentDocument.LatestPublishedVersion.LastModifiedDate,
                   ContentDocument.LatestPublishedVersion.CreatedDate
            FROM ContentDocumentLink
            WHERE LinkedEntityId IN ('{ids_str}')
        """)
        for r in cdl_q['records']:
            ft = r['ContentDocument']['LatestPublishedVersion']['FileType']
            if ft != 'SNOTE':
                continue
            notes_by_opp[r['LinkedEntityId']].append({
                'cv_id': r['ContentDocument']['LatestPublishedVersion']['Id'],
                'title': r['ContentDocument']['LatestPublishedVersion']['Title'],
                'last_mod': r['ContentDocument']['LatestPublishedVersion']['LastModifiedDate'],
                'created': r['ContentDocument']['LatestPublishedVersion']['CreatedDate'],
            })

    # Resolve ContentNote bodies for the latest per opp
    latest_per_opp = {}
    cv_ids = []
    for opp_id, notes in notes_by_opp.items():
        if not notes:
            continue
        latest = max(notes, key=lambda n: n['last_mod'])
        latest_per_opp[opp_id] = latest
        cv_ids.append(latest['cv_id'])

    # Fetch each ContentVersion's VersionData URL to get the actual HTML body. TextPreview as fallback.
    bodies = {}
    if cv_ids:
        # Pull TextPreview as cheap fallback in case VersionData fetch fails
        for i in range(0, len(cv_ids), 200):
            chunk = cv_ids[i:i+200]
            ids_str = "','".join(chunk)
            cv_q = sf.query_all(f"""
                SELECT Id, ContentDocumentId, TextPreview
                FROM ContentVersion WHERE Id IN ('{ids_str}')
            """)
            for r in cv_q['records']:
                bodies[r['Id']] = {'preview': r.get('TextPreview') or '', 'html': ''}

        # Fetch VersionData (HTML) in parallel
        import requests
        from concurrent.futures import ThreadPoolExecutor, as_completed
        headers = {'Authorization': f'Bearer {sf.session_id}'}
        def fetch_body(cv_id):
            url = f'{sf.base_url}sobjects/ContentVersion/{cv_id}/VersionData'
            try:
                r = requests.get(url, headers=headers, timeout=30)
                if r.status_code == 200:
                    return cv_id, r.content.decode('utf-8', errors='replace')
            except Exception as e:
                return cv_id, None
            return cv_id, None
        print(f"Fetching {len(cv_ids)} note bodies via VersionData...")
        done = 0
        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = {ex.submit(fetch_body, cv_id): cv_id for cv_id in cv_ids}
            for fut in as_completed(futures):
                cv_id, html = fut.result()
                if cv_id in bodies and html is not None:
                    bodies[cv_id]['html'] = html
                done += 1
                if done % 500 == 0:
                    print(f"  fetched {done}/{len(cv_ids)}")
        print(f"  fetched {done}/{len(cv_ids)}")

    updates = []
    cleared = 0
    for o in opps:
        opp_id = o['Id']
        latest = latest_per_opp.get(opp_id)
        if not latest:
            # Clear any stale value
            if o.get('Latest_Note_Date__c') or o.get('Latest_Note_Snippet__c'):
                updates.append({'Id': opp_id, 'Latest_Note_Date__c': None, 'Latest_Note_Snippet__c': None})
                cleared += 1
            continue
        body_info = bodies.get(latest['cv_id'], {})
        html = body_info.get('html', '')
        text = html_to_text(html) if html else (body_info.get('preview') or '')
        snippet = build_snippet(latest['last_mod'], latest['title'], text)

        # Skip update if no change
        if (o.get('Latest_Note_Date__c') == latest['last_mod']
            and (o.get('Latest_Note_Snippet__c') or '') == snippet):
            continue
        updates.append({
            'Id': opp_id,
            'Latest_Note_Date__c': latest['last_mod'],
            'Latest_Note_Snippet__c': snippet,
        })

    print(f"Opps with notes: {len(latest_per_opp)}")
    print(f"Updates queued: {len(updates)}  (clears: {cleared})")

    if args.dry_run:
        for u in updates[:10]:
            print(f"  {u['Id']} -> {u.get('Latest_Note_Snippet__c','(clear)')[:120]!r}")
        return

    if not updates:
        print("Nothing to update.")
        return

    # Use REST composite API (sObject Collections) for fast batch updates: 200 records per call, synchronous
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    headers = {
        'Authorization': f'Bearer {sf.session_id}',
        'Content-Type': 'application/json',
    }
    composite_url = f'{sf.base_url}composite/sobjects'

    def push_batch(chunk):
        records = [{'attributes': {'type': 'Opportunity'}, **r} for r in chunk]
        body = {'allOrNone': False, 'records': records}
        r = requests.patch(composite_url, headers=headers, json=body, timeout=120)
        return r.status_code, r.json() if r.text else []

    BATCH_UPDATE = 200
    chunks = [updates[i:i+BATCH_UPDATE] for i in range(0, len(updates), BATCH_UPDATE)]
    print(f"Pushing {len(chunks)} batches of up to {BATCH_UPDATE} records via composite API...", flush=True)
    success = 0
    errors = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(push_batch, c): c for c in chunks}
        done = 0
        for fut in as_completed(futures):
            status, results = fut.result()
            chunk = futures[fut]
            if status != 200:
                errors.append(('batch', f'HTTP {status}: {results}'))
                continue
            for u, r in zip(chunk, results):
                if r.get('success'):
                    success += 1
                else:
                    errors.append((u['Id'], r.get('errors')))
            done += 1
            print(f"  pushed batch {done}/{len(chunks)} (success so far: {success})", flush=True)
    print(f"Updated: {success}  Errors: {len(errors)}", flush=True)
    for opp_id, err in errors[:10]:
        print(f"  ! {opp_id}: {err}", flush=True)

if __name__ == '__main__':
    main()
