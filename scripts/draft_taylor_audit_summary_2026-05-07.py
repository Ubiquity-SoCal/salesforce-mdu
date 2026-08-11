"""Build an Outlook draft summarizing the Taylor 5/4 review actions.

Reads the audit CSVs from
SalesForce/audit_logs/2026-05-07_taylor_ema_bulk_cleanup/
and builds a single email with summary table + per-section detail.
"""
import csv
import glob
import os
import win32com.client

AUDIT_DIR = r'C:\Users\cass\Work_Projects\SalesForce\audit_logs\2026-05-07_taylor_ema_bulk_cleanup'

def newest(pattern):
    matches = sorted(glob.glob(os.path.join(AUDIT_DIR, pattern)))
    return matches[-1] if matches else None

def load_csv(path):
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

repoint   = load_csv(newest('phase2_repoint_*.csv')) if newest('phase2_repoint_*.csv') else []
agrs_csv  = load_csv(newest('phase2_agreements_*.csv'))
opps_csv  = load_csv(newest('phase2_opps_*.csv'))
stage_csv = load_csv(newest('phase2_stage_revert_*.csv'))

# Earlier (pre-pivot) repoint run created the 6 CDLs.  Pull that one too.
all_repoint = []
for f in sorted(glob.glob(os.path.join(AUDIT_DIR, 'phase2_repoint_*.csv'))):
    all_repoint.extend(load_csv(f))

n_agrs_deleted = sum(1 for r in agrs_csv if r['Result'] == 'OK')
n_opps_deleted = sum(1 for r in opps_csv if r['Result'] == 'OK')
n_stage_moves = sum(1 for r in stage_csv if r['Result'] == 'OK')
n_junctions = sum(1 for r in all_repoint if r['Object'] == 'Opportunity_Contact__c' and r['Result'] == 'OK')
n_cdls = sum(1 for r in all_repoint if r['Object'] == 'ContentDocumentLink' and r['Result'] == 'OK')
n_agr_clones = sum(1 for r in all_repoint if r['Object'] == 'Agreement__c' and r['Result'] == 'OK')

# Build per-Opp summary for the 3 dupe deletions
dupe_rows = [r for r in opps_csv if r['Result'] == 'OK']

# Per-owner breakdown of the 187 agreement deletes (need Opp -> Owner map; pull from snapshot)
import json
with open(os.path.join(AUDIT_DIR, 'phase1_resolved_targets.json'), encoding='utf-8') as f:
    targets = json.load(f)

# Approximate owner breakdown from the xlsx-derived plan: count by Opportunity__c
agr_by_opp = {}
for a in targets['agreements_to_delete']:
    agr_by_opp.setdefault(a['Opportunity__c'], []).append(a)

# Pull owner names live so the breakdown is reliable
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
opp_ids = list(agr_by_opp.keys())
ids_str = "','".join(opp_ids)
opp_owners = sf.query_all(f"""
    SELECT Id, Owner.Name FROM Opportunity WHERE Id IN ('{ids_str}')
""")['records']
owner_by_opp = {o['Id']: o['Owner']['Name'] for o in opp_owners}

owner_counts_opps = {}
owner_counts_agrs = {}
for opp_id, agrs in agr_by_opp.items():
    owner = owner_by_opp.get(opp_id, '(unknown)')
    owner_counts_opps[owner] = owner_counts_opps.get(owner, 0) + 1
    owner_counts_agrs[owner] = owner_counts_agrs.get(owner, 0) + len(agrs)

owner_breakdown_html = ''.join(
    f'<tr><td>{o}</td><td align="center">{owner_counts_opps[o]}</td>'
    f'<td align="center">{owner_counts_agrs[o]}</td></tr>'
    for o in sorted(owner_counts_opps, key=lambda x: -owner_counts_agrs[x])
)

# ─── Build HTML body ─────────────────────────────────────────────────────────
html = f"""
<html>
<body style="font-family:Calibri,Arial,sans-serif; font-size:11pt; color:#222;">

<p>Hi Taylor,</p>

<p>I worked through everything you flagged on the <i>Take 2 MDU Sales Review</i>
spreadsheet. Summary below.</p>

<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Action</th><th>Count</th><th>Verdict</th></tr>
  </thead>
  <tbody>
    <tr style="background-color:#D5F5E3;">
      <td>EMA / Bulk Agreement records deleted (per your "delete any EMA or Bulk listed" notes)</td>
      <td align="center"><b>{n_agrs_deleted}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#D5F5E3;">
      <td>Duplicate Opportunities deleted</td>
      <td align="center"><b>{n_opps_deleted}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#D5F5E3;">
      <td>Opportunities reverted to PAL/ROE Complete (no longer have any EMA/Bulk basis)</td>
      <td align="center"><b>{n_stage_moves}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#FFF3CD;">
      <td>Contacts, files, and signed ROE records preserved on the keeper Opp before the dupe was deleted</td>
      <td align="center"><b>{n_junctions + n_cdls + n_agr_clones}</b></td>
      <td>Preserved</td>
    </tr>
  </tbody>
</table>

<h3 style="margin-top:18px;">EMA / Bulk Agreements deleted ({n_agrs_deleted} records, across {len(opp_ids)} Opportunities)</h3>

<p>These were the leftover Marketing/Bulk Agreement records you flagged. The Opportunities themselves stayed,
but their EMA/Bulk children were removed and the Opp stage was rolled back to PAL/ROE Complete since
there's no longer an active Marketing/Bulk pursuit on file.</p>

<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Owner</th><th>Opps cleaned</th><th>Agreement records removed</th></tr>
  </thead>
  <tbody>
    {owner_breakdown_html}
  </tbody>
</table>

<h3 style="margin-top:18px;">Duplicate Opportunities deleted ({n_opps_deleted})</h3>

<p>For each duplicate, I checked what was on the dupe vs the surviving "keeper" Opportunity. Anything unique
on the dupe (contacts, files, signed ROE agreements that the keeper didn't have) was copied over to the
keeper before the dupe was deleted, so nothing was lost.</p>

<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Deleted (dupe)</th><th>Kept (canonical)</th><th>Preserved on keeper</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>Killeen_MDU_The Bungalows</td>
      <td>The Bungalows (Melissa)</td>
      <td>2 contacts (David Jirasek - PM, Cinderella Properties - PO), 2 files,
          1 signed ROE (signed 2025-04-14)</td>
    </tr>
    <tr>
      <td>Killeen_MDU_Bradley Arms</td>
      <td>Bradley Arms (Melissa)</td>
      <td>1 contact (Paul Williams - PO), 2 files</td>
    </tr>
    <tr>
      <td>Killeen_MDU_117-121_W_Avenue_A</td>
      <td>117 and 121 E Avenue A Apartments (Melissa)</td>
      <td>1 contact (Keystone Holdings - PM), 2 files,
          1 signed ROE (signed 2026-03-31)</td>
    </tr>
  </tbody>
</table>

<p>Recycle Bin still holds the deleted records for 15 days if anything looks off, and I have a full pre-change snapshot on my end if we ever need to roll something back.</p>

<p>Let me know if you spot anything that needs adjusting.</p>

<p>Thanks,<br>Cass</p>

</body>
</html>
"""

# ─── Create Outlook draft ────────────────────────────────────────────────────
SUBJECT = "MDU Sales Review (Take 2): cleanup complete"
PRIOR_SUBJECTS = {SUBJECT, "MDU Sales Review (Take 2): cleanup complete + audit trail"}

outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
drafts = ns.GetDefaultFolder(16)  # 16 = olFolderDrafts
# Remove any prior draft from this script so re-running doesn't accumulate copies
items = list(drafts.Items)  # snapshot — Outlook collections are unstable during deletion
for item in items:
    try:
        if getattr(item, 'Subject', None) in PRIOR_SUBJECTS:
            item.Delete()
            print(f'Removed prior draft: {item.Subject!r}')
    except Exception:
        pass

mail = outlook.CreateItem(0)  # 0 = MailItem
mail.To = "taylor@ubiquitygp.com"
mail.Subject = SUBJECT
mail.HTMLBody = html

mail.Save()  # Save as draft
print('Outlook draft saved.')
print(f'  To: {mail.To}')
print(f'  Subject: {mail.Subject}')
