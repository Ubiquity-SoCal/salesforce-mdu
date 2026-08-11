"""Verify the 8 original reports (post-deploy) run cleanly + have cross-filters."""
import json, requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])
host = sf.sf_instance
hdrs = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}

ORIGINALS = [
    ('00OWR00000ImYwH2AV', 'Cleanup_Under_Contract_No_PAL'),
    ('00OWR00000ImZE32AN', 'Cleanup_Opps_No_Projected_Close'),
    ('00OWR00000ImZE52AN', 'Cleanup_Stale_Active_Opps'),
    ('00OWR00000ImZE22AN', 'Cleanup_Opps_Need_IC_ID_Signed'),
    ('00OWR00000ImZE42AN', 'Cleanup_Opps_No_RE_Assigned'),
    ('00OWR00000InCk12AF', 'Cleanup_Stale_EMA_Bulk_Opps'),
    ('00OWR00000ImZE12AN', 'Cleanup_Opps_Need_IC_ID_OutForSign'),
    ('00OWR00000ImYRd2AN', 'Cleanup_Opps_No_Property_Location'),
]

for rid, dev in ORIGINALS:
    print(f'\n=== {rid}  {dev} ===')
    desc = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{rid}/describe', headers=hdrs).json()
    meta = desc['reportMetadata']
    print(f'  name={meta.get("name")!r}')
    cf = meta.get('crossFilters', [])
    print(f'  crossFilters: {len(cf)}')
    for x in cf:
        print(f"    relatedTable={x.get('relatedTable')}  ops:")
        for c in x.get('criteriaItems', []):
            print(f"      {c.get('column')} {c.get('operator')} {c.get('value')!r}")
    for f in meta.get('reportFilters', []):
        print(f'  filter: {f.get("column")} {f.get("operator")} {f.get("value")!r}')
    run = requests.get(f'https://{host}/services/data/v59.0/analytics/reports/{rid}', headers=hdrs)
    print(f'  run: {run.status_code}')
    if run.status_code == 200:
        body = run.json()
        rows = body.get('factMap',{}).get('T!T',{}).get('aggregates',[{}])[0].get('value')
        print(f'    rows: {rows}')
    else:
        print(f'    ERR {run.text[:300]}')
