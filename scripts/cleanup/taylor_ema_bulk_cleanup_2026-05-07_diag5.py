"""Why did Opportunity__c re-parent fail on these objects?"""
from simple_salesforce import Salesforce

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

for obj in ('Opportunity_Contact__c', 'Agreement__c'):
    print(f'\n=== {obj}.Opportunity__c ===')
    desc = getattr(sf, obj).describe()
    for f in desc['fields']:
        if f['name'] == 'Opportunity__c':
            keys = ['name', 'type', 'updateable', 'createable', 'nillable',
                    'restrictedDelete', 'cascadeDelete', 'writeRequiresMasterRead',
                    'permissionable', 'controllerName']
            for k in keys:
                print(f'  {k}: {f.get(k)}')
            print(f'  relationshipName: {f.get("relationshipName")}')
            print(f'  referenceTo: {f.get("referenceTo")}')

# Check FLS on System Admin profile
print('\n=== Tooling API: FieldPermissions on System Admin profile ===')
from simple_salesforce.api import Salesforce as SfApi
res = sf.toolingexecute("query/?q=" +
    "SELECT+SobjectType,Field,PermissionsRead,PermissionsEdit,Parent.Profile.Name"
    "+FROM+FieldPermissions"
    "+WHERE+Field+IN+('Opportunity_Contact__c.Opportunity__c','Agreement__c.Opportunity__c')"
    "+AND+Parent.Profile.Name='System+Administrator'")
print(res)
