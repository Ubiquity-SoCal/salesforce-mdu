"""Verify Lit__c formula field deployed and populates consistently with the
raw OR clause it replaces."""
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Hawaiian1984",
    security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
)
UNIV = "Address_Type__c='Business' AND Import_Delete_Property__c=false"

raw = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {UNIV} AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)")["totalSize"]
formula = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {UNIV} AND Lit__c = true")["totalSize"]

print(f"Raw OR clause:    {raw} lit")
print(f"Lit__c=true:      {formula} lit")
assert raw == formula, f"Lit__c drift! raw={raw} formula={formula}"
print("OK: counts match.")
