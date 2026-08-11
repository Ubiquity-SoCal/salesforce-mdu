# SFU / Lit_Fiber Build Tracking — Findings (2026-06-15)

Investigation into whether SFU build progress can be surfaced in Salesforce the way
MDU build status is. Triggered by the Taylor weekly note: "SFU projects (a lot of
Justin's) won't link as-is." Conclusion below; **display format is still undecided
(parked).**

## Verdict: SFU build is NOT per-Opp linkable (by design)

The original premise — "the SiteTracker sync is MDU-only, so SFU won't link" — turned
out to be the wrong framing. Three hard facts:

1. **No SFU Opportunity record type exists.** Opp record types are MDU (3,613),
   Business_ROE (293), Business (198). Justin Barry's pursuits (mobile-home parks,
   HOAs) are already in SF under the **MDU** record type with MDU-style agreement
   names, e.g. `oceanside_mdu_laguna vista mobile estates`. There is no separate SFU
   Opp population waiting to be linked.

2. **SFU/lit build data lives on `Lit_Fiber__c` in the *separate* SiteTracker org**
   (4,163 rows), not `MDU_Fiber__c` (the object the daily sync reads). SFU-type sites
   have **0** `MDU_Fiber__c` children, so relaxing the sync's `Site_Type__c = 'MDU'`
   filter to include `'SFU'` would pull in nothing.

3. **`Lit_Fiber__c` is keyed at the network-element level, not the property level.**
   Site names are `STATE_CITY_SA##_FDH##` (e.g. `TX_KILLEEN_SA01_FDH01`). Site-type
   distribution: FDH 3,364, PAC 340, HUT 139 — Fiber Distribution Hubs / cabinets /
   head-ends, not buildings.

**Overlap test** (Lit_Fiber site/Monday names vs Opp `Name`/`Agreement_Name__c`):
- vs Justin's Opps: **0 matches**.
- vs **all 4,843** Opp keys: **6 matches (~0.1%)** — coincidental HOA names appended to
  FDH codes (e.g. `az_chandler_sa05_fbxx_knoxlandinghoa`).

Grain mismatch (one development = many FDHs; an FDH serves an area, not a building) plus
engineering-coded naming means **there is no usable join key.** Auto-linking like MDU
isn't feasible without a manual serving-area → pursuit mapping from Justin/Taylor.

## What IS buildable: an area-level SFU build funnel

Decoupled from Opps — rolled up by market — this is achievable.

**Data model:** `Lit_Fiber__c.Project__c` → `sitetracker__Project__c` →
`sitetracker__Site__c` (`Name` = `STATE_CITY_SA##_FDH##`, `Site_Type__c`, City).
Market via `Project__r.sitetracker__Program2__r.Name`.
(Note: SOQL relationship paths must NOT use field aliases — `SELECT Project__r.Name v …`
returns "Malformed request". Drop the alias.)

**Natural grain = market / program:** AZ_Mesa 583, DFW 474, Omaha 430, Killeen 264,
CA_Carlsbad 249, Georgetown 192, AZ_Chandler 191, CA_Encinitas 151, Santa Rita Ranch 116,
AZ_Gilbert 106, …

**Phase derivation — use the populated actual-date milestones only:**

| Milestone (actual) | Populated | Funnel stage |
|---|---|---|
| `Construction_Start_A__c` | 1,998 | Construction started |
| `Construction_Complete_A__c` | 1,917 | Construction complete |
| `FDH_Activation_A__c` | 1,398 | FDH activated (lit) |
| `Serving_Area_Activation_A__c` | 204 | SA activated |

Design-phase fields are effectively empty at this object level
(`High_Level_Design_Complete_A__c` 8, `Circuit_Design_A__c` 0), and `Market_Status__c`
is unused (4,133 blank). So the honest, data-backed funnel is:
**Pre-construction → Construction Started → Construction Complete → FDH Activated**
— *not* the MDU "Design / Construction / Completed" labels.

## Open decision (PARKED 2026-06-15)

How to display it — Koa undecided. Options considered:
- **A. Python → HTML or Google Sheet** — pull Lit_Fiber from the SiteTracker org, derive
  phase, render a by-market funnel. No cross-org sync; matches the dashboard pattern.
- **B. Native report/dashboard in the SiteTracker org** — build where the data lives;
  Justin/Taylor view it there. Zero sync, but it's the separate org.
- **C. Sync a Lit_Fiber rollup into the main org** — lightweight market-rollup sync +
  native SF report (like the MDU funnel). Most integrated, most work.

Resume by picking a format, then run brainstorm → spec → plan.

## Probe scripts (read-only, in `scripts/_probes/`)
- `2026-06-15-sfu-and-expiration-probe.py` — MDU vs SFU site types; Lit_Fiber discovery.
- `2026-06-15-sfu-linkability-probe.py` — Lit_Fiber shape; no SFU record type.
- `2026-06-15-sfu-linkability-probe2.py` — sitetracker__Project__c relationships.
- `2026-06-15-sfu-linkability-probe3.py` — corrected (un-aliased) overlap test.
