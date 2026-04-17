# MDU Opp Page Baseline — 2026-04-17

Immutable snapshot of the MDU Opportunity record page and related Classic layout + sibling FlexiPages, taken after restoring everything that was accidentally stripped during the Opportunity_Account__c junction rollout.

## What this page looks like (source of truth)

**Classic Layout — `Opportunity-MDU Opportunity Layout`**
- Opportunity Information section (Name, AccountId, Site Name, Stage, Sales Status, Hold Reason, Loss Reason, Owner, RE Assigned, Projected Close Date, Close Date, Agreement Count, Notes Count)
- Property Details section (Living Units, Property Type, Classification, Category, HOA, Build Type, Brownfield/Greenfield, Address fields)
- ISP Information (multi-select ISP, Incumbent fields)
- Integration Links (SiteTracker / IronClad)
- Migration Reference (Monday_Item_ID__c)
- System Information
- Related lists (7): Contacts, Agreements, SiteTracker, Notes, Content Notes, Files, **Accounts (Opportunity_Account__c)**

**Lightning FlexiPage — `MDU_Opportunity_Record_Page`** (Three Regions template)
- **leftsidebar:** highlights panel + related lists (Contacts, Accounts, Agreements, SiteTracker, etc.)
- **main:** path assistant + tabset (Details tab with 6 field sections)
- **rightsidebar:** Quick Links container + Activities panel + Attached Files

## Why this snapshot exists

On 2026-04-17 a `sf project retrieve start → edit → sf project deploy start` round-trip on the MDU layout *silently stripped* the Contacts / Agreements / SiteTracker / Notes / Files related lists (classic layouts lose content on round-trip). A second round-trip on the FlexiPage stripped the entire `rightsidebar` region (Activities, Quick Links, Attached Files). Users hadn't noticed yet — but will once the page is in active use.

Koa's directive: never lose this page layout again; only build on top of it.

## How to use this baseline

1. **Before any layout/FlexiPage change**, diff the live org's version against this snapshot so you know exactly what's there.
2. **Prefer minimal additive deploys** — don't retrieve the full file, edit, and redeploy. Only ship the fragment you're adding.
3. **If a round-trip is unavoidable**, always compare the retrieved file against this baseline and restore anything that went missing before redeploying.
4. Future deltas should produce a *new* dated baseline folder in `baselines/` — do not overwrite this one.

## Files

- `Opportunity-MDU Opportunity Layout.layout-meta.xml`
- `MDU_Opportunity_Record_Page.flexipage-meta.xml`
- `Business_Opportunity_Record_Page.flexipage-meta.xml`
- `Opportunity_Record_Page_Three_Column.flexipage-meta.xml`
