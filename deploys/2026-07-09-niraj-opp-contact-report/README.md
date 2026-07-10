# Niraj's opportunity + contact + ownership reports

Built 2026-07-09 from the "Salesforce Download" call. Niraj Patel asked for "an opportunity
list and our owners, the status owner, and then just a name and the property management
data" so he can judge whether the closed-lost population is really closed.

## The deliverable

**`NE TX Opportunities Primary Contact`** - one row per property. This is the one to send.

- Report Id `00OWR00000Lpk6L2AR`
- <https://fun-power-747.lightning.force.com/lightning/r/Report/00OWR00000Lpk6L2AR/view>
- 1,067 rows = 1,067 opportunities. 335 show a contact, 732 show none.
- Shows the single highest-priority contact plus `Contact Count` for how many exist in total.

**`NE TX Opportunity Contacts and Ownership`** - every contact, one row each. Drill-down only.

- Report Id `00OWR00000Lpbiz2AB`
- 1,345 rows for the same 1,067 opportunities (the extra 278 rows are 2nd, 3rd... contacts).

Redeploy both: `sf project deploy start --source-dir force-app --target-org <org>`

## Supporting schema

Deployed separately in `../2026-07-09-opp-primary-contact-fields/`:

| Field | Type | Populated by |
|---|---|---|
| `Opportunity.Primary_Contact__c` | Lookup(Contact) | backfill script, then a Flow |
| `Opportunity.Primary_Contact_Role__c` | Text(60) | same |
| `Opportunity.Contact_Count__c` | Number(3,0) | same |

FLS was granted separately (`scripts/deploy/2026-07-09-fls-primary-contact-fields.py`) by
mirroring `Property_Category__c`. The Metadata API does not grant admins FLS on new fields.

**Primary contact rule** (Koa, 2026-07-09): highest role priority wins, oldest link breaks
ties. Priority: Property Owner, Property Manager, Leasing Contact, HOA Contact, Broker,
Developer, Legal Contact, Other, blank.

`Contact_Count__c` is deliberately **not** a roll-up summary. A roll-up counts junction
rows, and 62 (opportunity, contact) pairs are linked twice, so it would report 2 where one
person is listed twice. The backfill counts distinct Contact ids instead.

Backfill: `scripts/sync/backfill_opportunity_primary_contact.py` (dry-run default,
`--limit N` smoke test, rollback CSV to `data/output/audit_logs/`). Ran 2026-07-09:
428 opportunities updated, 0 failures, verified by re-read.

### Kept current automatically

`OpportunityContactRollupTrigger` (see `../2026-07-09-opp-primary-contact-apex/`) recomputes
all three fields on junction insert / update / delete / undelete. Deployed 2026-07-09, 9/9
tests pass, verified against live production data. Nothing depends on Koa's SoCal account.

## Filter, and why it is not "Category = Cat 1"

```
Property_State__c    equals    NE,TX
Property_Category__c notEqual  Cat 2,Cat 3
```

Both filters are run-page editable, so Niraj can change state or category without cloning.

`Property_Category__c` is **blank on 50.7% of NE/TX Closed Lost**. Filtering `= Cat 1` drops
278 of 548 closed-lost records and 44 of the 171 soft closed-lost (No Contact Info /
Non-Responsive) - precisely the population Niraj wants to re-approach. Blank means "never
categorized", not "not Cat 1". Excluding known Cat 2/3 keeps 93.2% of closed-lost while
still cutting 508 known-ineligible rows.

Note also: **every OnNet opp is already Cat 1** (121 of 121), so `Cat 1 OR OnNet` is
identical to `Cat 1` and adds nothing. `MDU_Categorization__c` and `Property_Category__c`
are different fields - see the `mdu-categorization-field` note.

## Gotchas hit while building

- A report references a custom report type with a `__c` suffix
  (`MDU_Opportunities_with_Contacts__c`) even though the ReportType metadata has none.
  Wrong name fails with the unhelpful `invalid report type`.
- The Metadata API rejects the column tokens that `/analytics/reportTypes/<name>` advertises,
  so both reports were created through the Analytics REST API and retrieved back to source.
- Reports created via the Analytics API default to `scope: "user"` ("My opportunities").
  That returned 21 rows instead of 1,345. Always set `scope: "organization"` and check the
  row count against SOQL.
- Report types only expose columns you declare. `OwnerId` / `AccountId` are invalid; declare
  the relationship name (`Owner`, `Account`, `Primary_Contact__c.Account`).
- Salesforce caps report names at 40 characters.
- Opportunity has two active triggers: `OpportunityAddressDupBlock` (before update, can
  reject) and `OpportunityUnitLinkTrigger` (after update). The backfill therefore touches
  only the 428 opportunities that have contacts, not all 4,152.

## What the report exposes

- 1,239 of 1,575 NE/TX opportunities (79%) have no linked contact at all.
- Of 611 NE/TX contact links, 59% have no Account, so "property management company" is
  mostly blank.
- 16.5% have a company crammed into the person-name field (`HARVEST DEVELOPMENT LLC`).
- Role priority cannot rescue junk: the 6-contact Omaha opp `ROE - 6237 N 89TH CIR` now
  shows a Property Owner literally named "Water Damage", because that link is the oldest.

The emptiness of this report is the finding, not a defect in it.

## Cleanup queued, not applied

Koa chose to flag rather than auto-delete. `scripts/analysis/build_contact_hygiene_review.py`
(read-only) writes `data/output/contact-hygiene-review-2026-07-09.xlsx` for Rosemary:

| Sheet | Rows |
|---|---|
| Duplicate Links | 64 redundant rows across 62 pairs |
| Orphan Links | 4 junction rows with no Contact |
| Junk Primary Contacts | 235 |

## Open

Niraj's Salesforce **Export button reportedly does nothing** (he has
`PermissionsExportReport=True`, so it is likely client-side). Confirm he can actually export
before treating this as landed.
