"""
Link 12 new IronClad easement records (imported 4/24) to existing SF Opps.
For each match:
  1. Create a new Agreement__c (Type=ROE, Status=Completed, Signed_Date from IC, linked to Opp and IronClad__c)
  2. Update IronClad__c.Agreement__c to point back at the new Agreement (bidirectional)
For the 3 Prospecting-stage matches, also promote StageName to ROE Secured.
"""
import sys, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

# 12 approved matches: (IronClad Counterparty, Opp Id, promote_to_ROE_Secured)
# Opp Ids resolved live to avoid stale data
matches = [
    # EXACT (all already ROE Secured)
    ('Haciendas De La Playa HOA', 'Haciendas de la Playa', False),
    ('Solana Beach and Tennis Club HOA', 'Solana Beach and Tennis Club', False),
    ('Terraces at Cantebria HOA', 'Terraces At Cantebria HOA', False),
    ('Cardiff Glen HOA', 'Cardiff Glen HOA', False),
    ('PORTICO AT RANCHO CARRILLO HOMEOWNERS ASSOCIATION', 'Portico At Rancho Carrillo HOA', False),
    ('Las Vistas HOA', 'Las Vistas HOA', False),
    ('Village Park', 'Village Park HOA', True),  # Prospecting -> ROE Secured
    # PARTIAL (all approved)
    ('Saxony at Encinitas Ranch HOA', 'Encinitas Ranch HOA', True),  # Prospecting -> ROE Secured
    ('Beacons Beach Homeowners Association', 'Beacons Beach Village', True),  # Prospecting -> ROE Secured
    ('Oceanic Drive-Private Road', 'Oceanic Drive', False),
    ('North Shore Encinitas Owners', 'North Shore HOA', False),
    ('Laurel Cove Homeowners Association', 'Laurel Cove Lane Pvt Road', False),
]

import datetime as dt

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

today_iso = dt.datetime.now().strftime("%Y-%m-%dT00:00:00Z")
new_ic = sf.query_all(f"""
  SELECT Id, Counterparty_Name__c, Record_Name__c, Record_Type_IC__c,
         Agreement_Date__c, Contract_Status__c, Stage_IC__c, IronClad_Id__c,
         Agreement__c
  FROM IronClad__c WHERE CreatedDate >= {today_iso}
""")['records']
ic_by_cp = {r['Counterparty_Name__c']: r for r in new_ic if r.get('Counterparty_Name__c')}
print(f"New IronClad records available: {len(ic_by_cp)}")

# Resolve Opp Ids by exact Name
opp_names = {name for _, name, _ in matches}
names_q = ",".join(f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in opp_names)
opp_recs = sf.query_all(f"""
  SELECT Id, Name, StageName FROM Opportunity WHERE Name IN ({names_q})
""")['records']
opp_by_name = {o['Name']: o for o in opp_recs}

results = {'created': [], 'failed': [], 'promoted': [], 'ic_linked': []}
for counterparty, opp_name, promote in matches:
    ic = ic_by_cp.get(counterparty)
    opp = opp_by_name.get(opp_name)
    if not ic:
        print(f"  [SKIP] IronClad record not found: {counterparty!r}")
        results['failed'].append({'reason': 'ic_not_found', 'counterparty': counterparty})
        continue
    if not opp:
        print(f"  [SKIP] Opp not found: {opp_name!r}")
        results['failed'].append({'reason': 'opp_not_found', 'opp_name': opp_name})
        continue

    # Create Agreement__c
    agreement = {
        'Opportunity__c': opp['Id'],
        'Agreement_Type__c': 'ROE',
        'Status__c': 'Completed',
        'Signed_Date__c': ic.get('Agreement_Date__c'),
        'IronClad_Record__c': ic['Id'],
        'IronClad_ID__c': ic.get('IronClad_Id__c'),
        'IronClad_Contract_Status__c': ic.get('Contract_Status__c'),
        'IronClad_Stage__c': ic.get('Stage_IC__c'),
    }
    try:
        r = sf.Agreement__c.create(agreement)
        if r.get('success'):
            new_ag_id = r['id']
            results['created'].append({'counterparty': counterparty, 'opp': opp_name, 'sf_id': new_ag_id})
            print(f"  [OK]  Agreement created on {opp_name:<38} Signed {ic.get('Agreement_Date__c')} -> {new_ag_id}")

            # Bidirectional: update IronClad__c.Agreement__c
            try:
                sf.IronClad__c.update(ic['Id'], {'Agreement__c': new_ag_id})
                results['ic_linked'].append({'ic_id': ic['Id'], 'agreement_id': new_ag_id})
            except Exception as e:
                print(f"    (bidirectional link failed: {e})")

            # Promote stage if needed
            if promote and opp.get('StageName') != 'ROE Secured':
                try:
                    sf.Opportunity.update(opp['Id'], {'StageName': 'ROE Secured'})
                    results['promoted'].append({'opp': opp_name, 'from': opp['StageName'], 'to': 'ROE Secured'})
                    print(f"    Stage promoted: {opp['StageName']} -> ROE Secured")
                except Exception as e:
                    print(f"    (stage promote failed: {e})")
        else:
            results['failed'].append({'counterparty': counterparty, 'error': r})
            print(f"  [FAIL] {counterparty}: {r}")
    except Exception as e:
        results['failed'].append({'counterparty': counterparty, 'error': str(e)})
        print(f"  [FAIL] {counterparty}: {e}")

with open(r'C:\Users\cass\Work_Projects\IronClad\link_results_2026-04-24.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n== SUMMARY ==")
print(f"  Agreements created:   {len(results['created'])}")
print(f"  Bidirectional links:  {len(results['ic_linked'])}")
print(f"  Stages promoted:      {len(results['promoted'])}")
print(f"  Failed:               {len(results['failed'])}")
