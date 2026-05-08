# SiteTracker Connection Details

## Production
- **Username:** cass@ubiquitygp.com
- **Password:** Hawaiian84
- **Security Token:** fe2pen6ceQeqGhWXhBeOIjqP
- **Instance:** sitetracker-ubiquity.my.salesforce.com
- **Login URL:** https://login.salesforce.com

## Sandbox (uqpartial)
- **Username:** cass@ubiquitygp.com.uqpartial
- **Password:** Hawaiian84
- **Security Token:** kQnlsCgShQzdZTf0gb9DMv6Z
- **Instance:** sitetracker-ubiquity--uqpartial.sandbox.my.salesforce.com
- **Login URL:** https://test.salesforce.com
- **Setup URL:** https://sitetracker-ubiquity--uqpartial.sandbox.my.salesforce-setup.com/lightning/setup/SetupOneHome/home

## Python Connection

### Production
```python
from simple_salesforce import Salesforce
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='Hawaiian84',
    security_token='fe2pen6ceQeqGhWXhBeOIjqP'
)
```

### Sandbox
```python
from simple_salesforce import Salesforce
sf_st_sandbox = Salesforce(
    username='cass@ubiquitygp.com.uqpartial',
    password='Hawaiian84',
    security_token='kQnlsCgShQzdZTf0gb9DMv6Z',
    domain='test'
)
```

## Notes
- SiteTracker is a **separate Salesforce org** from the main Ubiquity org
- Sandbox is for testing push/update operations before running against prod
- Sandbox security token is independent from prod — resetting one doesn't affect the other
- If the security token stops working, reset it in the sandbox: Settings > My Personal Information > Reset My Security Token
