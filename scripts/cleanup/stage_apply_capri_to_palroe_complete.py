"""Move Capri on Camelback (006WR00000wkEc3YAE) from Contract Negotiations
to PAL/ROE Complete. All 3 child Agreements signed; AGR-1039 IronClad-confirmed
(IC-153, stage=completed, status=active)."""
from simple_salesforce import Salesforce
from datetime import datetime
import csv
import os

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

OPP_ID = '006WR00000wkEc3YAE'
NEW_STAGE = 'PAL/ROE Complete'

before = sf.Opportunity.get(OPP_ID)
print(f"Before: {before['Name']}  StageName={before['StageName']}")

if before['StageName'] == NEW_STAGE:
    print("Already in target stage; nothing to do.")
    raise SystemExit(0)

result = sf.Opportunity.update(OPP_ID, {'StageName': NEW_STAGE})
print(f"Update HTTP status: {result}")

after = sf.Opportunity.get(OPP_ID)
print(f"After:  {after['Name']}  StageName={after['StageName']}  Probability={after['Probability']}")

# Audit log
ts = datetime.utcnow().isoformat() + 'Z'
log_dir = os.path.join('SalesForce', 'audit_logs')
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, f'stage_cleanup_{datetime.utcnow().strftime("%Y-%m-%d")}.csv')
new_file = not os.path.exists(log_path)
with open(log_path, 'a', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    if new_file:
        w.writerow(['SF_Id','Name','Field','Before','After','Source','Timestamp','Action'])
    w.writerow([
        OPP_ID, before['Name'], 'StageName',
        before['StageName'], after['StageName'],
        'stage_cleanup_2026-05-01 (Capri auto-move; IronClad IC-153 confirmed completed)',
        ts, 'update'
    ])
print(f"Logged to {log_path}")
