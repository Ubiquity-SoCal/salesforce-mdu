"""Diagnose the cleanup dashboard cloned reports - try running each, show metadata health."""
import json, requests, sys
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
host = sf.sf_instance
hdrs = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

NEW_REPORT_IDS = [
    ('00OWR00000IuGhF2AV', 'Cleanup: PAL/ROE Complete: No PAL'),
    ('00OWR00000IuGir2AF', 'Cleanup: No Projected Close Date'),
    ('00OWR00000IuGkT2AV', 'Cleanup: Stale Active Opps (60+ days)'),
    ('00OWR00000IuGm52AF', 'Cleanup: Need IronClad ID (Signed)'),
    ('00OWR00000IuGnh2AF', 'Cleanup: No RE Assigned'),
    ('00OWR00000IuGqv2AF', 'Cleanup: Stale EMA/Bulk on wrong stage'),
    ('00OWR00000IuGu92AF', 'Cleanup: Need IC ID (Out for Sign)'),
    ('00OWR00000IuGxN2AV', 'Cleanup: No Property Location'),
]

for rid, label in NEW_REPORT_IDS:
    print(f'\n=== {rid}  {label} ===')

    # 1. Describe (metadata)
    desc = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{rid}/describe', headers=hdrs)
    print(f'  describe: {desc.status_code}')
    if desc.status_code != 200:
        print(f'    ERR {desc.text[:300]}')
        continue
    meta = desc.json()['reportMetadata']
    print(f'    name={meta.get("name")}  devName={meta.get("developerName")}')
    print(f'    reportType={meta.get("reportType",{}).get("type")}')
    filters = meta.get('reportFilters', [])
    for f in filters:
        print(f'    filter: {f.get("column")} {f.get("operator")} {repr(f.get("value"))[:120]}')

    # 2. Try to RUN it via GET (sync execution)
    run = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{rid}?includeDetails=true', headers=hdrs)
    print(f'  run: {run.status_code}')
    if run.status_code != 200:
        print(f'    ERR {run.text[:600]}')
    else:
        body = run.json()
        att = body.get('attributes', {})
        fact = body.get('factMap', {})
        rows = fact.get('T!T', {}).get('aggregates', [{}])[0].get('value') if 'T!T' in fact else None
        print(f'    rows: {rows}  status={att.get("status")}')
