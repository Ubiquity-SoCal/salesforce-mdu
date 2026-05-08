"""Match MDU Weekly Tracker rows to Salesforce Opps and preview note import."""
import pandas as pd
import json
from simple_salesforce import Salesforce
from pathlib import Path

TRACKER = r'C:\Users\cass\OneDrive - Ubiquity Management\Desktop\MDU Projects - Weekly Tracker (1).xlsb'
OUT_DIR = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
OUT_DIR.mkdir(exist_ok=True)

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()

sf = Salesforce(
    username=creds['Username'],
    password=creds['Password'],
    security_token=creds['Security Token'],
)

df = pd.read_excel(TRACKER, sheet_name='Sales Pipeline', engine='pyxlsb')
df.columns = [c.strip() for c in df.columns]
print(f'Loaded {len(df)} tracker rows')

with_pid = df[df['Project ID'].notna()].copy()
without_pid = df[df['Project ID'].isna()].copy()
print(f'  {len(with_pid)} with Project ID, {len(without_pid)} without')

pids = sorted(with_pid['Project ID'].unique().tolist())
pid_list = "','".join(pids)
q = f"""
    SELECT Id, Name, Opportunity__c, Opportunity__r.Id, Opportunity__r.Name, Opportunity__r.StageName
    FROM SiteTracker_Project__c
    WHERE Name IN ('{pid_list}')
"""
st = sf.query_all(q)
st_rows = st['records']
print(f'\nSiteTracker_Project__c matches: {len(st_rows)} / {len(pids)}')

pid_to_opp = {}
for r in st_rows:
    pid = r['Name']
    opp = r.get('Opportunity__r')
    if opp:
        pid_to_opp[pid] = {'opp_id': opp['Id'], 'opp_name': opp['Name'], 'stage': opp.get('StageName')}
    else:
        pid_to_opp[pid] = None

matched_pid_rows = []
unmatched_pid_rows = []
for _, row in with_pid.iterrows():
    pid = row['Project ID']
    mapping = pid_to_opp.get(pid)
    rec = {
        'project_id': pid,
        'site_name': row['Site Name'],
        'state': row['State'],
        'owner_tracker': row['Owner'],
        'status': row['Status'],
        'notes': row['Notes'] if pd.notna(row['Notes']) else None,
    }
    if mapping:
        rec.update({'opp_id': mapping['opp_id'], 'opp_name': mapping['opp_name'], 'stage': mapping['stage']})
        matched_pid_rows.append(rec)
    else:
        unmatched_pid_rows.append(rec)

print(f'  Opp-linked: {len(matched_pid_rows)}  /  no Opp link or no ST record: {len(unmatched_pid_rows)}')

site_names = without_pid['Site Name'].dropna().unique().tolist()

def extract_property(sn):
    if '_MDU_' in sn:
        return sn.split('_MDU_', 1)[1].strip()
    if '_SFU_' in sn:
        return sn.split('_SFU_', 1)[1].strip()
    return sn.strip()

property_terms = [extract_property(s) for s in site_names]
print(f'\nLooking up {len(site_names)} sites by name...')
print('  Sample property terms:', property_terms[:5])

def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")

name_matches = {}
for orig, term in zip(site_names, property_terms):
    search_term = term.split(',')[0].split('(')[0].strip()
    if len(search_term) < 4:
        name_matches[orig] = []
        continue
    q = f"""
        SELECT Id, Name, StageName, Agreement_Name__c, RecordType.Name
        FROM Opportunity
        WHERE Name LIKE '%{esc(search_term)}%'
           OR Agreement_Name__c LIKE '%{esc(search_term)}%'
    """
    try:
        r = sf.query_all(q)
        name_matches[orig] = r['records']
    except Exception as e:
        print(f'  Query error for {search_term!r}: {e}')
        name_matches[orig] = []

matched_name_rows = []
unmatched_name_rows = []
ambiguous_name_rows = []
for _, row in without_pid.iterrows():
    sn = row['Site Name']
    if pd.isna(sn):
        continue
    hits = name_matches.get(sn, [])
    rec = {
        'project_id': None,
        'site_name': sn,
        'state': row['State'],
        'owner_tracker': row['Owner'] if pd.notna(row['Owner']) else None,
        'status': row['Status'],
        'notes': row['Notes'] if pd.notna(row['Notes']) else None,
    }
    if len(hits) == 0:
        unmatched_name_rows.append(rec)
    elif len(hits) == 1:
        h = hits[0]
        rec.update({'opp_id': h['Id'], 'opp_name': h['Name'], 'stage': h['StageName'], 'agreement_name': h.get('Agreement_Name__c')})
        matched_name_rows.append(rec)
    else:
        rec['candidates'] = [{'id': h['Id'], 'name': h['Name'], 'stage': h['StageName'], 'agreement_name': h.get('Agreement_Name__c')} for h in hits]
        ambiguous_name_rows.append(rec)

print(f'\nName match results:')
print(f'  single match: {len(matched_name_rows)}')
print(f'  ambiguous (>1 hit): {len(ambiguous_name_rows)}')
print(f'  no match: {len(unmatched_name_rows)}')

out = {
    'matched_by_project_id': matched_pid_rows,
    'unmatched_by_project_id': unmatched_pid_rows,
    'matched_by_name': matched_name_rows,
    'ambiguous_by_name': ambiguous_name_rows,
    'unmatched_by_name': unmatched_name_rows,
}
(OUT_DIR / 'match_results.json').write_text(json.dumps(out, indent=2, default=str))
print(f'\nWrote {OUT_DIR / "match_results.json"}')

print('\n' + '='*60)
print('SUMMARY')
print('='*60)
total_matched = len(matched_pid_rows) + len(matched_name_rows)
total_ambig = len(ambiguous_name_rows)
total_unmatched = len(unmatched_pid_rows) + len(unmatched_name_rows)
print(f'  matched (ready to import): {total_matched}')
print(f'  ambiguous (need manual pick): {total_ambig}')
print(f'  unmatched (no SF Opp found): {total_unmatched}')
print(f'  total rows: {len(df)}')
