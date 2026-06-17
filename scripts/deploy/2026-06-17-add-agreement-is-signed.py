"""Adds Agreement__c.Is_Signed__c (formula checkbox) encoding Taylor's 2026-05-22
signed definition: Status in (Completed, Cancelled) AND Signed_Date populated.
Drives the per-type signed-date rollups on Opportunity (Task 2). Additive.

Org-specific note: formula Checkbox fields on Agreement__c deployed via the Metadata
REST API land in the Tooling layer but are NOT SOQL-queryable until a Profile or
PermissionSet grants explicit Read FLS. The Admin Profile grant below is required.
Double-quotes in <formula> XML must be &quot;-escaped or Salesforce silently drops
the formula and the field shows as a plain non-formula Checkbox."""
from _md_deploy import connect, deploy

sf = connect()

# Object header MUST include <enableReports>true</enableReports> (foot-gun: omitting it
# silently disables Allow Reports and breaks the Opportunities-with-Agreements report type).
AGR_HDR = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label><pluralLabel>Agreements</pluralLabel>
    <nameField><label>Agreement Number</label><displayFormat>AGR-{0000}</displayFormat><type>AutoNumber</type></nameField>
    <sharingModel>ControlledByParent</sharingModel><deploymentStatus>Deployed</deploymentStatus>
    <enableReports>true</enableReports>
    <fields>
        <fullName>Is_Signed__c</fullName>
        <label>Is Signed</label>
        <type>Checkbox</type>
        <formula>AND(OR(ISPICKVAL(Status__c, &quot;Completed&quot;), ISPICKVAL(Status__c, &quot;Cancelled&quot;)), NOT(ISBLANK(Signed_Date__c)))</formula>
        <description>True when an agreement Status is Completed/Cancelled and has a Signed Date (Taylor 2026-05-22 signed definition). Drives the Opportunity per-type signed-date rollups.</description>
    </fields>
</CustomObject>"""

# Admin Profile FLS: required to make the field SOQL-queryable via REST API on this org.
# Formula fields on Agreement__c are not visible to describe/SOQL without explicit FLS.
ADMIN_FLS = """<?xml version="1.0" encoding="UTF-8"?>
<Profile xmlns="http://soap.sforce.com/2006/04/metadata">
    <fieldPermissions>
        <editable>false</editable>
        <field>Agreement__c.Is_Signed__c</field>
        <readable>true</readable>
    </fieldPermissions>
</Profile>"""

existing = [f["name"] for f in sf.Agreement__c.describe()["fields"]]
if "Is_Signed__c" in existing:
    print("Is_Signed__c already exists; skipping deploy.")
else:
    ok = deploy(sf, {"objects/Agreement__c.object": AGR_HDR},
                [("Agreement__c", "CustomObject")], "agr-is-signed")
    if not ok:
        raise SystemExit(1)
    # Grant Admin Profile FLS so field is SOQL-queryable (see module docstring).
    ok_fls = deploy(sf, {"profiles/Admin.profile": ADMIN_FLS},
                    [("Admin", "Profile")], "agr-is-signed-fls")
    if not ok_fls:
        raise SystemExit(1)

# Verify the formula matches the raw SOQL definition.
sf2 = connect()
def c(q): return sf2.query(q)["records"][0]["c"]
flag = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Is_Signed__c = true")
raw  = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Status__c IN ('Completed','Cancelled') AND Signed_Date__c != null")
print(f"\nVerification: Is_Signed__c=true -> {flag} ; raw definition -> {raw} (expect equal)")
assert flag == raw, "Is_Signed__c does not match the raw signed definition!"
print("OK: Is_Signed__c matches the signed definition.")
