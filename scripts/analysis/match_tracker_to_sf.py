"""
Match weekly tracker properties to SF Opps by name (fuzzy).
Output: matched / unmatched lists, plus current SF Projected_Close_Date / Next_Action / Stage.
"""
import json, csv, re
from difflib import SequenceMatcher
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

tracker = json.load(open('weekly_tracker_parsed.json'))

# Get all MDU + Business_ROE Opps
rt_q = sf.query("SELECT Id, DeveloperName FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName IN ('MDU','Business_ROE','Business')")
rt_map = {r['Id']: r['DeveloperName'] for r in rt_q['records']}
rt_ids = list(rt_map.keys())
in_clause = "','".join(rt_ids)

opps_q = sf.query_all(f"""
    SELECT Id, Name, RecordTypeId, StageName, Projected_Close_Date__c,
           Next_Action__c, Next_Action_Date__c, Owner.Name, Property_City__c, Property_State__c
    FROM Opportunity
    WHERE RecordTypeId IN ('{in_clause}') AND IsClosed = false
""")
opps = opps_q['records']
print(f"Open SF Opps: {len(opps)}")

def normalize(s):
    if not s: return ''
    s = s.lower()
    s = re.sub(r'_mdu_|_sfu_', ' ', s)
    s = re.sub(r'\b(apartments?|apts?|condos?|condominiums?|townho?mes?|townhouses?|homes?|hoa|llc|inc)\b', '', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# Build lookup by normalized name
opp_norm = [(o, normalize(o['Name'])) for o in opps]

def best_match(query_name, threshold=0.6):
    nq = normalize(query_name)
    if not nq: return None, 0
    best = None
    best_score = 0
    for o, no in opp_norm:
        # Token overlap + sequence ratio
        q_tokens = set(nq.split())
        o_tokens = set(no.split())
        if not q_tokens or not o_tokens: continue
        # require at least one overlapping token of length>=4 to avoid noise
        overlap = q_tokens & o_tokens
        meaningful = [t for t in overlap if len(t) >= 4]
        if not meaningful: continue
        score = SequenceMatcher(None, nq, no).ratio()
        # boost score by overlap fraction
        score = (score + len(overlap) / max(len(q_tokens), len(o_tokens))) / 2
        if score > best_score:
            best_score = score
            best = o
    return (best, best_score) if best_score >= threshold else (None, best_score)

results = []
unmatched = []
for row in tracker:
    site = row.get('Site Name') or ''
    if not site: continue
    match, score = best_match(site)
    if match:
        results.append({
            'tracker_site': site,
            'tracker_owner': row.get('Owner') or '',
            'tracker_target': row.get('Target Close Date') or '',
            'tracker_status': row.get('Status') or '',
            'tracker_units': row.get('Total Units') or '',
            'sf_id': match['Id'],
            'sf_name': match['Name'],
            'sf_owner': match['Owner']['Name'],
            'sf_rt': rt_map.get(match['RecordTypeId'], ''),
            'sf_stage': match['StageName'],
            'sf_proj_close': match.get('Projected_Close_Date__c') or '',
            'sf_next_action': match.get('Next_Action__c') or '',
            'sf_next_action_date': match.get('Next_Action_Date__c') or '',
            'match_score': round(score, 3),
        })
    else:
        unmatched.append({
            'tracker_site': site,
            'tracker_owner': row.get('Owner') or '',
            'best_score': round(score, 3),
        })

print(f"\nMatched: {len(results)}")
print(f"Unmatched: {len(unmatched)}\n")

print("=== UNMATCHED ===")
for u in unmatched:
    print(f"  [{u['tracker_owner']:10s}] {u['tracker_site']:55s} score={u['best_score']}")

print("\n=== MATCHED (full) ===")
for r in sorted(results, key=lambda x: x['tracker_owner']):
    print(f"  [{r['tracker_owner']:10s}] {r['tracker_site'][:50]:50s} -> {r['sf_name'][:40]:40s} | stage={r['sf_stage'][:18]:18s} pc={r['sf_proj_close']:12s} score={r['match_score']}")

with open('tracker_to_sf_matches.json', 'w', encoding='utf-8') as f:
    json.dump({'matched': results, 'unmatched': unmatched}, f, indent=2, default=str)
print("\nWrote tracker_to_sf_matches.json")
