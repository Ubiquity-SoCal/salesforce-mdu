# Taylor Revisions Review — In-Progress State

**Date:** 2026-04-17
**Source email:** `C:\Users\cass\OneDrive - Ubiquity Management\Desktop\RE_ Salesforce Requested Revisions _ Points to discuss with BDMs 3_30.msg`
**HTML extracted:** `C:\Users\cass\Work_Projects\SalesForce\taylor_revisions_thread.html`
**Status:** Briefed Koa on green follow-ups. Awaiting decisions before building.

## Color Key in Thread
- **Red (#ee0000)** — Cass replies, 4/15 4:19pm
- **Purple (#7030a0)** — Taylor mid-thread updates, 4/15 1:02pm
- **Green (#196b24)** — Taylor NEW follow-ups, 4/17 7:05am ← what we're reviewing

## Five Green Action Items

### 1. Account multi-select (pushback)
Cass said single-select only. Taylor still wants multi-select on Opportunity Account so sales can tag multiple. Fallback: she'll write parameters distinguishing Account / Management Co / Portfolio.
- **Options:** (a) custom multi-select picklist of Accounts (loses lookup integrity), (b) junction object `Opportunity_Account__c` mirroring `Opportunity_Contact__c` pattern (cleanest), (c) keep single + give her the parameter doc.
- **Recommendation:** (b) if she truly needs multi.
- **Decision needed from Koa.**

### 2. Closed Won — does it ever apply to MDU?
Taylor asks if MDU opps ever hit Closed Won; if not, suggests renaming "Closed" stage to "Closed Lost".
- Current lifecycle ends at Activation → Closed.
- **Caveat:** Check Business record type — B2B may still need Closed Won.
- **Decision needed from Koa.**

### 3. On Hold Reason — required field
Parallel to Loss Reason on Closed Lost. Required when Stage = On Hold.
- **Plan:** New picklist `On_Hold_Reason__c` on Opportunity, validation rule requiring it when StageName = "On Hold".
- **Easy.** Need picklist values from Taylor (or propose defaults).

### 4. Naming convention
Taylor thinking out loud about property naming. **No action.**

### 5. Living Units info icon
Field renamed Units → Living Units, so the help icon is now redundant.
- **Plan:** Clear `inlineHelpText` on `Living_Units__c` (or whatever the API name is on Property_Location__c).
- **Trivial.**

## Suggested Build Order
5 (trivial) → 3 (small, needs picklist values) → 2 (decide first) → 1 (biggest, needs approach decision)

## Resume After Restart
1. Re-read this file
2. Re-read `taylor_revisions_thread.html` if you need the full thread context
3. Ask Koa which items to start on (or which decisions to firm up first)
