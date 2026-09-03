"""
Park an Outlook draft handing the Salesforce field map and sample records to the
HubSpot consultant, per the 8/31 "Salesforce to Hubspot" call ("I'll give you
access and send my stuff, probably by tomorrow").

Addressed to Kia Zaman (kzaman@fiberfirst.com), the HubSpot side of the migration.
Draft only, never sent.

Run: python draft_hubspot_handoff_email.py
"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.outlook_draft import open_draft  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "output"
ATTACH = [
    OUT / "salesforce-hubspot-field-map.xlsx",
    OUT / "salesforce-hubspot-sample-records.xlsx",
]

BODY = """
<p>Hi Kia,</p>

<p>Two workbooks attached, and your Salesforce admin account is live.</p>

<p><b>Field map</b> covers the MDU Opportunity objects, the AVR cases and SiteTracker.
Every field with its type, whether it is required, its picklist values, and how many
records actually use it. Blank columns on the right for the HubSpot property and type.
Tabs are colour coded: blue is MDU Sales, green is Address Management, amber is SiteTracker.</p>

<p><b>Sample records</b> are four real records end to end, parent plus every related child.</p>

<p>Four things before you map:</p>

<ol>
<li>Contacts link through Opportunity_Contact__c, not OpportunityContactRole, which has 1 row
in the whole org. That junction is not just a link: it carries Role__c (Property Owner,
Property Manager) on 96% of rows, so it needs somewhere to land in HubSpot.</li>
<li>Opportunity Name is not unique, and Agreement_Name__c is empty on 2,995 of 4,174.
Migrate on the record Id.</li>
<li>Business Sales is out of scope. Business ROE is not, and it is 315 live records.</li>
<li>70% of opportunities are owned by deactivated users. That needs an owner decision
before anything imports.</li>
</ol>

<p>The Automation tab lists the triggers, flows and validation rules. None of it imports and
all of it gets rebuilt, so that list will drive the timeline more than the data will.</p>

<p>Let me know what you need next.</p>

<p>Thanks,</p>
"""


SUBJECT = "Salesforce field map and sample records for the HubSpot migration"


TO = "kzaman@fiberfirst.com"


def clear_own_prior_draft():
    """Re-running should replace this script's draft, not stack up copies. Only
    matches this exact subject AND a recipient this script itself would have set
    (blank, or Kia), so a draft re-addressed by hand is left alone."""
    import win32com.client

    ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    drafts = ns.GetDefaultFolder(16)
    ours = {"", TO.lower(), "kia zaman"}
    for item in list(drafts.Items):
        try:
            if item.Subject == SUBJECT and (item.To or "").strip().lower() in ours:
                print(f"  replacing prior draft from {item.CreationTime}")
                item.Delete()
        except Exception as exc:
            print(f"  note: could not inspect a draft: {exc}")


def main():
    missing = [p for p in ATTACH if not p.exists()]
    if missing:
        raise SystemExit(f"missing attachment(s): {missing}")
    clear_own_prior_draft()
    open_draft(
        subject=SUBJECT,
        body_html=BODY,
        to=TO,
        attachments=[str(p) for p in ATTACH],
        display=False,
        save=True,
    )
    print(f"draft saved to Outlook Drafts, addressed to {TO} (not sent)")
    for p in ATTACH:
        print(f"  attached: {p.name}  ({p.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
