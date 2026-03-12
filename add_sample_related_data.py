"""
Add sample related data to Salesforce Opportunities.

Creates:
  1. Contact Roles on 5-6 Opportunities
  2. Products, PricebookEntries, and OpportunityLineItems
  3. Quotes on 2 Negotiation-stage Opportunities
  4. Partner records (ISP partners) on 2-3 Opportunities
"""

import random
import sys
from simple_salesforce import Salesforce, SalesforceError

# ── Salesforce connection ────────────────────────────────────────────────────

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Karate88!",
    security_token="Ktc1n9mLmD9vwEcVcl45q0iAD",
)
print(f"Connected to Salesforce org: {sf.sf_instance}\n")

# ── Tracking ─────────────────────────────────────────────────────────────────

created_records = {
    "ContactRoles": [],
    "Products": [],
    "PricebookEntries": [],
    "OpportunityLineItems": [],
    "Quotes": [],
    "PartnerAccounts": [],
    "Partners": [],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONTACT ROLES
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("1. CONTACT ROLES")
print("=" * 70)

# Get existing contacts
contacts = sf.query(
    "SELECT Id, Name, AccountId FROM Contact LIMIT 20"
)["records"]
print(f"   Found {len(contacts)} contacts")

# Get opportunities with Monday_Item_ID__c
opps = sf.query(
    "SELECT Id, Name, StageName, AccountId "
    "FROM Opportunity WHERE Monday_Item_ID__c != null LIMIT 10"
)["records"]
print(f"   Found {len(opps)} opportunities with Monday_Item_ID__c")

ROLES = ["Decision Maker", "Evaluator", "Executive Sponsor", "Business User"]

# Pick 5-6 opportunities (or all if fewer)
opp_subset = opps[: min(6, len(opps))]

for opp in opp_subset:
    # Pick 1-3 contacts for this opportunity
    num_roles = random.randint(1, 3)
    selected_contacts = random.sample(contacts, min(num_roles, len(contacts)))

    for i, contact in enumerate(selected_contacts):
        role = ROLES[i % len(ROLES)]
        is_primary = i == 0  # first contact is primary

        try:
            result = sf.OpportunityContactRole.create(
                {
                    "OpportunityId": opp["Id"],
                    "ContactId": contact["Id"],
                    "Role": role,
                    "IsPrimary": is_primary,
                }
            )
            created_records["ContactRoles"].append(
                {
                    "id": result["id"],
                    "opp": opp["Name"],
                    "contact": contact["Name"],
                    "role": role,
                    "primary": is_primary,
                }
            )
            primary_tag = " [PRIMARY]" if is_primary else ""
            print(
                f"   + {opp['Name'][:40]:40s} <- {contact['Name']:25s} "
                f"({role}){primary_tag}"
            )
        except SalesforceError as e:
            print(f"   ! Failed on {opp['Name']}: {e}")

print(f"\n   Created {len(created_records['ContactRoles'])} Contact Roles\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PRODUCTS & LINE ITEMS
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("2. PRODUCTS, PRICEBOOK ENTRIES, AND LINE ITEMS")
print("=" * 70)

# Get standard pricebook
pb_result = sf.query("SELECT Id FROM Pricebook2 WHERE IsStandard = true")
if not pb_result["records"]:
    print("   ! No standard pricebook found. Skipping products.")
else:
    standard_pb_id = pb_result["records"][0]["Id"]
    print(f"   Standard Pricebook: {standard_pb_id}")

    # Define products
    PRODUCTS = [
        {
            "Name": "PAL Agreement",
            "Description": "Property Access Letter - legal agreement for property access",
            "Family": "Agreements",
            "UnitPrice": 0.00,
        },
        {
            "Name": "ROW Agreement",
            "Description": "Right of Way agreement for infrastructure access",
            "Family": "Agreements",
            "UnitPrice": 0.00,
        },
        {
            "Name": "EME Agreement",
            "Description": "Easement/Master Easement agreement - includes filing fee",
            "Family": "Agreements",
            "UnitPrice": 500.00,
        },
        {
            "Name": "Fiber Build - Per Unit",
            "Description": "Fiber infrastructure build cost per dwelling unit",
            "Family": "Construction",
            "UnitPrice": 150.00,
        },
        {
            "Name": "Door Fee",
            "Description": "Per-unit door/access fee for MDU properties",
            "Family": "Fees",
            "UnitPrice": 50.00,
        },
    ]

    product_map = {}  # product name -> {product_id, pbe_id, unit_price}

    for prod_def in PRODUCTS:
        # Create Product2
        try:
            prod_result = sf.Product2.create(
                {
                    "Name": prod_def["Name"],
                    "Description": prod_def["Description"],
                    "Family": prod_def.get("Family"),
                    "IsActive": True,
                }
            )
            prod_id = prod_result["id"]
            created_records["Products"].append(
                {"id": prod_id, "name": prod_def["Name"]}
            )
            print(f"   + Product: {prod_def['Name']}")

            # Create PricebookEntry
            pbe_result = sf.PricebookEntry.create(
                {
                    "Pricebook2Id": standard_pb_id,
                    "Product2Id": prod_id,
                    "UnitPrice": prod_def["UnitPrice"],
                    "IsActive": True,
                }
            )
            pbe_id = pbe_result["id"]
            created_records["PricebookEntries"].append(
                {
                    "id": pbe_id,
                    "product": prod_def["Name"],
                    "price": prod_def["UnitPrice"],
                }
            )
            print(
                f"     PricebookEntry: ${prod_def['UnitPrice']:.2f}"
            )

            product_map[prod_def["Name"]] = {
                "product_id": prod_id,
                "pbe_id": pbe_id,
                "unit_price": prod_def["UnitPrice"],
            }

        except SalesforceError as e:
            print(f"   ! Failed creating {prod_def['Name']}: {e}")

    # Add line items to opportunities
    print("\n   Adding line items to opportunities...")

    # Get a few opportunities for line items — mix of stages
    negotiation_opps = sf.query(
        "SELECT Id, Name, StageName, Units__c FROM Opportunity "
        "WHERE Monday_Item_ID__c != null AND StageName = 'Negotiation' LIMIT 3"
    )["records"]

    closed_won_opps = sf.query(
        "SELECT Id, Name, StageName, Units__c FROM Opportunity "
        "WHERE Monday_Item_ID__c != null AND StageName = 'Closed Won' LIMIT 2"
    )["records"]

    # If not enough in those stages, grab whatever we can
    if not negotiation_opps and not closed_won_opps:
        fallback_opps = sf.query(
            "SELECT Id, Name, StageName, Units__c FROM Opportunity "
            "WHERE Monday_Item_ID__c != null LIMIT 4"
        )["records"]
        negotiation_opps = fallback_opps[:2]
        closed_won_opps = fallback_opps[2:4]

    def add_line_item(opp, product_name, quantity=1):
        """Add a line item to an opportunity."""
        if product_name not in product_map:
            return
        pm = product_map[product_name]
        try:
            result = sf.OpportunityLineItem.create(
                {
                    "OpportunityId": opp["Id"],
                    "PricebookEntryId": pm["pbe_id"],
                    "Quantity": quantity,
                    "UnitPrice": pm["unit_price"],
                }
            )
            created_records["OpportunityLineItems"].append(
                {
                    "id": result["id"],
                    "opp": opp["Name"],
                    "product": product_name,
                    "qty": quantity,
                    "total": quantity * pm["unit_price"],
                }
            )
            total = quantity * pm["unit_price"]
            print(
                f"   + {opp['Name'][:35]:35s} | {product_name:25s} "
                f"x{quantity:>4d} = ${total:>10,.2f}"
            )
        except SalesforceError as e:
            print(f"   ! LineItem failed ({opp['Name']}, {product_name}): {e}")

    # Negotiation deals: PAL + Fiber Build
    for opp in negotiation_opps:
        units = int(opp.get("Units__c") or 50)
        add_line_item(opp, "PAL Agreement", 1)
        add_line_item(opp, "Fiber Build - Per Unit", units)

    # Closed Won deals: all agreements + Fiber Build + Door Fee
    for opp in closed_won_opps:
        units = int(opp.get("Units__c") or 50)
        add_line_item(opp, "PAL Agreement", 1)
        add_line_item(opp, "ROW Agreement", 1)
        add_line_item(opp, "EME Agreement", 1)
        add_line_item(opp, "Fiber Build - Per Unit", units)
        add_line_item(opp, "Door Fee", units)

    print(
        f"\n   Created {len(created_records['OpportunityLineItems'])} "
        f"Line Items\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. QUOTES
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("3. QUOTES")
print("=" * 70)

# Use negotiation-stage opps for quotes
quote_opps = negotiation_opps[:2] if negotiation_opps else opp_subset[:2]

for i, opp in enumerate(quote_opps, start=1):
    quote_name = f"Q-2026-{i:03d} - {opp['Name'][:50]}"
    try:
        result = sf.Quote.create(
            {
                "OpportunityId": opp["Id"],
                "Name": quote_name,
                "Status": "Draft",
                "ExpirationDate": "2026-06-30",
            }
        )
        created_records["Quotes"].append(
            {"id": result["id"], "name": quote_name, "opp": opp["Name"]}
        )
        print(f"   + Quote: {quote_name}")
    except SalesforceError as e:
        print(f"   ! Quote failed on {opp['Name']}: {e}")

print(f"\n   Created {len(created_records['Quotes'])} Quotes\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PARTNERS
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("4. PARTNERS")
print("=" * 70)

ISP_PARTNERS = [
    {
        "Name": "FiberFirst Networks",
        "Industry": "Telecommunications",
        "Description": "Regional fiber ISP partner for MDU builds",
    },
    {
        "Name": "Ting Internet",
        "Industry": "Telecommunications",
        "Description": "Fiber-to-the-home ISP partner",
    },
    {
        "Name": "ClearWave Broadband",
        "Industry": "Telecommunications",
        "Description": "Fixed wireless and fiber ISP for multi-family",
    },
]

partner_account_ids = []

for isp in ISP_PARTNERS:
    # Check if account already exists
    existing = sf.query(
        f"SELECT Id, Name FROM Account WHERE Name = '{isp['Name']}' LIMIT 1"
    )
    if existing["records"]:
        acct_id = existing["records"][0]["Id"]
        print(f"   Found existing account: {isp['Name']}")
    else:
        try:
            result = sf.Account.create(
                {
                    "Name": isp["Name"],
                    "Industry": isp["Industry"],
                    "Description": isp["Description"],
                    "Type": "Technology Partner",
                }
            )
            acct_id = result["id"]
            created_records["PartnerAccounts"].append(
                {"id": acct_id, "name": isp["Name"]}
            )
            print(f"   + Account: {isp['Name']}")
        except SalesforceError as e:
            print(f"   ! Account failed ({isp['Name']}): {e}")
            continue

    partner_account_ids.append({"id": acct_id, "name": isp["Name"]})

# Link partners to 2-3 opportunities
partner_opps = opp_subset[:3]

for i, opp in enumerate(partner_opps):
    partner = partner_account_ids[i % len(partner_account_ids)]

    # Skip if the partner account is the same as the opportunity's account
    if partner["id"] == opp.get("AccountId"):
        print(
            f"   ~ Skipping {opp['Name']} - partner is same as opp account"
        )
        continue

    # Try with Role first, fall back without
    try:
        result = sf.Partner.create(
            {
                "OpportunityId": opp["Id"],
                "AccountToId": partner["id"],
            }
        )
        created_records["Partners"].append(
            {"id": result["id"], "opp": opp["Name"], "partner": partner["name"]}
        )
        print(f"   + {opp['Name'][:40]:40s} <-> {partner['name']}")
    except SalesforceError as e:
        # Partner object might not be enabled or may need different approach
        print(f"   ! Partner failed ({opp['Name']} <-> {partner['name']}): {e}")


print(f"\n   Created {len(created_records['Partners'])} Partner links\n")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"   Contact Roles created:       {len(created_records['ContactRoles'])}")
print(f"   Products created:            {len(created_records['Products'])}")
print(f"   PricebookEntries created:    {len(created_records['PricebookEntries'])}")
print(f"   OpportunityLineItems created:{len(created_records['OpportunityLineItems'])}")
print(f"   Quotes created:              {len(created_records['Quotes'])}")
print(f"   Partner Accounts created:    {len(created_records['PartnerAccounts'])}")
print(f"   Partner links created:       {len(created_records['Partners'])}")

total = sum(len(v) for v in created_records.values())
print(f"\n   TOTAL RECORDS CREATED: {total}")
print("\nDone!")
