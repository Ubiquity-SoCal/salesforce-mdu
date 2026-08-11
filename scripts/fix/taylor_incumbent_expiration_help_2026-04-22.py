"""Add inlineHelpText to Incumbent_Agreement_Expiration__c.

Taylor's 2026-04-21 feedback flagged this as still missing on 2026-04-22.
Original taylor_revisions_2026-04-21.py deployed the other 3 items (Property
Address help + city/state/zip validation, EMA/NEMA picklist values, FlexiPage
tab move) but didn't include the expiration field help text.
"""
import sys
import json
import requests
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


DRY_RUN = "--dry-run" in sys.argv

HELP_TEXT = (
    "If you don't know the specific date, put the first day of the month the agreement "
    "will expire so we can still track incumbent expirations coming up in the next 3-6 months. "
    "This is how we'll know when a competitor's contract is going to expire so sales can start "
    "negotiating a Ubiquity/FF agreement."
)


def main():
    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )
    base = sf.base_url.rstrip('/').replace('/data/v59.0', '/data/v59.0/tooling')
    h = {"Authorization": f"Bearer {sf.session_id}", "Content-Type": "application/json"}

    r = requests.get(
        f"{base}/query/?q=SELECT+Id+FROM+CustomField+WHERE+TableEnumOrId%3D%27Opportunity%27"
        f"+AND+DeveloperName%3D%27Incumbent_Agreement_Expiration%27",
        headers=h,
    ).json()
    fid = r["records"][0]["Id"]

    meta = requests.get(f"{base}/sobjects/CustomField/{fid}", headers=h).json()["Metadata"]
    print(f"Current help: {meta.get('inlineHelpText') or '(none)'}")
    meta["inlineHelpText"] = HELP_TEXT

    if DRY_RUN:
        print(f"[DRY] would set to: {HELP_TEXT}")
        return

    r = requests.patch(
        f"{base}/sobjects/CustomField/{fid}",
        headers=h,
        data=json.dumps({"Metadata": meta}),
    )
    print(f"Status: {r.status_code}")
    if r.status_code in (200, 204):
        print(f"[OK] inlineHelpText set")
    else:
        print(f"[FAIL] {r.text}")


if __name__ == "__main__":
    main()
