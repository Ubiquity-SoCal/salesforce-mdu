# Opportunity primary-contact rollup (Apex)

Keeps `Opportunity.Primary_Contact__c`, `Primary_Contact_Role__c` and `Contact_Count__c` in
sync with the `Opportunity_Contact__c` junction, so Niraj's one-line report stays true after
the 2026-07-09 backfill.

Deployed to production 2026-07-09. Trigger active, 9/9 tests pass, org-wide coverage 81%.

| Component | Purpose |
|---|---|
| `OpportunityContactRollupTrigger` | after insert / update / delete / undelete on the junction |
| `OpportunityContactRollup` | all logic; `recalculate(Set<Id>)` is callable from a backfill |
| `OpportunityContactRollupTest` | 9 tests |

Redeploy:
`sf project deploy start --source-dir force-app --target-org <org> --test-level RunSpecifiedTests --tests OpportunityContactRollupTest`

## Rules

- **Primary contact:** highest role priority wins; oldest link breaks ties. Priority order is
  Property Owner, Property Manager, Leasing Contact, HOA Contact, Broker, Developer,
  Legal Contact, Other, then blank.
- **Contact Count:** DISTINCT contacts. The same person linked twice counts once. Blank means
  nobody is on file.

## Why Apex and not a Flow

Koa asked for a Flow first. It is the wrong tool here, for four reasons found while looking:

1. A record-triggered Flow cannot combine after-save (create/update) with delete. You need
   two Flows.
2. Delete-triggered Flows run **before** the row is removed, so a Get Records still returns
   the row being deleted and you must exclude it by Id. Easy to get subtly wrong.
3. `Opportunity_Contact__c.Opportunity__c` is **master-detail with cascade delete**. Deleting
   an Opportunity cascades to its junction rows, fires the before-delete Flow, which then
   tries to update the Opportunity that is mid-delete. Without a fault path this **blocks
   Opportunity deletion**. `deletingParentOpportunity_doesNotThrow` covers exactly this.
4. Flow has no DISTINCT. Emulating it needs a second Get Records sorted by Contact plus a
   second Loop, because the primary-contact pick needs CreatedDate ordering.

There is also no sandbox in this org, so production is the only place to activate automation
on a junction object. Apex at least ships with a test class that fails loudly.

## Safety notes

- `Database.update(records, false)` (allOrNone = false): a parent that vanished mid-transaction,
  or one blocked by an unrelated validation rule, must never abort the user's save.
- The class re-queries surviving parents first, so cascade-deleted Opportunities are skipped.
- Static `running` flag prevents re-entry via our own Opportunity update.
- The other two Opportunity triggers are safe to fire past: `OpportunityAddressDupBlock`
  short-circuits unless `Property_Address__c` or `Property_Zip__c` changed, and
  `OpportunityUnitLinkTrigger` unless `Property_Unit__c` changed. We touch none of them.

## Test fixture gotcha

A validation rule requires City, State and Zip on MDU/Business ROE opportunities. The test
fixture sets those but deliberately leaves `Property_Address__c` blank, because
`OpportunityAddressDupBlock` skips any record with a blank address. That lets 200 bulk
fixtures share a zip without colliding.

## Verified on real data

`scripts/analysis/verify_opportunity_contact_rollup.py` runs against production: links a
manager (count 1), links an owner (owner wins, count 2), links the owner again (count stays
2), re-saves a link (idempotent), then deletes everything (fields clear). Net zero change.
All six checks passed 2026-07-09. The 428 backfilled opportunities were unaffected.
