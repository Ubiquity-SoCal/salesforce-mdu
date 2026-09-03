# Salesforce to HubSpot: migration brief

Prepared 2026-08-31, from the live org (Generate Ubiquity Services LLC, `fun-power-747`).
Companion to the two workbooks in `SalesForce/data/output/`:

- `salesforce-hubspot-field-map.xlsx` - every field on every in-scope object, with type,
  required flag, picklist values, what it links to, and how full it actually is. Blank
  HubSpot Property / HubSpot Type / Migrate? / Notes columns on each tab for the mapping.
- `salesforce-hubspot-sample-records.xlsx` - four real records read end to end, parent plus
  every related child, so the shape of a live record is visible rather than described.

Source: the 8/31 "Salesforce to Hubspot" call. Three buckets were agreed there: get the
data across, rebuild the workflows, then repoint the syncs. This brief covers what the
workbooks cannot say on their own.

## The org in one page

| App | Object | Records | Note |
|---|---|---|---|
| MDU Sales | Opportunity | 4,174 | The property deal. 4 record types, 133 fields. |
| MDU Sales | Agreement__c | 1,312 | Signed PAL / ROE / marketing agreements. |
| MDU Sales | Contact | 1,070 | Linked via a junction, see trap 1. |
| MDU Sales | Account | 619 | Management companies. Only 419 opps carry an AccountId. |
| MDU Sales | IronClad__c | 2,017 | Contract mirror, synced twice a week. |
| MDU Sales | SiteTracker_Project__c | 479 | Construction mirror, nightly. |
| Address Mgmt | Property_Location__c | 18,161 | The physical property, address backbone. |
| Address Mgmt | Property_Unit__c | 46,502 | Units inside a property. |
| Address Mgmt | Case | 269 | The AVR (Address Validation Request) workflow. |

820 fields across the 19 in-scope objects. 89 are completely empty and 109 more are under
5% populated, so roughly 24% of the field surface is a drop candidate rather than a mapping
job. Those rows are shaded in the field map.

## Six things that will bite an import

**1. Contacts do not use OpportunityContactRole.** The standard object has 1 row in the
whole org. The real link is `Opportunity_Contact__c`, a custom junction, with 931 rows. Any
contact migration that follows the standard Salesforce relationship comes back empty.

**2. Opportunity Name is not unique and is not the join key.** 45 names are used more than
once, covering 147 records. Two properties genuinely share a name in several cases. The
cross-system key is `Agreement_Name__c`, but it is null on 2,995 of 4,174 opportunities, so
it cannot be the primary key either. Migrate on Salesforce Id and keep it in a HubSpot
field, so a record can still be traced back after cutover.

**3. "Business Sales" is out of scope. "Business ROE" is not.** These are two different
record types and the names are close enough to be dangerous.

| Record type | Opps | Modified since 8/01 | Owners |
|---|---|---|---|
| MDU/SFU | 3,646 | 3,630 | Brett Spivey, Chuck McNeely, Jeff Chao |
| Business ROE | 315 | 22 | Rosemarie Shortino, Tanya Friese, Justin Barry |
| Business Sales | 199 | 0 | Julian Harrell, Shane Lowry (Sales Focus, the departed vendor) |

Business Sales is genuinely dormant and was correctly deprioritised on the call. Business
ROE is live: Rose and Tanya are working those TX and NE addresses right now, and 22 moved
in the last month. Dropping anything matching "Business" would take out active pipeline.

**4. Validation rules will fight the import.** 21 active rules, several of which lock fields
once populated (`Lock_IronClad_ID`, `Lock_IronClad_Record`, `Lock_Status_When_IronClad_Linked`,
`Prevent_Opportunity_Name_Change`) or require a field conditionally (`Require_Loss_Reason_Closed_Lost`,
`Require_Hold_Reason_On_Hold`, `Require_City_State_Zip_On_New_MDU`). They are listed on the
Automation tab. This matters mostly for any write back into Salesforce during a parallel-run
period, not for reads.

**5. 70% of opportunities are owned by deactivated users.** 2,928 of 4,174. Only 1,246 sit
with an active user. HubSpot has no user to map those to, and the default behaviour is to
dump them all on whoever runs the import, which destroys the ownership history.

| Inactive owner | Opps |
|---|---|
| Brett Spivey (`brett1`) | 937 |
| Chuck McNeely | 739 |
| Jeff Chao | 544 |
| Marty Samuels | 403 |
| Julian Harrell | 178 |
| Jeff Wickersham | 95 |
| Shane Lowry, Jerry Lumpkin, Jose Varela, Scott Avanzo | 32 combined |

This needs a decision before migration: either create inactive placeholder owners in HubSpot,
or reassign to the people actually working the pipeline, or write the original owner name to
a plain text field and assign everything to a house account. The third option is the cheapest
and loses the least.

**Related, and it corrects an assumption from the 8/27 call.** There are two Brett Spivey
users, not one:

- `brett1@ubiquitygp.com`, created 2026-03-10, inactive, **has never logged in**, owns 937 opportunities.
- `brett2@ubiquitygp.com`, created 2026-04-28, **active, last login 2026-08-12**, owns 177 opportunities.

On the 8/27 call the read was that Brett "didn't even log in for like 3 months" and so the
reassign was held. That describes the duplicate `brett1` account. The real account logged in
on 8/12, fifteen days before that call, so the login data does not support the conclusion
that he has left. Worth confirming with HR before anything is reassigned, and the duplicate
account is worth cleaning up regardless.

**6. The custom behaviour does not import at all.** 6 Apex triggers, 14 record-triggered
flows, 21 validation rules and 17 Apex classes. Every one is a rebuild-or-drop decision, not
a field mapping. This is the part that was called out on the 8/31 call as the thing that
takes time, and the Automation tab is the list to work through.

## Bucket three: the syncs

These write into Salesforce today. Each needs repointing at HubSpot or retiring. This is the
bucket with the least visibility, because most of it runs unattended.

| Source | Writes to | Cadence | Matched on |
|---|---|---|---|
| SiteTracker | SiteTracker_Project__c, Opportunity | Nightly, GitHub Actions cron | Site name / Agreement_Name__c |
| IronClad | IronClad__c, Agreement__c | Twice a week | `IronClad_Id__c`, not Name |
| Vetro | Property_Location__c, Property_Unit__c | Ad hoc refresh | Address / agreename |
| COS (FiberFirst) | Serviceability reporting | Ad hoc | external_address_id |
| Requestor Email Extract | Case (AVR) | On inbound email | n/a, parses 16 fields in one update |
| Databricks dashboards | Reads Salesforce | Scheduled | n/a |
| Monday.com | Opportunity | Retired 2026-06-01 | n/a |

The two custom Lightning apps (the Tracker grid and Address Management) are the daily UI for
the remaining sales team. They are not integrations, but they are how the data actually gets
entered, and there is no equivalent in HubSpot out of the box.

## Timeline risk

The call put the target at mid-September, tied to the California approval plus roughly ten
days to close. That is achievable for moving data across. It is not achievable for the
automation list above, and the two are easy to conflate in a status update. Recommend
splitting the commitment: data in HubSpot by mid-September, automation rebuilt on its own
schedule, with Salesforce kept read-only rather than turned off until the automation list is
actually closed out.

## Access

Kia Zaman (`kzaman@fiberfirst.com`, Id `005WR00000LDFzdYAH`) was created 2026-08-31, System
Administrator profile, active, invite sent.

The profile alone was not enough. This org does not grant System Administrator field-level
security on custom fields automatically, which left 17 fields invisible to her, including
`Tracker_View__c.Config__c` (the JSON defining the Tracker grid columns she offered to
rebuild) and `Opportunity.Property_Location__c` (the link between the MDU Sales and Address
Management sides). Assigning `SMB_RE_Field_Access` and `Tracker_Admin` on 2026-08-31 closed
it: she now reads all 483 in-scope fields, matching Koa exactly.

Worth remembering for any future admin onboarding here, this is the same FLS trap that has
bitten metadata deploys in this org before.

## Open items

- The consultant's HubSpot side: a custom "MDU property name" field, rebuilt column set, and
  a few contacts moved across as a test.
- A HubSpot walkthrough session for Koa, to be scheduled once the connection is live.
- Owner mapping decision for the 2,928 opportunities owned by deactivated users (trap 5).
- Confirm Brett Spivey's employment status before reassigning anything, and clean up the
  duplicate `brett1` account.
