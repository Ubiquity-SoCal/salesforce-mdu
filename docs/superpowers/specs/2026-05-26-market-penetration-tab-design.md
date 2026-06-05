# Market Penetration Tab — Design Spec

**Status:** Draft — awaiting user review
**Date:** 2026-05-26
**Driver:** Pankaj (PMO meeting 2026-05-26). Action item: a Salesforce dashboard for footprint penetration with single-unit / multi-unit / un-lit ROE views, national + by state.

## Goal

Build a recurring, in-Salesforce surface for **business** property footprint penetration with three semantic sections (single-unit, multi-unit lit, ROE-completed-but-not-yet-lit). Initially scoped to Business; designed so MDU and SFU views can be slotted in later via the existing audience slicer.

## Placement

A new tab on `InsideSalesDashboard.page` (the Visualforce dashboard rendered by both the MDU_Sales and Inside_Sales (Business Sales) apps), inserted after the existing `Executive` tab.

- New tab label: **Market Penetration**
- New tab `data-tab` attribute: `marketpen`
- Inherits the existing audience slicer (`All / MDU / Business ROE / Business Sales`)
- Bookmark URL: same as today's dashboard, no new tab in app nav required

Initial scope is Business. When the audience slicer is set to anything other than Business / Business Sales / Business ROE, the tab body renders a placeholder ("Business penetration only for now — MDU/SFU coming") in lieu of the three sections.

## Universe

`Property_Location__c WHERE Address_Type__c = 'Business' AND Import_Delete_Property__c = false`

Confirmed count (2026-05-26): 17,034 records.
- 13,811 single-unit (`Property_Unit_Count__c = 1`)
- 3,223 multi-unit (`Property_Unit_Count__c > 1`)

## Key Definitions

| Term | Operational definition |
|---|---|
| **In footprint** | Any record passing the universe filter above. All have `FDH_Activated_Date__c` populated by virtue of the existing Vetro-to-SF sync rule. |
| **Lit** | `Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0`. A building counts as lit if at least one drop has been installed, active or churned. |
| **Single-unit** | `Property_Unit_Count__c = 1` |
| **Multi-unit** | `Property_Unit_Count__c > 1` |
| **ROE completed** | Has at least one `Agreement__c` row where `Status__c = 'Completed'` AND `Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')` AND parent `Opportunity__r.RecordType.DeveloperName = 'Business_ROE'` |
| **Single-unit penetration** | (Lit single-unit buildings) / (Total single-unit buildings) — building-level ratio |
| **Multi-unit door-weighted penetration** | SUM(`Active_Unit_Count__c`) across lit multi-unit / SUM(`Property_Unit_Count__c`) across lit multi-unit |

Verified data counts on 2026-05-26 (used as smoke-test ground truth):

- Lit (universe-wide, under the chosen `Active_Unit_Count > 0 OR Deactive_Unit_Count > 0` definition): **760 buildings** (494 single-unit, 266 multi-unit)
- Multi-unit lit door rollup: 2,329 total units, 492 active, 21.1% door-weighted
- Business PLs with completed ROE: 31
- Of those, NOT lit yet: 14 (9 single-unit, 5 multi-unit)

Note: the old standalone Business Penetration dashboard showed "Lit: 679" because it used `Penetration_Priority__c IN ('Category 1','All Active')` — a derived priority field that depends on the single-vs-multi-unit branch of `Priority__c`, not a direct read of unit counts. Switching to the direct definition (760) is intentional. Stakeholders comparing old vs new dashboards should be told the definition changed.

**Also differs from the 2026-05-22 Vetro/Databricks Excel** (`Serviceability_Lookup/data/output/business-penetration-2026-05-22.xlsx`, which showed 686 lit BBAs and 24,660 universe):
- Excel universe: serviceable BBAs from Vetro (24,660). New dashboard universe: SF Business Property_Locations (17,034) — gap of ~7,626 is the SF import rule that drops Vetro buildings with no FDH activation date (the Ariel Lake / FDH01AER pattern Pankaj raised in the 2026-05-26 PMO meeting).
- Excel lit count: 686. Dashboard lit count: 760. Gap of +74 is almost entirely California (Excel 6, dashboard 81): Excel's `addrstatus='serviceable'` filter excluded 75 CA Property_Locations that the dashboard includes because the dashboard's universe filter doesn't constrain on `addrstatus`. Most of these are legacy MDU-migration business addresses in Carlsbad/Encinitas/Solana Beach.
- AZ (12), NE (59), TX (608-609) match between Excel and dashboard.

Decision (2026-05-26 with Koa): keep the dashboard scope as-is (SF Business PL universe, any drop = lit). The divergence is real but intentional — the dashboard reflects the SF source of truth used by all other workflows. Future viewers comparing to the May 22 Excel will need this note.

## Schema Changes

**One new formula field** on `Property_Location__c`:

```
Lit__c
- Type: Checkbox (Formula)
- Formula: Active_Unit_Count__c > 0 || Deactive_Unit_Count__c > 0
- FLS: grant Read to System Administrator on deploy (per sf-customfield-fls-system-admin pattern)
- Description: "True if building has at least one drop installed (active or churned)."
```

No other field changes. The existing `Penetration__c` and `Penetration_Priority__c` formula fields stay untouched — they remain useful for the existing reports.

## Tab Content (3 vertical sections)

### Section 1 — Single-Unit Buildings

KPI row (3 tiles):
- Total single-unit buildings
- Lit single-unit buildings
- Single-unit penetration % (`lit / total`, building-level)

By-state table:

| State | Total | Lit | Penetration % |
|---|---|---|---|

### Section 2 — Multi-Unit Buildings

KPI row (5 tiles):
- Total multi-unit buildings
- Lit multi-unit buildings
- Total units in lit multi-unit buildings (sum of `Property_Unit_Count__c` where lit)
- Active units in lit multi-unit buildings (sum of `Active_Unit_Count__c` where lit)
- Door-weighted penetration % (`active units / total units in lit multi-unit`)

By-state table:

| State | Multi-Unit Buildings | Lit | Units in Lit | Active | Door-Weighted % |
|---|---|---|---|---|---|

### Section 3 — ROE Completed but Not Yet Lit

KPI row (3 tiles):
- Total properties (single + multi)
- Single-unit count
- Multi-unit count

Detail table (currently ~14 rows):

| Property | State | Units | Agreement | ROE Signed | Owner |
|---|---|---|---|---|---|

Table rows link to the Property_Location__c record (property column) and to the Agreement__c record (agreement column).

## Data Fetching

Three new SOQL queries appended to the existing `Promise.all([...])` array in `InsideSalesDashboard.page` (around lines 227-289):

```javascript
// Q-A: drives sections 1 + 2
SELECT Id, Property_Unit_Count__c, Active_Unit_Count__c, Deactive_Unit_Count__c,
       State__c                    // or whichever state field the page already uses
FROM Property_Location__c
WHERE Address_Type__c='Business' AND Import_Delete_Property__c=false

// Q-B: section 3 KPIs — Property_Locations with completed Business ROE
SELECT Property_Location__c, Property_Location__r.Property_Unit_Count__c,
       Property_Location__r.Active_Unit_Count__c, Property_Location__r.Deactive_Unit_Count__c
FROM Agreement__c
WHERE Status__c='Completed'
  AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
  AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
  AND Property_Location__c != null
  AND Property_Location__r.Address_Type__c='Business'
  AND Property_Location__r.Import_Delete_Property__c=false

// Q-C: section 3 detail table
SELECT Id, Name, Agreement_Type__c, Signed_Date__c, Status__c,
       Opportunity__r.Owner.Name,
       Property_Location__c, Property_Location__r.Name,
       Property_Location__r.Property_Unit_Count__c,
       Property_Location__r.Active_Unit_Count__c, Property_Location__r.Deactive_Unit_Count__c,
       Property_Location__r.State__c                  // or equivalent
FROM Agreement__c
WHERE Status__c='Completed'
  AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
  AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
  AND Property_Location__c != null
  AND Property_Location__r.Address_Type__c='Business'
  AND Property_Location__r.Import_Delete_Property__c=false
  AND Property_Location__r.Active_Unit_Count__c = 0
  AND Property_Location__r.Deactive_Unit_Count__c = 0
ORDER BY Signed_Date__c DESC NULLS LAST
```

Q-C uses the explicit "no drops" filter rather than referencing `Lit__c` so the query still works without the field present (defense-in-depth). Once `Lit__c` is verified live, this can be tightened to `Property_Location__r.Lit__c=false`.

Aggregation for state-level rollups happens client-side in the `.then()` handler, using the same JS string-concat HTML pattern the other tabs use. No per-state SOQL calls.

## Audience Slicer Behavior

The audience slicer buttons set the JS-global `currentRT` (or equivalent) and call `loadDashboard()` (defined around line 348). `loadDashboard()` re-runs the entire `Promise.all([...])` and the `.then()` re-renders every tab body. So the Market Penetration tab content is naturally refreshed whenever the slicer changes — no special event listener needed.

Render-time branching inside the Market Penetration tab body:

- If `currentRT` is the Business / Business Sales / Business ROE / All button → render the 3 sections
- Otherwise (MDU button) → render the placeholder block ("MDU/SFU view in development.")

When the slicer is on **All**, the dashboard still scopes Q-A/Q-B/Q-C to `Address_Type__c='Business'` (the universe of "in footprint" stays the business dataset until MDU/SFU views are added).

## Cleanup / Migration

After the tab is live and Pankaj has verified the numbers:

1. Delete the standalone native dashboard `01ZWR000004X6if2AC` (`Business_Penetration` in Inside Sales folder)
2. Optionally archive the `BizPen_*` reports under `PropertyReports` folder. Leave them for now — they're cheap to keep and sometimes useful for ad-hoc views.

The existing `Penetration__c` and `Penetration_Priority__c` formula fields are NOT removed.

## Implementation Order

1. Deploy `Lit__c` formula field on `Property_Location__c` with FLS to System Admin
2. One-off probe: confirm `Lit__c` count matches the OR-clause count (679 today)
3. Edit `InsideSalesDashboard.page`:
   - Add tab button at line ~312
   - Add 3 SOQL queries to the `Promise.all` array
   - Add render block for the tab body (3 sections + placeholder branch)
4. Deploy VF page
5. Smoke test in browser against ground-truth probe counts:
   - 13,811 single-unit / 3,223 multi-unit / 679 lit / 14 ROE-not-lit
   - Audience slicer placeholder triggers when MDU is selected
6. Wait 24-48 hrs of real use, then delete `01ZWR000004X6if2AC`

## Testing

- No Apex test changes (VF page is client-side JS)
- Manual smoke test against the probe numbers above
- Confirm `Lit__c` formula field shows on the Property_Location page layout (or at least is queryable for the dashboard)
- Re-run the field-coverage probe (`_probes/2026-05-26-property-location-lit-fields.py`) after deploy to confirm `Lit__c` populates as expected

## Out of Scope (Deferred)

- MDU + SFU penetration sections (requires defining "in footprint" for MDU at unit-level vs building-level, which Pankaj didn't specify and which is a separate clarification cycle with Taylor)
- Email subscription / scheduled snapshot to Pankaj
- Drill-down navigation from the tables (clickable property names jumping to Property_Location__c records — easy to add but not in scope for first cut)
- Time-series / month-over-month penetration trend (would require snapshotting; not asked for)

## Risk / Open Questions

- The verbal "lit = fiber to the building" in the PMO meeting clarified down to "lit = has any drop installed (active or churned)" via the question round. If Pankaj meant something stricter ("active customers only") or looser ("fiber reached the FDH"), the metric will need adjustment. Smoke-test the headline numbers with him before retiring the old dashboard.
- The state field on `Property_Location__c` is `State__c` (picklist) — verified 2026-05-26. The same VF page uses `Property_State__c` for `Opportunity` queries; the two are different fields on different objects, don't conflate.
- The future MDU/SFU expansion is sketched at the slicer level but not designed. When that work comes, the placeholder branch becomes the entry point for the MDU view's own queries + render block.
