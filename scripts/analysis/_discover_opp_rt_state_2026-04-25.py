"""
Read-only discovery: snapshot the current state of Opportunity RTs, Sales Processes,
Stage picklist, profile RT visibility, layouts, and FlexiPages -- before adding the
new Business ROE Record Type.

Output: Work_Projects/SalesForce/audit_logs/opp_rt_state_2026-04-25.json
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from datetime import datetime
from simple_salesforce import Salesforce

sf = Salesforce(username=_SF["username"], password=_SF["password"], security_token=_SF["token"])

snap = {'generated_at': datetime.now().isoformat(timespec='seconds')}

# ── 1. Record Types on Opportunity ──
print("\n[1] Opportunity Record Types")
rts = sf.query("SELECT Id, Name, DeveloperName, IsActive, BusinessProcessId, Description FROM RecordType WHERE SObjectType='Opportunity' ORDER BY DeveloperName")
snap['record_types'] = rts['records']
for rt in rts['records']:
    print(f"  {rt['DeveloperName']:20s} active={rt['IsActive']!s:5s} bp={rt['BusinessProcessId']}  desc={rt['Description']}")

# ── 2. Business Processes (Sales Processes) on Opportunity ──
print("\n[2] Sales Processes (BusinessProcess) on Opportunity")
bps = sf.toolingexecute(
    "query/?q=" + "SELECT+Id,Name,Description,IsActive+FROM+BusinessProcess"
)
snap['business_processes'] = bps.get('records', [])
for bp in bps.get('records', []):
    print(f"  {bp.get('Name',''):30s} active={bp.get('IsActive')!s:5s} id={bp.get('Id')}")

# ── 3. OpportunityStage picklist values (with probability + forecast category) ──
print("\n[3] OpportunityStage picklist values (org-wide)")
desc = sf.Opportunity.describe()
for f in desc['fields']:
    if f['name'] == 'StageName':
        snap['stage_picklist'] = []
        for v in f['picklistValues']:
            snap['stage_picklist'].append({'label': v['label'], 'value': v['value'], 'active': v['active'], 'defaultValue': v['defaultValue']})
            print(f"  {v['value']:50s} active={v['active']!s:5s} default={v['defaultValue']}")
        break

# Per-RT picklist values via Process Builder Picklist endpoint
print("\n[3b] OpportunityStage values per Record Type (UI-API)")
snap['stage_per_rt'] = {}
import requests

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()

hdr = {'Authorization': f'Bearer {sf.session_id}', 'Content-Type': 'application/json'}
for rt in snap['record_types']:
    rt_id = rt['Id']
    url = f"https://{sf.sf_instance}/services/data/v59.0/ui-api/object-info/Opportunity/picklist-values/{rt_id}/StageName"
    r = requests.get(url, headers=hdr)
    if r.status_code == 200:
        data = r.json()
        vals = [v['value'] for v in data.get('values', [])]
        snap['stage_per_rt'][rt['DeveloperName']] = vals
        print(f"  {rt['DeveloperName']:20s} {len(vals)} stages: {vals}")
    else:
        print(f"  {rt['DeveloperName']:20s} ERROR {r.status_code}: {r.text[:200]}")

# ── 4. Profiles + active user counts ──
print("\n[4] Profiles (with active user count)")
profs = sf.query("SELECT Id, Name, UserType FROM Profile ORDER BY Name")
snap['profiles'] = []
for p in profs['records']:
    cnt = sf.query(f"SELECT COUNT(Id) c FROM User WHERE ProfileId='{p['Id']}' AND IsActive=true")['records'][0]['c']
    entry = {'Id': p['Id'], 'Name': p['Name'], 'UserType': p['UserType'], 'active_users': cnt}
    snap['profiles'].append(entry)
    if cnt > 0 or 'MDU' in p['Name'] or 'Business' in p['Name'] or 'Sales' in p['Name'] or 'Admin' in p['Name'] or 'RE' in p['Name']:
        print(f"  {p['Name']:50s} users={cnt:3d}  type={p['UserType']}")

# ── 5. Active users by profile (so we know who's in each bucket) ──
print("\n[5] Active internal users by profile")
users = sf.query("SELECT Id, Name, Email, ProfileId, Profile.Name, IsActive FROM User WHERE IsActive=true AND UserType='Standard' ORDER BY Profile.Name, Name")
snap['active_users'] = users['records']
by_prof = {}
for u in users['records']:
    pn = u['Profile']['Name'] if u['Profile'] else '(none)'
    by_prof.setdefault(pn, []).append(f"{u['Name']} <{u['Email']}>")
for pn, lst in sorted(by_prof.items()):
    print(f"  {pn}:")
    for entry in lst:
        print(f"    {entry}")

# ── 6. Permission Sets (look for SMB_RE_Field_Access et al) ──
print("\n[6] Custom Permission Sets")
psets = sf.query("SELECT Id, Name, Label, IsCustom, Description FROM PermissionSet WHERE IsCustom=true ORDER BY Name")
snap['permission_sets'] = psets['records']
for p in psets['records']:
    print(f"  {p['Name']:40s} label={p['Label']}")

# ── 7. Layouts on Opportunity ──
print("\n[7] Page Layouts on Opportunity")
layouts = sf.toolingexecute("query/?q=" + "SELECT+Id,Name,TableEnumOrId+FROM+Layout+WHERE+TableEnumOrId='Opportunity'+ORDER+BY+Name")
snap['layouts'] = layouts.get('records', [])
for l in layouts.get('records', []):
    print(f"  {l.get('Name',''):60s} id={l.get('Id')}")

# ── 8. Layout assignments per Profile ──
print("\n[8] Layout assignments per Profile (Opportunity)")
# ProfileLayout assignments live on Profile.layoutAssignments inside metadata
# Easier here: query ListView style via Tooling API? Actually we'll skip this for snapshot;
# easier to get from UI / metadata retrieve later if needed.
print("  (skipped — will retrieve via Metadata API when actually editing)")

# ── 9. FlexiPages on Opportunity ──
print("\n[9] FlexiPages (Lightning Record Pages) for Opportunity")
fps = sf.toolingexecute("query/?q=" + "SELECT+Id,DeveloperName,MasterLabel,Type+FROM+FlexiPage+WHERE+Type='RecordPage'")
fps['records'] = [f for f in fps.get('records', []) if 'opp' in f.get('DeveloperName','').lower() or 'opp' in f.get('MasterLabel','').lower()]
snap['flexipages'] = fps.get('records', [])
for f in fps.get('records', []):
    print(f"  {f.get('DeveloperName',''):60s} label={f.get('MasterLabel','')}")

# ── 10. Validation Rules on Opportunity ──
print("\n[10] Validation Rules on Opportunity")
vrs = sf.toolingexecute("query/?q=" + "SELECT+Id,ValidationName,Active,Description+FROM+ValidationRule+WHERE+EntityDefinition.QualifiedApiName='Opportunity'")
snap['validation_rules'] = vrs.get('records', [])
for v in vrs.get('records', []):
    print(f"  {v.get('ValidationName',''):40s} active={v.get('Active')!s:5s}  desc={v.get('Description','')}")

# ── 11. Existing Opportunity custom fields relevant to SMB ROE pursuit ──
print("\n[11] Opportunity custom fields with 'roe', 'pursuit', 'closed', 'hold', 'handoff', 'ff_' in name")
relevant = []
for f in desc['fields']:
    n = f['name'].lower()
    if any(k in n for k in ['roe', 'pursuit', 'closed_b', 'closed_n', 'hold_', 'handoff', 'ff_', 'off_hold']):
        relevant.append({'name': f['name'], 'label': f['label'], 'type': f['type']})
        print(f"  {f['name']:40s} label={f['label']!r:50s} type={f['type']}")
snap['relevant_existing_fields'] = relevant

# ── Save ──
out = Path(r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\opp_rt_state_2026-04-25.json')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(snap, indent=2, default=str), encoding='utf-8')
print(f"\nSnapshot saved: {out}")
