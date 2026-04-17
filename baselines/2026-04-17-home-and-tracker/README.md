# Home Pages + Tracker App Pages Baseline — 2026-04-17

Immutable snapshot of the Lightning home pages, Tracker app pages, and the VisualForce dashboards that back them.

## Structure

Each Tracker / Home FlexiPage is a **thin wrapper** around a single component. The real layout lives in the wrapped component. Regressions happen when someone round-trips either the wrapper OR the backing VF page without understanding this.

### Home Pages (HomePage type)

- **`InsideSales_Home.flexipage-meta.xml`** — wraps VF page `InsideSalesDashboard`. Served as the home page of the MDU Sales app (API name `MDU_Sales`, label "MDU Sales"). Template: `industries_common:homeTemplateOneRegion`. Single region with a `flexipage:visualforcePage` pointing at `InsideSalesDashboard`, height 900.
- **`BusinessSales_Home.flexipage-meta.xml`** — Business Sales app home. Same shape.

### App Pages (AppPage type)

- **`MDU_Tracker.flexipage-meta.xml`** — wraps the `trackerGrid` LWC with `appContext=MDU_Sales`. Template: `flexipage:defaultAppHomeTemplate`.
- **`Business_Tracker.flexipage-meta.xml`** — same LWC, different context.
- **`Executive_Dashboard.flexipage-meta.xml`** — exec view.

### Backing VisualForce Pages

- **`InsideSalesDashboard.page`** (1,032 lines) — main MDU Sales dashboard. **Big**. Contains the full home-page grid, filters, charts, summaries.
- **`BusinessSalesDashboard.page`** (680 lines) — Business Sales equivalent.

## Why this snapshot exists

Koa's note 2026-04-17:

> "same for the home page and its current layout please understand the structure and settings as regressing is just hours min of wasted time"

Home Page regressions have happened before. The lesson from the Opp page disaster applies here too: round-trips can silently drop content, especially in VisualForce `<apex:*>` constructs and FlexiPage regions.

## How to use this baseline

1. Before touching *any* home page, tracker, or backing VF dashboard:
   - Diff the live org against this snapshot so you know exactly what's there.
2. For the VF pages (`.page` files), always prefer targeted edits (`Edit` tool on specific blocks), not whole-file rewrites.
3. For the FlexiPage wrappers, they're thin — if you edit one, the entire content is visible in under 40 lines. Diff against this baseline before deploying.
4. Future dated baselines go in new `baselines/YYYY-MM-DD-*/` folders. Never overwrite this one.

## Files

- `InsideSales_Home.flexipage-meta.xml`
- `BusinessSales_Home.flexipage-meta.xml`
- `MDU_Tracker.flexipage-meta.xml`
- `Business_Tracker.flexipage-meta.xml`
- `Executive_Dashboard.flexipage-meta.xml`
- `InsideSalesDashboard.page`
- `BusinessSalesDashboard.page`
