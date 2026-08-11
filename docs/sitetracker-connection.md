# SiteTracker Connection Details

## Production
- **Username:** cass@ubiquitygp.com
- **Password:** <password: see _shared/sf_auth.py org=st>
- **Security Token:** <token: see _shared/sf_auth.py org=st>
- **Instance:** sitetracker-ubiquity.my.salesforce.com
- **Login URL:** https://login.salesforce.com

## Sandbox (uqpartial)
- **Username:** cass@ubiquitygp.com.uqpartial
- **Password:** <password: see _shared/sf_auth.py org=st>
- **Security Token:** <token: see _shared/sf_auth.py org=st>
- **Instance:** sitetracker-ubiquity--uqpartial.sandbox.my.salesforce.com
- **Login URL:** https://test.salesforce.com
- **Setup URL:** https://sitetracker-ubiquity--uqpartial.sandbox.my.salesforce-setup.com/lightning/setup/SetupOneHome/home

## Python Connection

### Production
```python
from simple_salesforce import Salesforce
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='<password: see _shared/sf_auth.py org=st>',
    security_token='<token: see _shared/sf_auth.py org=st>'
)
```

### Sandbox
```python
from simple_salesforce import Salesforce
sf_st_sandbox = Salesforce(
    username='cass@ubiquitygp.com.uqpartial',
    password='<password: see _shared/sf_auth.py org=st>',
    security_token='<token: see _shared/sf_auth.py org=st>',
    domain='test'
)
```

## Notes
- SiteTracker is a **separate Salesforce org** from the main Ubiquity org
- Sandbox is for testing push/update operations before running against prod
- Sandbox security token is independent from prod — resetting one doesn't affect the other
- If the security token stops working, reset it in the sandbox: Settings > My Personal Information > Reset My Security Token
