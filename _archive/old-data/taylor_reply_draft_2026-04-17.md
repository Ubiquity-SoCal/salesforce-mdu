# Reply to Taylor — 4/17 follow-up

**Subject:** RE: Salesforce Requested Revisions / Points to discuss with BDMs 3/30

---

Hey Taylor — went through each of your follow-ups, hit them all below.

**Account multi-select — built it, your instinct was right**

Rather than a multi-select picklist (which loses the Account lookup and kills the ability to search / report by Account) I built a multi-tag relationship underneath. On the MDU Opportunity page there's now an "Accounts" related list on the left rail, right under Contacts. You can add as many Accounts as you want, each with an optional Role tag (Owner / Management Company / Portfolio / Other — leave blank if you don't know).

Search works across every tagged Account — if you search "Greystar" you'll find every Opp where Greystar is linked regardless of role. Same for "Blackstone" or any portfolio, mgmt co, or owner entity. That was the real goal, right?

I backfilled 109 Opps from the data already sitting in the old Account / Management Company / Portfolio fields — anything populated before is already tagged. The three old fields are off the MDU layout but still there on the object, nothing lost. Once you're comfortable with the new setup we can retire them for good.

One note: I'm also relabeling the standard "Account Name" field to "Primary Account" so it's clear it's the single anchor Account that feeds reports, SiteTracker sync, IronClad, etc. — distinct from the multi-tag list. The junction is for discovery and tagging; Primary Account stays the one SF-standard lookup.

**Closed Won — leaving as-is**

Business record type uses Closed Won, so I don't want to rename it globally. MDU reps will see the error once on their first Closed Won attempt and learn that Activation is the right end-state. If it becomes a recurring pain point we'll fork the stages by record type, but I don't want to do that preemptively.

**On Hold Reason — need your picklist values**

The validation rule (required when stage = On Hold) is ready to go, just need your preferred reasons for the picklist. I had some rough guesses but figured you'd know better since you see the real-world reasons deals get paused. Send me a list when you have a minute.

**Naming convention**

Yeah, address-as-name makes consistency tricky. Let me know if you want me to draft a first pass or if you want to take a crack at it.

**Living Units help icon**

Cleared. Field is just "Living Units" now, no icon.

Poke around the Accounts list on a few Opps and let me know if the shape works. Happy to tweak the Role picklist or add columns to what shows up inline.

Thanks,
Cass
