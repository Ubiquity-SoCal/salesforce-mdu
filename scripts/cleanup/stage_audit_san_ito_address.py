from simple_salesforce import Salesforce
import base64
import re
import html as html_mod

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Pull both Opps' note text in full
for label, opp_id in [('San Ito', '006WR00000ywTezYAE'), ('Ito San', '006WR0000112vHHYAY')]:
    print(f"\n{'='*80}")
    print(f"{label} ({opp_id})")
    print('='*80)
    cdl = sf.query_all(f"SELECT ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId = '{opp_id}'")['records']
    for cd in cdl:
        try:
            cn = sf.ContentNote.get(cd['ContentDocumentId'])
            raw = cn.get('Content')
            if raw:
                txt = base64.b64decode(raw).decode('utf-8', errors='ignore')
                txt = html_mod.unescape(re.sub(r'<[^>]+>', ' ', txt))
                txt = re.sub(r'\s+', ' ', txt)
                print(f"  Title: {cn.get('Title')}")
                print(f"  Content: {txt[:1200]}")
        except Exception as e:
            print(f"  (could not fetch ContentNote: {e})")

# Also check the Ito San Agreement details
print(f"\n{'='*80}")
print("Ito San Agreement detail")
print('='*80)
agr = sf.query("""
    SELECT Id, Name, Opportunity__c, Opportunity__r.Name, Status__c, Agreement_Type__c,
           Signed_Date__c, IronClad_ID__c, Notes__c
    FROM Agreement__c WHERE Name = 'AGR-1434'
""")['records']
for a in agr:
    print(f"  {a['Name']}  Type={a['Agreement_Type__c']}  Status={a['Status__c']}  Signed={a['Signed_Date__c']}")
    print(f"  Notes: {a.get('Notes__c')}")

# Plus: how many CA MDU Merge Import notes exist on Opps that don't have their CA partner?
print(f"\n{'='*80}")
print("Looking for other potential CA MDU Merge orphans")
print('='*80)
# Pull all CA MDU Merge SNOTEs and the Opps they're on
cn = sf.query_all("""
    SELECT Id, ContentDocumentId, Title, CreatedDate
    FROM ContentVersion
    WHERE FileType = 'SNOTE' AND Title LIKE 'CA MDU Merge Import%'
    AND IsLatest = TRUE
""")['records']
print(f"Total 'CA MDU Merge Import' notes: {len(cn)}")
print("Sample of titles:")
for r in cn[:8]:
    print(f"  {r['Title']}")
