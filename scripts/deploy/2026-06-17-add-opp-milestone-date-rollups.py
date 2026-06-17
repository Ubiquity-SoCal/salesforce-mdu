"""Adds five Opportunity roll-up summary date fields: MAX(Agreement__c.Signed_Date__c)
filtered by Agreement_Type__c and Is_Signed__c=true. One per milestone type.
Pivots the per-type signed dates onto the Opportunity so the tracker report shows
them as columns on one row per property. Additive; rollups recalc automatically.

FLS granted to Admin + Standard User - Custom (rollups are read-only). The verification
retries because roll-up summary creation can recalc asynchronously."""
import time
from _md_deploy import connect, deploy

sf = connect()

# (api_name, label, agreement_type_value)
ROLLUPS = [
    ("PAL_Signed_Date__c",          "PAL Signed Date",          "PAL"),
    ("ROE_Signed_Date__c",          "ROE Signed Date",          "ROE"),
    ("EMA_Signed_Date__c",          "EMA Signed Date",          "EMA"),
    ("Bulk_Signed_Date__c",         "Bulk Signed Date",         "Bulk"),
    ("PAL_Addendum_Signed_Date__c", "PAL Addendum Signed Date", "PAL Addendum"),
]


def field_xml(api, label, atype):
    return f"""    <fields>
        <fullName>{api}</fullName>
        <label>{label}</label>
        <summarizedField>Agreement__c.Signed_Date__c</summarizedField>
        <summaryForeignKey>Agreement__c.Opportunity__c</summaryForeignKey>
        <summaryOperation>max</summaryOperation>
        <summaryFilterItems>
            <field>Agreement__c.Agreement_Type__c</field>
            <operation>equals</operation>
            <value>{atype}</value>
        </summaryFilterItems>
        <summaryFilterItems>
            <field>Agreement__c.Is_Signed__c</field>
            <operation>equals</operation>
            <value>True</value>
        </summaryFilterItems>
        <type>Summary</type>
        <description>MAX signed date of {atype} agreements (Status Completed/Cancelled + Signed Date) on this Opportunity. Built for the MDU Agreements Milestone Tracker.</description>
    </fields>"""


existing = [f["name"] for f in sf.Opportunity.describe()["fields"]]
todo = [r for r in ROLLUPS if r[0] not in existing]
if not todo:
    print("All five rollup fields already exist; skipping deploy.")
else:
    body = "".join(field_xml(*r) for r in todo)
    opp = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
           f'{body}\n</CustomObject>')
    if not deploy(sf, {"objects/Opportunity.object": opp},
                  [("Opportunity", "CustomObject")], "opp-rollups"):
        raise SystemExit(1)


# FLS read for Admin + the MDU team profile (rollups are read-only).
def fls_xml(profile_api):
    perms = "".join(
        f"<fieldPermissions><editable>false</editable>"
        f"<field>Opportunity.{api}</field><readable>true</readable></fieldPermissions>"
        for api, _, _ in ROLLUPS)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Profile xmlns="http://soap.sforce.com/2006/04/metadata">'
            f'{perms}</Profile>')


for prof in ["Admin", "Standard User - Custom"]:
    ok = deploy(sf, {f"profiles/{prof}.profile": fls_xml(prof)},
                [(prof, "Profile")], f"fls-{prof}")
    if not ok:
        print(f"  WARN: FLS deploy failed for '{prof}' (verify the profile name).")

# Verify a rollup matches the child data, retrying for async rollup recalculation.
sf2 = connect()
def c(q): return sf2.query(q)["records"][0]["c"]
missed = None
for attempt in range(12):
    try:
        missed = c("SELECT COUNT(Id) c FROM Opportunity WHERE Id IN "
                   "(SELECT Opportunity__c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Is_Signed__c=true) "
                   "AND PAL_Signed_Date__c = null")
    except Exception as e:
        print(f"  verify attempt {attempt + 1}: not queryable yet ({str(e)[:70]})")
        time.sleep(5); continue
    if missed == 0:
        break
    print(f"  verify attempt {attempt + 1}: {missed} opps pending rollup recalc; waiting...")
    time.sleep(5)
print(f"\nVerification: PAL-signed opps with null PAL_Signed_Date__c -> {missed} (expect 0)")
assert missed == 0, "A PAL-signed opp has a null PAL rollup — recalc/filters wrong!"
for api, _, _ in ROLLUPS:
    n = c(f"SELECT COUNT(Id) c FROM Opportunity WHERE {api} != null")
    print(f"   {api:<30} populated on {n} opps")
print("OK: rollups populate correctly.")
