"""
Create the "SoCal HOA/SFU Project" Campaign and link the 107 CA MDU merge Opps.

The 107 Opps are identified by Owner = Justin Barry AND Pipeline_Bucket__c != null,
which is the exact signature of the 2026-04-21 CA MDU Merge import.
Matches the 107 rows across the CA Pipeline + On Air tabs of
'CA MDU Agreement Status 04172026.xlsx'.

Idempotent: skips create if Campaign already exists, skips Opps already linked.

Usage:
  python assign_campaign_socal_hoa_sfu.py --dry-run
  python assign_campaign_socal_hoa_sfu.py
"""

import sys
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


DRY_RUN = "--dry-run" in sys.argv

CAMPAIGN_CONFIG = {
    "Name": "SoCal HOA/SFU Project",
    "Type": "Other",
    "Status": "In Progress",
    "IsActive": True,
    "StartDate": "2026-01-01",
    "Resolution_Stage__c": "ROE Secured",
    "Description": (
        "SoCal HOA and SFU properties from the 2026-04-21 CA MDU Agreement Status + "
        "Opportunities_Prospects_RE merge. 107 properties across Encinitas, Carlsbad, "
        "Oceanside, and Solana Beach. Property mix: 84 SFU, 17 MDU, 6 Mobile Home Park. "
        "Note: HOAs are treated as SFUs for this project."
    ),
}


def main():
    print("=" * 70)
    print(f"Assign Campaign '{CAMPAIGN_CONFIG['Name']}'  ({'DRY RUN' if DRY_RUN else 'LIVE'})")
    print("=" * 70)

    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )

    # Find or create Campaign
    existing = sf.query(
        f"SELECT Id, Name FROM Campaign WHERE Name = '{CAMPAIGN_CONFIG['Name']}' LIMIT 1"
    )
    if existing["totalSize"]:
        campaign_id = existing["records"][0]["Id"]
        print(f"\nCampaign exists: {campaign_id}")
    else:
        if DRY_RUN:
            print("\nWould CREATE Campaign:")
            for k, v in CAMPAIGN_CONFIG.items():
                print(f"  {k}: {v}")
            campaign_id = "<new>"
        else:
            result = sf.Campaign.create(CAMPAIGN_CONFIG)
            campaign_id = result["id"]
            print(f"\nCreated Campaign: {campaign_id}")

    # Find the 107 Opps
    q = (
        "SELECT Id, Name, HOA__c, CampaignId, Property_City__c, Pipeline_Bucket__c "
        "FROM Opportunity "
        "WHERE Owner.Name = 'Justin Barry' AND Pipeline_Bucket__c != null"
    )
    r = sf.query_all(q)
    opps = r["records"]
    print(f"\nCandidate Opps: {len(opps)}")

    to_link = [o for o in opps if o.get("CampaignId") != campaign_id]
    already = len(opps) - len(to_link)
    print(f"  Already on this Campaign: {already}")
    print(f"  Will link: {len(to_link)}")

    if DRY_RUN:
        print("\nSample of what would be linked (first 10):")
        for o in to_link[:10]:
            print(f"  {o['Id']}  {o['Name'][:55]:55}  HOA={o.get('HOA__c')}  Bucket={o.get('Pipeline_Bucket__c')}")
        print("\nDRY RUN — no writes.")
        return

    if not to_link:
        print("\nNothing to link. Done.")
        return

    print(f"\nLinking {len(to_link)} Opps...")
    ok, errors = 0, []
    for i, opp in enumerate(to_link, 1):
        try:
            sf.Opportunity.update(opp["Id"], {"CampaignId": campaign_id})
            ok += 1
            if i % 25 == 0:
                print(f"  {i}/{len(to_link)}...")
        except Exception as e:
            errors.append((opp["Id"], opp.get("Name"), str(e)))

    print(f"\nLinked: {ok}")
    if errors:
        print(f"Errors: {len(errors)}")
        for eid, name, err in errors[:5]:
            print(f"  {eid} {name}: {err}")

    print(f"\nCampaign Id: {campaign_id}")
    print(f"URL: https://fun-power-747.lightning.force.com/lightning/r/Campaign/{campaign_id}/view")


if __name__ == "__main__":
    main()
