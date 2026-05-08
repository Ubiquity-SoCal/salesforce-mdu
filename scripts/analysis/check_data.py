from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="Karate88!",
    security_token="Ktc1n9mLmD9vwEcVcl45q0iAD",
)

# === OPPORTUNITIES ===
print("=== OPPORTUNITIES ===")
result = sf.query("SELECT COUNT(Id) cnt FROM Opportunity")
print(f"Total: {result['records'][0]['cnt']}")

result = sf.query("SELECT COUNT(Id) cnt FROM Opportunity WHERE CreatedDate >= 2026-01-01T00:00:00Z")
print(f"Created in 2026: {result['records'][0]['cnt']}")

result = sf.query("SELECT Owner.Name, COUNT(Id) cnt, SUM(Amount) total FROM Opportunity GROUP BY Owner.Name")
print("\nBy Owner:")
for r in result["records"]:
    total = r["total"] or 0
    print(f"  {r['Name']}: {r['cnt']} opps, ${total:,.2f}")

result = sf.query("SELECT StageName, COUNT(Id) cnt, SUM(Amount) total FROM Opportunity GROUP BY StageName")
print("\nBy Stage:")
for r in result["records"]:
    total = r["total"] or 0
    print(f"  {r['StageName']}: {r['cnt']} opps, ${total:,.2f}")

result = sf.query("SELECT Name, StageName, Amount, CloseDate, Owner.Name, CreatedDate FROM Opportunity ORDER BY CreatedDate DESC LIMIT 5")
print("\nRecent opportunities:")
for r in result["records"]:
    amt = r["Amount"] or 0
    print(f"  {r['Name']} | {r['StageName']} | ${amt} | Close: {r['CloseDate']} | Owner: {r['Owner']['Name']}")

# === TASKS ===
print("\n=== TASKS ===")
result = sf.query("SELECT COUNT(Id) cnt FROM Task")
print(f"Total: {result['records'][0]['cnt']}")

result = sf.query("SELECT Status, COUNT(Id) cnt FROM Task GROUP BY Status")
print("\nBy Status:")
for r in result["records"]:
    print(f"  {r['Status']}: {r['cnt']}")

result = sf.query("SELECT Owner.Name, COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND CompletedDateTime >= THIS_WEEK GROUP BY Owner.Name")
print("\nCompleted this week by owner:")
for r in result["records"]:
    print(f"  {r['Name']}: {r['cnt']}")

result = sf.query("SELECT Owner.Name, COUNT(Id) cnt FROM Task WHERE Status = 'Completed' AND CompletedDateTime >= LAST_WEEK AND CompletedDateTime < THIS_WEEK GROUP BY Owner.Name")
print("\nCompleted last week by owner:")
for r in result["records"]:
    print(f"  {r['Name']}: {r['cnt']}")

# Check task subjects/types
result = sf.query("SELECT Subject, COUNT(Id) cnt FROM Task GROUP BY Subject ORDER BY COUNT(Id) DESC LIMIT 10")
print("\nTop task subjects:")
for r in result["records"]:
    print(f"  {r['Subject']}: {r['cnt']}")
