# MDU Agreements Milestone Tracker — Design Spec

**Date:** 2026-06-17
**Project:** SalesForce (MDU Sales)
**Status:** Approved design, pending spec review → implementation plan

## Origin

Stakeholder request (forwarded by Koa, Taylor CC'd): an **MDU Agreements tracker for all
opportunities where we have a Signed PAL/ROE**, showing the critical milestones from an
agreement perspective. Requested items:

- Sales POC
- Total units
- Address
- State
- SiteTracker project #
- Design Phase completion date (from SiteTracker)
- PAL/ROE signed date
- EMA signed date
- Bulk Agreement signed date
- PAL addendum signed date

Taylor was invited to suggest additional dates.

## Decision summary

- **Vehicle:** a native Salesforce **report** (not Excel/LWC). Refreshable, exportable, lives
  with the data, no runtime code.
- **Grain:** one row per **Opportunity** (property), not per agreement. This is what makes it a
  milestone *timeline* instead of a per-agreement list.
- **Enabler:** the four/five signed-date milestones each live on a separate `Agreement__c` child
  record (distinguished by `Agreement_Type__c`). To show them as columns on a single Opportunity
  row, we add per-type **roll-up summary date fields** on the Opportunity. `Agreement__c` is
  master-detail to Opportunity, so these are native roll-ups (no Apex).
- **PAL and ROE are SEPARATE columns** (Koa, 2026-06-17) — can be combined later if needed.
- **Sales POC = Opportunity Owner** (Koa, 2026-06-17) — the assigned salesperson.
- **Design Phase completion date is a FAST-FOLLOW (v2)** (Koa, 2026-06-17). It is not in the
  SiteTracker mirror today; v1 ships with the nine other columns, v2 extends the sync.
- **Contacts: two role columns** (Koa, 2026-06-17) — **Property Manager** and **Property Owner**
  (the only two `Opportunity_Contact__c` roles with real data), kept fresh by a **native
  record-triggered Flow**. Sequenced after the core report so v1 value lands first.
- **"Signed" definition reuses Taylor's** (her 2026-05-22 rule, she owns this logic): an
  agreement counts as signed when `Status__c ∈ {Completed, Cancelled}` **and** `Signed_Date__c`
  is populated. This keeps the new tracker reconciled with her existing "MDU/SFU PALs/ROEs"
  dashboard.

## Relationship to existing work (do not duplicate)

A sibling already exists: the **"MDU/SFU PALs/ROEs"** report + dashboard built for Taylor
(2026-05-21/22, see `palroe-completed-dashboard` memory). It is **agreement-grain** (one row per
agreement, deduped PAL-priority) and serves a **signed-PAL/ROE census** purpose — different grain
and purpose from this per-property milestone timeline, so it is not a substitute.

What we reuse from it:
- SiteTracker is already surfaced onto the Opportunity: `ST_Build_Status__c`,
  `ST_Activation_Actual__c`, kept fresh by `surface_to_opportunity.py` in the Automation repo.
- The signed-agreement concept (`Is_Signed_PAL__c`, `Signed_PAL_Date_Count__c`) and Taylor's
  signed definition.

The new per-type date roll-ups added here are also reusable on Taylor's dashboard later.

## v1 — New metadata

### Agreement__c.Is_Signed__c (formula, checkbox)
Encodes Taylor's signed definition once, reused by every roll-up filter:

```
AND(
  OR(ISPICKVAL(Status__c, "Completed"), ISPICKVAL(Status__c, "Cancelled")),
  NOT(ISBLANK(Signed_Date__c))
)
```

References only `Agreement__c`'s own fields, so it is valid as a roll-up summary filter field.

### Opportunity roll-up summary date fields
Each is `MAX(Signed_Date__c)` over child `Agreement__c` records filtered by
`Agreement_Type__c = <type>` AND `Is_Signed__c = true`:

| Field (API) | Label | Agreement_Type filter |
|---|---|---|
| `PAL_Signed_Date__c` | PAL Signed Date | PAL |
| `ROE_Signed_Date__c` | ROE Signed Date | ROE |
| `EMA_Signed_Date__c` | EMA Signed Date | EMA |
| `Bulk_Signed_Date__c` | Bulk Signed Date | Bulk |
| `PAL_Addendum_Signed_Date__c` | PAL Addendum Signed Date | PAL Addendum |

`MAX` is used so that if a type has multiple signed records, the latest signed date wins.

Naming note: confirm at build that none of these API names collide on the Opportunity. The
SiteTracker mirror has its own `SiteTracker_Project__c.PAL_Signed_Date__c`, but that is on a
different object and is not surfaced to the Opportunity, so there is no collision.

### Field-level security
Grant read on all new fields to the **Standard User - Custom** profile (the MDU team) so report
viewers see populated columns.

## v1 — Contacts (two role columns), sequenced after the core report

**Data reality (live probe 2026-06-17):** of 441 MDU opps with a signed PAL/ROE, only **72 (16%)**
have any `Opportunity_Contact__c` attached. The two roles that carry data are **Property Owner**
(387 junction records org-wide) and **Property Manager** (297); all other roles (Leasing, Broker,
HOA, Legal, Developer) are sparse. So these columns will be **mostly blank today** — they add value
for the 72 populated opps and double as a prompt for the team to backfill contacts. This is a
data-population gap, not a report defect.

Roll-up summaries can only count/sum/min/max — they **cannot concatenate text** — so contact names
are materialized onto the Opportunity by a Flow:

- `Opportunity_Contact__c.Contact_Name__c` — formula text: `Contact__r.Name`. Lets the Flow read
  the contact's name from the junction's own field (no cross-object access inside the Flow).
- `Opportunity.Property_Manager_Contact__c` — Text(255). Comma-joined names of attached
  Property Manager contacts.
- `Opportunity.Property_Owner_Contact__c` — Text(255). Comma-joined names of attached
  Property Owner contacts.
- **Flow** (record-triggered, *create or update*, after-save, on `Opportunity_Contact__c`):
  re-aggregates the parent Opp's two fields from all sibling junction records by role. Keeps the
  columns live as contacts are added/changed.
- **One-time backfill script** populates the existing 72 opps immediately (the Flow only fires on
  future edits) and serves as the manual resync tool (e.g. after a contact is *removed* — delete
  handling is intentionally **not** in the Flow per YAGNI, given removals are rare; resync via the
  backfill).
- FLS read on the two Opportunity fields granted to `Admin` + `Standard User - Custom`.

## v1 — The report

- **Report type:** standard **Opportunities** (all columns resolve on the Opportunity after the
  roll-ups + the already-surfaced SiteTracker fields).
- **Folder:** MDU Sales Reports.
- **Name (≤40 chars):** `MDU Agreements Milestone Tracker`.
- **Filter:** `RecordType = MDU` **AND** (`PAL_Signed_Date__c ≠ blank` **OR**
  `ROE_Signed_Date__c ≠ blank`). Filter logic: `1 AND (2 OR 3)`.
- **Format:** Tabular (a true list/tracker), sortable.
- **Columns** (requester order, with usability extras):
  1. Sales POC — Opportunity Owner (`Owner.Name`)
  2. Property Manager — `Property_Manager_Contact__c` *(contacts phase)*
  3. Property Owner — `Property_Owner_Contact__c` *(contacts phase)*
  4. Property (Opportunity Name) *(usability extra)*
  5. Total Units — `Units__c`
  6. Address — `Property_Address__c`
  7. State — `Property_State__c`
  8. SiteTracker Project # — `SiteTracker_Project_ID__c`
  9. Stage — `StageName` *(usability extra)*
  10. ST Build Status — `ST_Build_Status__c` *(usability extra, already surfaced)*
  11. PAL Signed Date — `PAL_Signed_Date__c`
  12. ROE Signed Date — `ROE_Signed_Date__c`
  13. EMA Signed Date — `EMA_Signed_Date__c`
  14. Bulk Signed Date — `Bulk_Signed_Date__c`
  15. PAL Addendum Signed Date — `PAL_Addendum_Signed_Date__c`
  - *(v2 column, deferred: Design Phase Completion Date)*
  - Columns #2–#3 (contacts) are added in the contacts phase, after the core report is verified.
  - Usability extras (#4, #9, #10) are easy to drop if the requester wants a strict match.
- **Optional variant:** a summary-format copy grouped by State that sums Total Units. Not built
  in v1 unless requested.

## v2 — Design Phase completion date (fast-follow, sequenced after v1)

Self-contained; does not block v1. Steps:
1. Confirm the design-milestone field on `MDU_Fiber__c` in the **SiteTracker org** (the actual
   design-phase completion/"design complete" actual-date field; naming to verify live).
2. Add a `Design_Complete_Date__c` field to the `SiteTracker_Project__c` mirror object.
3. Add it to the mirror sync query + upsert in `sync_sitetracker.py` (currently pulls only PAL
   date, activation forecast/actual, build status — see the script's `to_upsert` block).
4. Surface it onto the Opportunity (extend the surfacing pattern used for `ST_Build_Status__c` /
   `ST_Activation_Actual__c`, i.e. `surface_to_opportunity.py` in the Automation repo) so it is
   reportable at Opportunity grain.
5. Add the **Design Phase Completion Date** column to the report.

## Verification (no unit tests for metadata)

- Pick a property whose `Agreement__c` children include signed PAL + EMA + Bulk; confirm each
  Opportunity roll-up shows the correct date.
- Confirm the report population reconciles to Taylor's signed census (~447 signed PAL/ROE opps as
  of 2026-05-22); investigate any material delta.
- Spot-check 3–5 opps' date columns against their `Agreement__c` children directly.
- After roll-up creation, confirm the fields back-fill (Salesforce recalculates on save).
- **Contacts:** after backfill, confirm an opp with a known Property Manager/Owner shows the
  expected names; functionally test the Flow by adding a test `Opportunity_Contact__c` and
  confirming the parent field updates (then remove it and resync via backfill).

## Gotchas to honor during build

- **`enableReports` foot-gun:** whenever the `Agreement__c` object header is redeployed (e.g. to
  add `Is_Signed__c`), it MUST include `<enableReports>true</enableReports>` or Allow Reports
  silently resets to false and breaks the `OpportunityCustomEntity$Agreement__c` report type (and
  every report on it). See `sf-report-dashboard-metadata-gotchas` / `palroe-completed-dashboard`.
- **Roll-up filter on a formula checkbox** (`Is_Signed__c`) is allowed because it references only
  same-object fields. Verify at deploy.
- **Audit/log everything** per the SF batch-op convention if any data is touched (this build is
  metadata + report only, so no record mutation expected).

## Out of scope (v1)

- A dashboard for this tracker (Taylor's existing dashboard already serves the census view; a
  dedicated dashboard can be a later add).
- Combining PAL+ROE into one column (kept separate per Koa).
- Sending any email. A reply to the requester/Taylor (what's in v1, the design-phase fast-follow,
  and a request for Taylor's additional dates) will be prepared as a **draft only**, never sent.
