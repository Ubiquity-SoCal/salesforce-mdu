"""Resolve ambiguous matches + retry unmatched with fuzzier searches."""
import json
from simple_salesforce import Salesforce
from pathlib import Path

OUT = Path(r'C:\Users\cass\Work_Projects\SalesForce\weekly_tracker_import')
d = json.load(open(OUT / 'match_results.json'))

creds = {}
for line in open(r'C:\Users\cass\Work_Projects\SalesForce\Salesforce_Credentials.txt'):
    if ':' in line:
        k, v = line.split(':', 1)
        creds[k.strip()] = v.strip()
sf = Salesforce(username=creds['Username'], password=creds['Password'], security_token=creds['Security Token'])

for r in d['ambiguous_by_name']:
    sn = r['site_name']
    extract = sn.split('_MDU_', 1)[1] if '_MDU_' in sn else sn
    best = None
    for c in r['candidates']:
        if c.get('agreement_name') == sn:
            best = c
            break
    if not best:
        for c in r['candidates']:
            if c['name'] == sn:
                best = c
                break
    if not best:
        best = r['candidates'][0]
    rec = {k: v for k, v in r.items() if k != 'candidates'}
    rec.update({'opp_id': best['id'], 'opp_name': best['name'], 'stage': best['stage'], 'agreement_name': best.get('agreement_name')})
    d['matched_by_name'].append(rec)
    print(f"resolved: {sn} -> {best['name']} ({best['id']})")

d['ambiguous_by_name'] = []

print()
print('Retrying unmatched with fuzzier search...')
retry_terms = {
    'Bridgeport_MDU_Dry Creek HOA': ['Dry Creek'],
    'Mesa_MDU_Woodglen Square Condo II': ['Woodglen'],
    'Deerfield Apartments': ['Deerfield'],
}

still_unmatched = []
for r in d['unmatched_by_name']:
    sn = r['site_name']
    terms = retry_terms.get(sn, [sn.split('_MDU_', 1)[1] if '_MDU_' in sn else sn])
    hits = []
    for t in terms:
        q = f"SELECT Id, Name, StageName, Agreement_Name__c FROM Opportunity WHERE Name LIKE '%{t}%' OR Agreement_Name__c LIKE '%{t}%'"
        res = sf.query_all(q)
        hits.extend(res['records'])
    dedup = {h['Id']: h for h in hits}.values()
    print(f"\n  {sn} -> {len(dedup)} hits")
    for h in dedup:
        print(f"    - {h['Name']}  |  stage={h['StageName']}  |  agreement={h.get('Agreement_Name__c')}  |  {h['Id']}")
    if len(dedup) == 1:
        h = list(dedup)[0]
        rec = dict(r)
        rec.update({'opp_id': h['Id'], 'opp_name': h['Name'], 'stage': h['StageName'], 'agreement_name': h.get('Agreement_Name__c')})
        d['matched_by_name'].append(rec)
        print(f"    -> auto-matched")
    else:
        r['retry_candidates'] = [{'id': h['Id'], 'name': h['Name'], 'stage': h['StageName'], 'agreement_name': h.get('Agreement_Name__c')} for h in dedup]
        still_unmatched.append(r)

d['unmatched_by_name'] = still_unmatched
(OUT / 'match_results.json').write_text(json.dumps(d, indent=2, default=str))

total_matched = len(d['matched_by_project_id']) + len(d['matched_by_name'])
print(f'\n=== FINAL ===')
print(f'  matched: {total_matched}')
print(f'  unmatched: {len(d["unmatched_by_name"])}')
