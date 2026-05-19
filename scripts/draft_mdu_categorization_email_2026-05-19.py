"""Build an Outlook DRAFT (never sent) explaining the MDU Categorization updates:
new field + import, tracker column, OnNet->Cat1 alignment, PAL agreement creation,
and the duplicate-record review items. Recipient left blank (Koa fills it in).
"""
import win32com.client

# Verified figures from the 2026-05-19 work
N_OPPS = 313
ONNET, OFFNET, NEARNET = 151, 141, 21
N_VIEWS = 12
N_ALIGNED = 12

html = f"""
<html>
<body style="font-family:Calibri,Arial,sans-serif; font-size:11pt; color:#222;">

<p>Hi,</p>

<p>Quick rundown of the MDU categorization work we just pushed into Salesforce,
sourced from the <i>Signed MDU Agreement Analysis</i> workbook (Signed MDUs tab).</p>

<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Update</th><th>Count</th><th>Status</th></tr>
  </thead>
  <tbody>
    <tr style="background-color:#D5F5E3;">
      <td>New "MDU Categorization" field (OnNet / OffNet / NearNet) populated on Opportunities</td>
      <td align="center"><b>{N_OPPS}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#D5F5E3;">
      <td>Field added as a column in the MDU Tracker (next to Category), across all stage views</td>
      <td align="center"><b>{N_VIEWS}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#D5F5E3;">
      <td>Serviceability category aligned: every OnNet Opp now reads Cat 1</td>
      <td align="center"><b>{N_ALIGNED}</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#D5F5E3;">
      <td>Missing PAL agreement created on 1810 N 8th St (it was building with no PAL record on file)</td>
      <td align="center"><b>1</b></td>
      <td>Done</td>
    </tr>
    <tr style="background-color:#FFF3CD;">
      <td>Possible duplicate / mis-linked records flagged for review</td>
      <td align="center"><b>4 groups</b></td>
      <td>Needs review</td>
    </tr>
    <tr style="background-color:#FFF3CD;">
      <td>Opportunity with a signed PAL still sitting at Prospects (Birchwood Apts)</td>
      <td align="center"><b>1</b></td>
      <td>Needs review</td>
    </tr>
  </tbody>
</table>

<h3 style="margin-top:18px;">What "MDU Categorization" is</h3>
<p>It is the network categorization from the signed-agreement workbook: OnNet, OffNet,
or NearNet. It is separate from the existing "Category" field (Cat 1 / 2 / 3), which is
serviceability distance to fiber. Breakdown of what was loaded:</p>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Value</th><th>Opportunities</th></tr>
  </thead>
  <tbody>
    <tr><td>OnNet</td><td align="center">{ONNET}</td></tr>
    <tr><td>OffNet</td><td align="center">{OFFNET}</td></tr>
    <tr><td>NearNet</td><td align="center">{NEARNET}</td></tr>
  </tbody>
</table>
<p>All 316 source rows linked to an Opportunity (most via the SiteTracker link on the
Monday.com name, the rest by name match or manual confirmation). PAL cross-check: of the
228 rows that show a signed PAL, 227 line up with a signed PAL agreement in Salesforce.</p>

<h3 style="margin-top:18px;">Records flagged for review</h3>
<p>While linking, a few SiteTracker projects share an address or name. None are exact
duplicates (every project ID is unique), but these are worth a look:</p>
<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse; font-size:10.5pt;">
  <thead style="background-color:#305496; color:#fff; font-weight:bold;">
    <tr><th>Item</th><th>Detail</th><th>Suggested action</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>Indian Hills Terrace</td>
      <td>Two different properties (Terrace P-005578 and Village Court P-006838) both link to one Opportunity</td>
      <td>Give Village Court its own Opportunity</td>
    </tr>
    <tr>
      <td>Orchard Park Apartments</td>
      <td>"Orchard Park Apartments" + "...-2" at 7805 Harney St, same Monday name, units 19 vs 25</td>
      <td>Confirm second building vs duplicate</td>
    </tr>
    <tr>
      <td>Indian Hills Village Apartments</td>
      <td>"...Apartments" + "...-2" at 107 S 87th St, same Monday name, units 21 vs 15</td>
      <td>Confirm second building vs duplicate</td>
    </tr>
    <tr>
      <td>4750 / 4760 Lafayette Ave</td>
      <td>Two adjacent buildings bundled on one Opp; the 4750 row's address was entered as 4760</td>
      <td>Fix address; decide one Opp or two</td>
    </tr>
  </tbody>
</table>

<p>Full detail is in two write-ups on my end (categorization summary and a duplicate
cleanup list) that I can share if useful.</p>

<p>Thanks,<br>Cass</p>

</body>
</html>
"""

SUBJECT = "MDU Categorization rollout + signed-MDU updates"

outlook = win32com.client.Dispatch("Outlook.Application")
ns = outlook.GetNamespace("MAPI")
drafts = ns.GetDefaultFolder(16)  # olFolderDrafts
for item in list(drafts.Items):
    try:
        if getattr(item, "Subject", None) == SUBJECT:
            item.Delete()
            print(f"Removed prior draft: {item.Subject!r}")
    except Exception:
        pass

mail = outlook.CreateItem(0)  # MailItem
mail.To = ""  # recipient intentionally blank per Koa
mail.Subject = SUBJECT
mail.HTMLBody = html
mail.Save()  # DRAFT ONLY -- never .Send()
print("Outlook draft saved (no recipient set).")
print(f"  Subject: {mail.Subject}")
