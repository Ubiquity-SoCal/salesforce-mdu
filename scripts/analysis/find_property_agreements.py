"""
Find agreements, opps, SiteTracker projects, property locations for 8 target properties.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

TARGETS = [
    {"label": "Del Mar Beach Club",         "street": "137 S Shore",          "name_keys": ["del mar beach club"],          "city": "Solana Beach"},
    {"label": "Del Mar Shores Terrace",     "street": "180 Del Mar Shores",   "name_keys": ["del mar shores"],              "city": "Solana Beach"},
    {"label": "Las Brisas",                 "street": "135 S Sierra",         "name_keys": ["las brisas"],                  "city": "Solana Beach"},
    {"label": "Seascape Chateau",           "street": "707 S Sierra",         "name_keys": ["seascape chateau"],            "city": "Solana Beach"},
    {"label": "Seascape Shores Condos",     "street": "325 S Sierra",         "name_keys": ["seascape shores"],             "city": "Solana Beach"},
    {"label": "Surfsong Condos",            "street": "205 S Helix",          "name_keys": ["surfsong"],                    "city": "Solana Beach"},
    {"label": "Oceanic Drive",              "street": "1145 Oceanic",         "name_keys": ["oceanic"],                     "city": "Encinitas"},
    {"label": "Portico At Rancho Carrillo", "street": "6471 Terraza Portico", "name_keys": ["portico", "rancho carrillo"],  "city": "Carlsbad"},
]


def dq(s):
    return s.replace("'", "\\'")


def query_property_locations(t):
    name_conds = " OR ".join(
        [f"Property_Location_Name__c LIKE '%{dq(k)}%'" for k in t["name_keys"]]
        + [f"Name LIKE '%{dq(k)}%'" for k in t["name_keys"]]
    )
    soql = f"""
        SELECT Id, Name, Property_Location_Name__c, City__c, State__c,
               Property_Status__c, Property_Type__c, Property_Unit_Count__c,
               Active_Unit_Count__c, ROE_Status__c, ROE_Executed__c,
               Access_Agreement_Required__c, Import_Delete_Property__c,
               FDH_Name__c, Circuit_ID__c
        FROM Property_Location__c
        WHERE ({name_conds})
        LIMIT 50
    """
    return sf.query_all(soql)["records"]


def query_opportunities(t):
    street = dq(t["street"])
    name_conds = " OR ".join([f"Name LIKE '%{dq(k)}%'" for k in t["name_keys"]])
    addr_conds = f"Property_Address__c LIKE '%{street}%'"
    agname_conds = " OR ".join([f"Agreement_Name__c LIKE '%{dq(k)}%'" for k in t["name_keys"]])
    soql = f"""
        SELECT Id, Name, StageName, CloseDate,
               Agreement_Name__c, Units__c, Property_Category__c,
               Franchise_Type__c, In_SiteTracker__c,
               Property_Address__c, Property_City__c, Property_State__c, Property_Zip__c,
               Owner.Name, RecordType.Name,
               (SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
                       Expiration_Date__c, Requested_Date__c,
                       IronClad_ID__c, IronClad_URL__c, IronClad_Contract_Status__c,
                       Notes__c
                FROM Agreements__r),
               (SELECT Id, Name, Site_Name__c, Build_Status__c, Site_Status__c,
                       PAL_Signed_Date__c, Activation_Actual__c, Activation_Forecast__c,
                       City__c, State__c, Total_Units__c, MDU_Category__c
                FROM SiteTracker_Projects__r)
        FROM Opportunity
        WHERE ({addr_conds}) OR ({name_conds}) OR ({agname_conds})
        LIMIT 50
    """
    return sf.query_all(soql)["records"]


def query_agreements_direct(t):
    # Agreement__c has no Name match on property — go via Opportunity relation
    name_conds = " OR ".join([f"Opportunity__r.Name LIKE '%{dq(k)}%'" for k in t["name_keys"]])
    soql = f"""
        SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
               Expiration_Date__c, Requested_Date__c,
               IronClad_ID__c, IronClad_URL__c, IronClad_Contract_Status__c,
               Opportunity__c, Opportunity__r.Name, Opportunity__r.StageName,
               Opportunity__r.Property_Address__c
        FROM Agreement__c
        WHERE {name_conds}
        LIMIT 50
    """
    return sf.query_all(soql)["records"]


def query_sitetracker_projects(t):
    name_conds = " OR ".join(
        [f"Site_Name__c LIKE '%{dq(k)}%'" for k in t["name_keys"]]
        + [f"Monday_Name__c LIKE '%{dq(k)}%'" for k in t["name_keys"]]
    )
    soql = f"""
        SELECT Id, Name, Site_Name__c, Monday_Name__c,
               Build_Status__c, Site_Status__c, PAL_Signed_Date__c,
               Activation_Actual__c, Activation_Forecast__c,
               City__c, State__c, Total_Units__c, MDU_Category__c,
               Opportunity__c, Opportunity__r.Name
        FROM SiteTracker_Project__c
        WHERE ({name_conds})
        LIMIT 50
    """
    return sf.query_all(soql)["records"]


def fmt_ags(ags):
    if not ags:
        return "        (no agreements)"
    lines = []
    for a in ags:
        signed = a.get("Signed_Date__c") or "unsigned"
        t = a.get("Agreement_Type__c") or "?"
        s = a.get("Status__c") or "?"
        ic = a.get("IronClad_ID__c") or ""
        icstage = a.get("IronClad_Contract_Status__c") or ""
        ic_str = f" | IC: {ic} ({icstage})" if ic else ""
        lines.append(f"        · {a.get('Name'):12} | {t:4} | Status: {s:10} | Signed: {signed!s:12}{ic_str}")
    return "\n".join(lines)


def fmt_sts(sts):
    if not sts:
        return "        (no ST projects)"
    lines = []
    for s in sts:
        sn = s.get('Site_Name__c') or s.get('Monday_Name__c') or s.get('Name')
        lines.append(
            f"        · {s.get('Name')} | {sn} | Build: {s.get('Build_Status__c')} | Site: {s.get('Site_Status__c')}\n"
            f"          PAL signed: {s.get('PAL_Signed_Date__c')} | Act A: {s.get('Activation_Actual__c')} | Act F: {s.get('Activation_Forecast__c')} | Units: {s.get('Total_Units__c')}"
        )
    return "\n".join(lines)


print("=" * 100)
print("AGREEMENT LOOKUP FOR 8 TARGET PROPERTIES  (main Salesforce org)")
print("=" * 100)

for t in TARGETS:
    print(f"\n{'█' * 100}")
    print(f"▶ {t['label']}  ({t['street']}, {t['city']})")
    print("█" * 100)

    # 1) Property_Location__c
    try:
        props = query_property_locations(t)
    except Exception as e:
        print(f"  [PL query error: {e}]")
        props = []
    print(f"\n  [1] Property_Location__c matches: {len(props)}")
    for p in props:
        flag = " [DELETED-FLAGGED]" if p.get("Import_Delete_Property__c") else ""
        print(f"    • {p.get('Name')} — {p.get('Property_Location_Name__c')}{flag}")
        print(f"      City: {p.get('City__c')}, {p.get('State__c')} | Status: {p.get('Property_Status__c')} | Type: {p.get('Property_Type__c')}")
        print(f"      Units total: {p.get('Property_Unit_Count__c')} / active: {p.get('Active_Unit_Count__c')} | FDH: {p.get('FDH_Name__c')} | Circuit: {p.get('Circuit_ID__c')}")
        print(f"      ROE Status: {p.get('ROE_Status__c')} | ROE Executed: {p.get('ROE_Executed__c')} | AAA Req: {p.get('Access_Agreement_Required__c')}")

    # 2) Opportunities
    try:
        opps = query_opportunities(t)
    except Exception as e:
        print(f"  [Opp query error: {e}]")
        opps = []
    print(f"\n  [2] Opportunity matches: {len(opps)}")
    seen_ag_ids = set()
    for o in opps:
        rt = (o.get('RecordType') or {}).get('Name')
        print(f"    • {o.get('Name')}  [{rt}]")
        print(f"      Stage: {o.get('StageName')} | Units: {o.get('Units__c')} | Cat: {o.get('Property_Category__c')} | Franchise: {o.get('Franchise_Type__c')}")
        print(f"      Addr: {o.get('Property_Address__c')}, {o.get('Property_City__c')}, {o.get('Property_State__c')} {o.get('Property_Zip__c')}")
        print(f"      Agreement_Name__c: {o.get('Agreement_Name__c')} | In_SiteTracker: {o.get('In_SiteTracker__c')} | Owner: {(o.get('Owner') or {}).get('Name')}")
        ags = (o.get("Agreements__r") or {}).get("records") or []
        for a in ags:
            seen_ag_ids.add(a.get("Id"))
        print(f"      Agreements ({len(ags)}):")
        print(fmt_ags(ags))
        sts = (o.get("SiteTracker_Projects__r") or {}).get("records") or []
        print(f"      SiteTracker Projects ({len(sts)}):")
        print(fmt_sts(sts))

    # 3) Extra Agreements (via Opp name LIKE)
    try:
        extra_ags = query_agreements_direct(t)
    except Exception as e:
        print(f"  [Ag query error: {e}]")
        extra_ags = []
    extra_ags = [a for a in extra_ags if a.get("Id") not in seen_ag_ids]
    if extra_ags:
        print(f"\n  [3] ADDITIONAL Agreement__c matches (via Opp name): {len(extra_ags)}")
        for a in extra_ags:
            opp = a.get("Opportunity__r") or {}
            print(f"    • {a.get('Name')} | {a.get('Agreement_Type__c')} | Status: {a.get('Status__c')} | Signed: {a.get('Signed_Date__c')}")
            print(f"      Opp: {opp.get('Name')} | Addr: {opp.get('Property_Address__c')}")

    # 4) ST projects that might be orphan (no Opp link)
    try:
        sts_all = query_sitetracker_projects(t)
    except Exception as e:
        print(f"  [ST query error: {e}]")
        sts_all = []
    # Filter out ones already shown under opps
    opp_ids = {o.get("Id") for o in opps}
    orphan_sts = [s for s in sts_all if not s.get("Opportunity__c") or s.get("Opportunity__c") not in opp_ids]
    if orphan_sts:
        print(f"\n  [4] ADDITIONAL SiteTracker_Project__c (no Opp link or different Opp): {len(orphan_sts)}")
        for s in orphan_sts:
            opp = s.get("Opportunity__r") or {}
            print(f"    • {s.get('Name')} | {s.get('Site_Name__c') or s.get('Monday_Name__c')}")
            print(f"      Build: {s.get('Build_Status__c')} | Site: {s.get('Site_Status__c')} | PAL: {s.get('PAL_Signed_Date__c')}")
            print(f"      Linked Opp: {opp.get('Name') or '(none)'}")

print("\n" + "=" * 100)
print("DONE")
print("=" * 100)
