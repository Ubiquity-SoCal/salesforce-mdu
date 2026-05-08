"""
For the 8 target Opps, pull IronClad URLs + attached Files/Notes/Emails.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Opp Ids from the earlier run
OPPS = [
    ("Del Mar Beach Club",                  "Del Mar Beach Club"),
    ("Del Mar Shores Terrace",              "Del Mar Shores Terrace"),
    ("Las Brisas",                          "Las Brisas"),
    ("Seascape Chateau",                    "Solana Beach_MDU_Seascape Chateau"),
    ("Seascape Shores Condos",              "Solana Beach_MDU_Seascape Shores Condos"),
    ("Surfsong Condos",                     "Solana Beach_MDU_Surfsong Condos"),
    ("Oceanic Drive",                       "Oceanic Drive"),
    ("Portico At Rancho Carrillo",          "Portico At Rancho Carrillo HOA"),
]


def dq(s):
    return s.replace("'", "\\'")


for label, opp_name in OPPS:
    print(f"\n{'═' * 100}")
    print(f"▶ {label}  —  Opp: {opp_name}")
    print("═" * 100)

    # Get Opp Id
    q = sf.query(f"SELECT Id, Name FROM Opportunity WHERE Name = '{dq(opp_name)}' LIMIT 1")
    if not q["records"]:
        print("  [Opp not found]")
        continue
    oid = q["records"][0]["Id"]

    # Full Agreement details inc IronClad URL
    ags = sf.query_all(f"""
        SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
               Requested_Date__c, Expiration_Date__c,
               IronClad_ID__c, IronClad_URL__c,
               IronClad_Contract_Status__c, IronClad_Stage__c,
               Notes__c
        FROM Agreement__c WHERE Opportunity__c = '{oid}'
        ORDER BY CreatedDate
    """)["records"]
    print(f"\n  Agreements ({len(ags)}):")
    for a in ags:
        print(f"    • {a['Name']} | {a.get('Agreement_Type__c')} | Status: {a.get('Status__c')}")
        print(f"      Requested: {a.get('Requested_Date__c')} | Signed: {a.get('Signed_Date__c')} | Exp: {a.get('Expiration_Date__c')}")
        ic = a.get('IronClad_ID__c')
        if ic:
            print(f"      IronClad: {ic} | Stage: {a.get('IronClad_Stage__c')} | Status: {a.get('IronClad_Contract_Status__c')}")
            print(f"      URL: {a.get('IronClad_URL__c')}")
        if a.get('Notes__c'):
            print(f"      Notes: {a.get('Notes__c')[:200]}")

    # Content document links (Files)
    cdl = sf.query_all(f"""
        SELECT Id, ContentDocumentId, ContentDocument.Title, ContentDocument.FileType,
               ContentDocument.FileExtension, ContentDocument.ContentSize,
               ContentDocument.LatestPublishedVersion.VersionNumber,
               ContentDocument.CreatedDate
        FROM ContentDocumentLink WHERE LinkedEntityId = '{oid}'
    """)["records"]
    if cdl:
        print(f"\n  Attached Files ({len(cdl)}):")
        for c in cdl:
            cd = c.get("ContentDocument") or {}
            size = cd.get("ContentSize") or 0
            print(f"    • {cd.get('Title')}.{cd.get('FileExtension')} ({size:,} bytes) — {cd.get('CreatedDate')}")

    # Notes
    notes = sf.query_all(f"""
        SELECT Id, Title, Body, CreatedDate, CreatedBy.Name
        FROM Note WHERE ParentId = '{oid}'
        ORDER BY CreatedDate DESC
    """)["records"]
    if notes:
        print(f"\n  Notes ({len(notes)}):")
        for n in notes[:10]:
            body = (n.get('Body') or '')[:150].replace("\n", " ")
            print(f"    • [{n.get('CreatedDate')}] {n.get('Title')} — {(n.get('CreatedBy') or {}).get('Name')}")
            print(f"      {body}")

    # Emails
    emails = sf.query_all(f"""
        SELECT Id, Subject, FromAddress, ToAddress, MessageDate, HasAttachment
        FROM EmailMessage WHERE RelatedToId = '{oid}'
        ORDER BY MessageDate DESC LIMIT 20
    """)["records"]
    if emails:
        print(f"\n  Email Messages ({len(emails)}):")
        for e in emails:
            att = " [ATTACH]" if e.get("HasAttachment") else ""
            print(f"    • [{e.get('MessageDate')}] {e.get('Subject')}{att}")
            print(f"      from {e.get('FromAddress')} to {e.get('ToAddress')}")

print("\n" + "═" * 100)
print("DONE")
