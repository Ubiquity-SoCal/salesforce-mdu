# "By Owner" Tab — Design Spec

**Status:** Draft — awaiting user review
**Date:** 2026-06-11
**Driver:** RE/sales leadership ask relayed by Koa (2026-06-11 email): *"the dashboard/report telling us the progress made by RE Owner for all the properties assigned to them for the entire portfolio."* To become a recurring weekly-meeting view. Koa's framing: "look at each active user and what they are actively working on," shown as three lifecycle tables.

## Goal

Add an at-a-glance view of every **active** RE owner's book of business, split into three lifecycle buckets (in-progress / dead / completed), so leadership can see who is working what and how far along it is — live, in Salesforce, refreshed on load.

## Placement

A new tab on `InsideSalesDashboard.page` (the Visualforce dashboard rendered by both the MDU_Sales and Inside_Sales apps), inserted after the existing `My Pipeline` tab (`data-tab="mine"`, line ~347).

- New tab label: **By Owner**
- New tab `data-tab` attribute: `byowner`
- Inherits the existing audience slicer (`All / MDU / Business ROE / Business Sales`) — re-renders on slicer change via `loadDashboard()`, same as every other tab.

## Scope / Universe

`Opportunity WHERE Owner.IsActive = true` + the active slicer's `rtFilter`.

- **Active owners only.** `Owner.IsActive = true` (SOQL-filterable, unlike the report builder). The inactive-owner backlog (Chuck/Jeff/Marty/duplicate-Brett, ~2,810 MDU opps) is intentionally excluded here — it is covered by the separate "CAT1 by Owner" reassignment report.
- **Consistent with the dashboard's in-network scope.** This tab applies the **same `rtFilter` + `catFilter` + `yrFilter`** as every other panel. In MDU view that means **Cat 1 only**, matching the page's *"In-network view: showing Cat 1 only"* banner — showing all categories on one tab would contradict that banner. The cross-category **entire portfolio** is reached via the **All** slicer, which drops `catFilter`. (Decision with Koa 2026-06-11.)
- `yrFilter` (`CreatedDate >= 2026-01-01`) is a **no-op for MDU** — all 3,613 MDU opps were created in 2026 (verified) — kept only so the tab matches the other panels.
- All stages, including closed/dead — the data is bucketed into the three tables below, not filtered out.

## Bucket Definitions (stage → table)

Each Opportunity's `StageName` maps to exactly one table. Bucket ③ reuses the page's existing per-pipeline `completedStagesList`, so it auto-adapts to the slicer.

| Table | MDU / Business ROE stages | Business Sales stages |
|---|---|---|
| **① Active / In Progress** | Prospects, Prospecting, Engaged, Proposal Sent, Contract Negotiations | Prospects, Prospecting, Engaged, Contract Negotiations |
| **② Closed Lost / On Hold** | Closed Lost, On Hold | Closed Lost, On Hold |
| **③ Activated / Completed** | PAL/ROE Complete, Marketing/Bulk In Progress, Marketing/Bulk Complete | Under Contract, Closed Won |

- **On Hold → table ②** (parked / not being actively worked). Confirmed with Koa 2026-06-11.
- **"Activated/Completed" is stage-based for v1** — i.e. the agreement is secured (PAL/ROE Complete onward). True build-level "activated" (SiteTracker activation date present) is a deferred enhancement (see Out of Scope). Confirmed with Koa 2026-06-11.
- Any stage not listed (defensive: e.g. a stray Business stage in the All view) falls into table ① so no record is silently dropped.

## Tab Content (3 stacked tables)

All three tables share the same shape: **one row per active owner**, **stage-count columns** for that bucket, a **Total** column, a **Living Units** (Σ `Units__c`) column, and a **grand-total row**. Each table is **sorted by Total (desc)** in v1 (interactive column-click sorting is deferred — see Out of Scope). Owners with zero rows in a bucket are omitted from that table.

```
① ACTIVE / IN PROGRESS                                  [All|MDU|BizROE|Biz]
Owner          Prosp Prspng Eng Prop Contr │ Total  Units
Bill Holick     251    0    11   2    7    │  271   43,9xx
Justin Barry     74    0     6   0    0    │   80   ...
…                                          │
GRAND TOTAL                                │
──────────────────────────────────────────────────────────
② CLOSED LOST / ON HOLD
Owner          Closed Lost  On Hold │ Total  Units
…
──────────────────────────────────────────────────────────
③ ACTIVATED / COMPLETED        (Business view: Under Contract · Closed Won)
Owner          PAL/ROE✓  Bulk-IP  Bulk✓ │ Total  Units
…
```

Column headers for table ① and ③ are driven by the active pipeline (so the Business slicer shows `Under Contract / Closed Won` in ③). Table ② is constant.

## Data Fetching

**One** aggregate SOQL appended to the existing `Promise.all([...])` array in `loadDashboard()`:

```javascript
SELECT Owner.Name ownerName, StageName, COUNT(Id) cnt, SUM(Units__c) units
FROM Opportunity
WHERE Owner.IsActive = true AND <yrFilter> <rtFilter> <catFilter>
GROUP BY Owner.Name, StageName
ORDER BY Owner.Name
```

- `<rtFilter>`, `<catFilter>`, `<yrFilter>` are the existing per-slicer fragments already computed at 4a — identical to what every other panel uses, so this tab's scope matches the rest of the dashboard (incl. the Cat 1 in-network filter in MDU view).
- Client-side `.then()` handler pivots the flat `(owner, stage, cnt, units)` rows into the three bucket tables using the bucket map above — same JS string-concat HTML pattern the other tabs use. No per-owner or per-stage extra SOQL.
- Reuses existing helpers: `query()`, `recs()`, `escHtml()`. Pure client-side aggregation.

## Audience Slicer Behavior

The slicer sets `currentPipeline` and calls `loadDashboard()`, which re-runs the whole `Promise.all` and re-renders all tab bodies — so the By Owner tab refreshes automatically on slicer change. No special listener.

- **MDU / Business ROE / Business** → render the 3 tables with that RT's stage columns.
- **All** → render the 3 tables across all RTs; table ③ uses the union `completedStagesList`; table ① uses the union of in-progress stages.

## Out of Scope (Deferred)

- **Interactive column-click sorting** (v1 sorts each table by Total desc).
- **Click-to-drill** into an owner's individual deals (inline expand or link to a filtered list). Easy follow-on.
- **State filter / slicer** on the tab (the manager's "bucketized by State status" — deferred; geographic-vs-stage meaning still unconfirmed).
- **True build "Activated"** — splitting table ③ into *Completed (agreement secured)* vs *Activated (SiteTracker build live, `Activation_Actual__c` present)*. The page already computes this in the Post-PAL panel; can be layered in later.
- **Amount column** — `Units__c` (doors) is the meaningful MDU measure; `Amount` is mostly $0 on MDU opps, so it's omitted.

## Implementation Order

1. Edit `InsideSalesDashboard.page`:
   - Add tab button after line ~347 (`data-tab="byowner"`).
   - Add the one aggregate SOQL to the `Promise.all` array.
   - Add a `renderByOwner()` block (3 tables + bucket pivot) and the tab-body container.
2. Deploy VF page (validate then deploy, like the CAT1 report).
3. Browser smoke test against ground-truth probe counts (below), per slicer.

## Testing

- No Apex (client-side JS only).
- Smoke test against the `_probes/2026-06-11-mdu-portfolio-by-owner-stage.py` numbers, e.g. MDU active owners: Bill 300, Justin 161, Rosemarie 147, Melissa 74, Tanya 71, active-Brett 45 — and that **no inactive owner appears** (Chuck/Marty/Jeff/inactive-Brett absent).
- Confirm bucket sums per owner equal that owner's total opp count.
- Toggle each slicer value; confirm column headers adapt (MDU shows PAL/ROE; Business shows Under Contract/Closed Won) and totals change.

## Open Questions (for spec review)

1. ~~Cat 1 vs entire portfolio~~ — **Resolved 2026-06-11:** match the dashboard (Cat 1 in MDU view, per the in-network banner); cross-category portfolio = All slicer.
2. ~~All-time vs year~~ — **Resolved 2026-06-11:** keep `yrFilter` for consistency (no-op for MDU anyway).
3. Tab name "**By Owner**" — ok, or prefer "RE Owners" / "Team Pipeline"?
