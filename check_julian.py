from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Karate88!",
    security_token="Ktc1n9mLmD9vwEcVcl45q0iAD",
)

r = sf.query(
    "SELECT Name, CreatedDate, StageName, Amount "
    "FROM Opportunity WHERE Owner.Name = 'Julian Harrell' "
    "AND IsClosed = false ORDER BY CreatedDate"
)
for rec in r["records"]:
    amt = rec["Amount"] or 0
    print(f"  {rec['CreatedDate'][:10]} | {rec['Name']} | {rec['StageName']} | ${amt}")
print(f"\nTotal: {r['totalSize']}")
