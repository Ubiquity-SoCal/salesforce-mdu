"""Build the full import plan: note inserts + CloseDate updates.
Previews current vs new values before user approves execution.
"""
import pandas as pd, json
from datetime import datetime, timedelta
from pathlib import Path
from simple_salesforce import Salesforce

TRACKER = r'C:\Users\cass\OneDrive - Ubiquity Management\Desktop\MDU Projects - Weekly Tracker (1).xlsb'
OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

# Manual overrides from user decisions
# - Bridgeport Dry Creek HOA: skip
# - Woodglen Square Condo II: -> 006WR00000wkDtwYAE
# - Deerfield Apartments: -> 006WR000011aP8ZYAU
OVERRIDES_BY_SITE_NAME = {
    'Mesa_MDU_Woodglen Square Condo II': '006WR00000wkDtwYAE',
    'Deerfield Apartments': '006WR000011aP8ZYAU',
}
SKIP_SITES = {'Bridgeport_MDU_Dry Creek HOA'}

# Load match results and rebuild the full row->Opp map
match = json.load(open(OUT / 'match_results.json'))
row_map = {}
for r in match['matched_by_project_id']:
    row_map[(r.get('project_id'), r['site_name'])] = r
for r in match['matched_by_name']:
    row_map[(r.get('project_id'), r['site_name'])] = r

# Re-apply user decisions over top of auto-matches
def to_date(v):
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(v))).date().isoformat()
    return str(v)

df = pd.read_excel(TRACKER, sheet_name='Sales Pipeline', engine='pyxlsb')
df.columns = [c.strip() for c in df.columns]

plan = []
for _, row in df.iterrows():
    sn = row['Site Name']
    if pd.isna(sn):
        continue
    if sn in SKIP_SITES:
        continue
    pid = row['Project ID'] if pd.notna(row['Project ID']) else None
    matched = row_map.get((pid, sn))
    opp_id = None
    opp_name = None
    if sn in OVERRIDES_BY_SITE_NAME:
        opp_id = OVERRIDES_BY_SITE_NAME[sn]
    elif matched:
        opp_id = matched.get('opp_id')
        opp_name = matched.get('opp_name')
    if not opp_id:
        continue

    plan.append({
        'opp_id': opp_id,
        'opp_name': opp_name,
        'site_name': sn,
        'project_id': pid,
        'state_tracker': row['State'] if pd.notna(row['State']) else None,
        'owner_tracker': row['Owner'] if pd.notna(row['Owner']) else None,
        'status': row['Status'] if pd.notna(row['Status']) else None,
        'notes': row['Notes'] if pd.notna(row['Notes']) else None,
        'target_close_date': to_date(row['Target Close Date']),
    })

# Fetch current CloseDate + Opp names for all targets
ids = list({p['opp_id'] for p in plan})
id_list = "','".join(ids)
q = f"SELECT Id, Name, CloseDate, StageName, Owner.Name FROM Opportunity WHERE Id IN ('{id_list}')"
res = sf.query_all(q)
current = {r['Id']: r for r in res['records']}

note_imports = []
date_updates = []
for p in plan:
    cur = current.get(p['opp_id'])
    if cur:
        p['opp_name'] = cur['Name']
        p['current_close_date'] = cur.get('CloseDate')
        p['current_stage'] = cur.get('StageName')
        p['current_owner'] = (cur.get('Owner') or {}).get('Name')
    if p['notes']:
        note_imports.append(p)
    if p['target_close_date'] and p['target_close_date'] != p.get('current_close_date'):
        date_updates.append(p)

# Also drop the Laredo dup (detected earlier)
laredo = [p for p in note_imports if p['site_name'].endswith('Laredo Apartments')]
for p in laredo:
    p['skip_note_reason'] = 'likely dup of existing Brett Spivey note'
note_imports = [p for p in note_imports if 'skip_note_reason' not in p]

(OUT / 'final_plan.json').write_text(json.dumps({
    'note_imports': note_imports,
    'date_updates': date_updates,
    'skipped_note_dups': laredo,
}, indent=2, default=str))

print(f'Notes to import: {len(note_imports)}')
print(f'CloseDate updates: {len(date_updates)}')
print(f'Skipped note dups: {len(laredo)}')
print()
print('=== CloseDate updates preview ===')
for p in date_updates:
    print(f"  {p['opp_name']}  ({p['state_tracker']}) : {p.get('current_close_date')} -> {p['target_close_date']}")
