"""
Verify OpportunityContactRollupTrigger against REAL production data, not just the test
context. Apex tests run in an isolated data sandbox; this proves the trigger fires on the
actual org with the actual validation rules and the other two Opportunity triggers active.

Sequence (net zero change, fully reversible):
  1. pick a real Opportunity with Contact_Count__c blank (nobody linked)
  2. link an existing Contact with Role = Property Manager  -> expect count 1, primary set
  3. link a SECOND contact with Role = Property Owner       -> expect count 2, primary flips
  4. link the SAME owner again (duplicate)                  -> expect count STILL 2
  5. delete all three links                                 -> expect fields back to null

Also re-checks idempotency: re-saving an untouched junction row must not change anything.
"""
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from simple_salesforce import Salesforce  # noqa: E402
from enrich_omaha_onnet_mdus import creds  # noqa: E402

sf = Salesforce(*creds())
created = []
failures = []


def state(oid):
    o = sf.query(
        "SELECT Primary_Contact__c, Primary_Contact_Role__c, Contact_Count__c "
        f"FROM Opportunity WHERE Id='{oid}'"
    )["records"][0]
    return o["Primary_Contact__c"], o["Primary_Contact_Role__c"], o["Contact_Count__c"]


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}\n         got={got}\n         want={want}")
    if not ok:
        failures.append(label)


try:
    opp = sf.query(
        "SELECT Id, Name FROM Opportunity "
        "WHERE Contact_Count__c = null AND Property_State__c = 'NE' "
        "AND StageName = 'Closed Lost' LIMIT 1"
    )["records"][0]
    contacts = sf.query("SELECT Id, Name FROM Contact LIMIT 2")["records"]
    mgr, owner = contacts[0], contacts[1]
    print(f"opportunity : {opp['Name']} ({opp['Id']})")
    print(f"contact A   : {mgr['Name']}\ncontact B   : {owner['Name']}\n")

    check("baseline: no contacts", state(opp["Id"]), (None, None, None))

    r = sf.Opportunity_Contact__c.create(
        {"Opportunity__c": opp["Id"], "Contact__c": mgr["Id"], "Role__c": "Property Manager"})
    created.append(r["id"])
    check("after 1 manager link", state(opp["Id"]), (mgr["Id"], "Property Manager", 1))

    r = sf.Opportunity_Contact__c.create(
        {"Opportunity__c": opp["Id"], "Contact__c": owner["Id"], "Role__c": "Property Owner"})
    created.append(r["id"])
    check("owner outranks manager", state(opp["Id"]), (owner["Id"], "Property Owner", 2))

    r = sf.Opportunity_Contact__c.create(
        {"Opportunity__c": opp["Id"], "Contact__c": owner["Id"], "Role__c": "Property Owner"})
    created.append(r["id"])
    check("duplicate link does NOT inflate count", state(opp["Id"]),
          (owner["Id"], "Property Owner", 2))

    # idempotency: touch a link without changing anything
    sf.Opportunity_Contact__c.update(created[0], {"Role__c": "Property Manager"})
    check("re-save is idempotent", state(opp["Id"]), (owner["Id"], "Property Owner", 2))

    for lid in created:
        sf.Opportunity_Contact__c.delete(lid)
    created = []
    check("all links deleted -> fields cleared", state(opp["Id"]), (None, None, None))

finally:
    for lid in created:
        try:
            sf.Opportunity_Contact__c.delete(lid)
            print(f"  cleaned up stray link {lid}")
        except Exception as e:
            print(f"  COULD NOT CLEAN UP {lid}: {e}")

print("\nALL PASS" if not failures else f"\nFAILURES: {failures}")
