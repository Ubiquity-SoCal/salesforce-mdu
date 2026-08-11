# Salesforce Ops Transition Hub — Design

**Date:** 2026-07-02
**Status:** Approved, building
**Purpose:** A living, self-serve reference that helps whoever inherits Koa's Salesforce
work understand (a) everything we do to keep Salesforce updated and (b) how the org
itself is put together (apps, home page/LWCs, data model, integrations).

## Format
Single self-contained `.html` file. No build step, no external dependencies, works
offline, hand off by sending one file. Lives at
`SalesForce/docs/salesforce-ops-transition-hub.html`.

## Architecture (why it's "dynamic")
All content lives in one commented `SECTIONS` JavaScript array near the top of the file.
The sidebar index AND the content cards both render from that array at load time. Adding
a new sync or topic = add one object to the array and refresh the browser; the index
links, anchors, and section update themselves. A `HOW TO ADD AN ITEM` comment sits above
the data.

Data shape:
```
SECTIONS = [ { id, title, icon, blurb, items: [
  { name, tag?, systems?, summary, detail? }
] } ]
```
- `tag` drives a colored chip (Automated / Manual / Primary / Cross-check / Read-only / Historical).
- `summary` always visible (plain English). `detail` is HTML, shown in a collapsible
  "Technical detail" disclosure — the layered-depth approach so it serves technical and
  non-technical readers alike.

## Layout
- Left: sticky auto-generated index grouped by section, with a live type-to-filter box.
- Right: scrollable content, cards per item, section headers with icon.
- Top bar: title + last-updated date.

## Content sections
1. Orientation — two orgs, three apps, the Agreement_Name__c golden key
2. What keeps Salesforce updated — the sync inventory (automated + manual), run steps in detail
3. The three Salesforce apps
4. Home page & dashboards — InsideSalesDashboard VF page, campaignDashboard LWC, Tracker LWC, routing map + orphaned-component warning
5. Data model — Opportunity, Agreement, Opportunity_Contact, SiteTracker_Project, Property_Location/Unit
6. Integrations — IronClad, SiteTracker org, Databricks/Vetro, PowerBI, Stripe, Monday
7. Running it + tribal knowledge — code + secrets locations, GitHub Actions, don't-revert rules

## Accuracy guardrails
- Content sourced from verified code + current memory this session, not memory alone.
- Verified: cancelled builds now INCLUDED in the ST mirror (filter removed 2026-05-26);
  home-page routing renders InsideSalesDashboard, executiveDashboard LWC is orphaned;
  current restructured stage names (not the old project-note stages).
- Resolved: Databricks/Vetro property sync is PRIMARY; PowerBI is the secondary cross-check.
- Anything still uncertain is marked inline rather than asserted.

## Out of scope
- No live SF API calls (static reference).
- Not a slide deck (chose HTML hub over PPTX for the dynamic clickable index).
