"""For all 181 PAL/ROE Complete MDU Opps, scan Next_Action__c and Notes
text for EMA/Bulk-related keywords. Surface any that mention an EMA or Bulk
being in progress, even if no Agreement record reflects it."""
from simple_salesforce import Salesforce
from collections import defaultdict
import re
import base64
import html as html_mod

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

# Keyword patterns. Word-boundary matches to avoid false positives like "remap" containing "ma".
KEYWORDS = [
    re.compile(r'\bEMA\b', re.I),
    re.compile(r'\bbulk\b', re.I),
    re.compile(r'\bMSA\b', re.I),
    re.compile(r'\bNEMA\b', re.I),
]

rt = sf.query("SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='MDU'")['records'][0]['Id']
opps = sf.query_all(f"""
    SELECT Id, Name, Owner.Name, Sales_Status__c, Next_Action__c, Projected_Close_Date__c
    FROM Opportunity
    WHERE StageName='PAL/ROE Complete' AND RecordTypeId='{rt}'
""")['records']
print(f"Scanning {len(opps)} Opps")
ids = [o['Id'] for o in opps]
ids_str = "','".join(ids)
opp_map = {o['Id']: o for o in opps}

# Existing EMA/Bulk Agreement coverage (so we can subtract those — already known)
existing_emabulk = set()
for r in sf.query_all(f"""
    SELECT Opportunity__c FROM Agreement__c
    WHERE Opportunity__c IN ('{ids_str}') AND Agreement_Type__c IN ('EMA','Bulk','NEMA','MSA','EMA Addendum','Bulk Addendum','2nd ISP MSA Addendum')
""")['records']:
    existing_emabulk.add(r['Opportunity__c'])
print(f"Opps already having ANY EMA/Bulk Agreement child: {len(existing_emabulk)}")

# Find Opps where Next_Action mentions EMA/Bulk
hits = defaultdict(list)
for o in opps:
    txt = (o.get('Next_Action__c') or '')
    for kw in KEYWORDS:
        m = kw.search(txt)
        if m:
            hits[o['Id']].append(('Next_Action', kw.pattern, txt))
            break

# Pull notes via ContentDocumentLink/ContentVersion. Use TextPreview for the text.
cdl = sf.query_all(f"SELECT LinkedEntityId, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids_str}')")['records']
doc_to_opps = defaultdict(list)
for r in cdl:
    doc_to_opps[r['ContentDocumentId']].append(r['LinkedEntityId'])

# Notes: Salesforce ContentNote has Content (base64 html). For lightweight scan, TextPreview on ContentVersion is enough.
if doc_to_opps:
    docs_str = "','".join(doc_to_opps.keys())
    cv = sf.query_all(f"""
        SELECT Id, ContentDocumentId, Title, TextPreview, FileType, CreatedDate
        FROM ContentVersion WHERE ContentDocumentId IN ('{docs_str}') AND IsLatest = TRUE
    """)['records']
    for r in cv:
        text = (r.get('TextPreview') or '') + ' ' + (r.get('Title') or '')
        # ContentNote types may have null TextPreview; pull Content if needed (base64 html)
        if r.get('FileType') == 'SNOTE' and not r.get('TextPreview'):
            try:
                cn = sf.ContentNote.get(r['ContentDocumentId'])
                raw = cn.get('Content')
                if raw:
                    decoded = base64.b64decode(raw).decode('utf-8', errors='ignore')
                    text += ' ' + html_mod.unescape(re.sub(r'<[^>]+>', ' ', decoded))
            except Exception:
                pass
        for kw in KEYWORDS:
            m = kw.search(text)
            if m:
                for opp_id in doc_to_opps[r['ContentDocumentId']]:
                    hits[opp_id].append(('Note', kw.pattern, f"{r.get('Title')}: {text[max(0,m.start()-60):m.end()+60]}"))
                break

# Subtract opps already known via Agreement child
fresh_hits = {oid: h for oid, h in hits.items() if oid not in existing_emabulk}
print(f"Opps with EMA/Bulk text in Next_Action or Notes: {len(hits)}")
print(f"  Of those, NOT already covered by an EMA/Bulk Agreement child: {len(fresh_hits)}")

print()
print("=" * 100)
print("Opps with EMA/Bulk mentions but NO Agreement record for it")
print("=" * 100)
for opp_id, h in fresh_hits.items():
    o = opp_map[opp_id]
    print(f"\n{o['Name']}  Owner={o['Owner']['Name']}  Id={opp_id}")
    if o.get('Next_Action__c'):
        print(f"  Next_Action: {o['Next_Action__c']}")
    seen_titles = set()
    for src, kw, snippet in h[:6]:
        key = (src, kw, snippet[:80])
        if key in seen_titles: continue
        seen_titles.add(key)
        print(f"  [{src}] kw={kw}: {snippet[:300]}")
