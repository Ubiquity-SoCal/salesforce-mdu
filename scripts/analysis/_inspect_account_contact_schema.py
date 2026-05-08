"""Pull Account, Contact, Opportunity_Contact__c schemas + sample to plan field mapping."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from simple_salesforce import Salesforce

sf = Salesforce(username='cass1@ubiquitygp.com', password='Hawaiian1984', security_token='IBSKT6CFUpSUJWxq1CMm0HkFC')

OBJECTS = ['Account', 'Contact', 'Opportunity_Contact__c', 'Opportunity']
INTERESTING = ['Type', 'AccountType', 'Account_Type', 'Phone', 'Email', 'Owner', 'Manage',
               'LLC', 'Property', 'Mgmt', 'Primary', 'Role', 'Title', 'Description']

for obj in OBJECTS:
    print(f"\n{'='*70}\n{obj}\n{'='*70}")
    try:
        d = getattr(sf, obj).describe()
    except Exception as e:
        print(f"  ERROR: {e}")
        continue
    rts = [r for r in d.get('recordTypeInfos', []) if r.get('available') and not r.get('master')]
    if rts:
        print(f"\n  Record Types:")
        for rt in rts:
            print(f"    {rt['developerName']:40s} {rt['name']:30s} default={rt['defaultRecordTypeMapping']}")
    print(f"\n  Custom + interesting fields:")
    for f in d['fields']:
        n, label, t = f['name'], f['label'], f['type']
        is_custom = n.endswith('__c')
        is_interesting = any(k.lower() in n.lower() or k.lower() in label.lower() for k in INTERESTING)
        if is_custom or is_interesting:
            extra = ''
            if t == 'picklist':
                vals = [v['value'] for v in f.get('picklistValues', []) if v.get('active')]
                if vals:
                    extra = f"  values={vals[:8]}{'...' if len(vals)>8 else ''}"
            print(f"    {n:45s} {label[:35]:35s} {t:12s}{extra}")
