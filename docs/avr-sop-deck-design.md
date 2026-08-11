# AVR Process SOP Deck — Design

**Date:** 2026-07-01
**Owner:** Cass / UBQ GIS
**Deliverable:** An editable PowerPoint (`.pptx`) documenting the AVR process as-built, kept as a reference SOP.

## What an AVR is

**AVR = Address Verification Request.** A requestor (e.g. FiberFirst) submits an address;
the UBQ/GIS team verifies it against Vetro and resolves it one of three ways — the address is
**added**, **modified**, or **rejected**. Lives in the **Address Management** app in Salesforce,
tracked as **Cases**. Drives an auto-email back to the requestor on status change
(`MDU_Case_Notification` flow).

## Audience & goal

Process documentation / SOP — comprehensive, as-built, meant to be referred back to. Simple tone
(Koa's steer: "not much to be said, either an address gets added, modified or rejected").

## Build approach

`python-pptx` generator → native editable `.pptx`, embeds the actual screenshots at full fidelity,
re-runnable if the screens change. Clean, neutral visual with a Salesforce-blue accent.

- **Script:** `SalesForce/scripts/analysis/generate_avr_sop_deck.py`
- **Screenshots source:** `~/OneDrive - Ubiquity Management/Desktop/AVRs/*.png` (7 images)
- **Output:** `SalesForce/data/output/avr-process-sop.pptx` **and** a copy dropped in the Desktop
  `AVRs` folder next to the screenshots.

## Slide outline (9 slides, 16:9)

| # | Slide | Screenshot |
|---|-------|-----------|
| 1 | Title — "AVR Process · Address Verification Requests" | — |
| 2 | What is an AVR? (added / modified / rejected one-liner) | — |
| 3 | The AVR Lifecycle — email in → case auto-created → UBQ review vs Vetro → added/modified/rejected → auto-email → dashboard | — (drawn diagram) |
| 4 | Step 1 · Request comes in (email) | AVR Email received |
| 5 | Step 2 · Case auto-created | AVR Case Record |
| 6 | Step 3 · Review & set status | AVR Status |
| 7 | Step 4 · Auto-email on status change | AVR Auto Email |
| 8 | Tracking · Pipeline views | Open Cases + All Cases |
| 9 | Tracking · Summary dashboard | AVR Summary |

## Status → outcome mapping (slide 6)

Statuses grouped by the three real-world outcomes. Added + Modified roll up to the dashboard's
"Complete"; Rejected rolls up to "Invalid".

- **Added** — *Uploaded to Vetro*, *Pending Upload to Vetro*
- **Modified** — *Format Change Completed in Vetro*, *Omnia/CHR Changes Required*
- **Rejected** — *Invalid Address Request*, *Address Not in Network*, *Future / Unserviceable*, *See "Engineering / Add. Management Notes" Column*
- **Mid-workflow (not a final outcome)** — *Pending Review Board*, *Utilize Master List – Address Provided via Master List*, *Further Investigation Required*

> Note: the added/modified/rejected split of the picklist is inferred from the dashboard's
> "AVR Status Simplified" bucketing + the screenshots. Verify against the team's definitions.

## Visual system

- 16:9 (13.333 × 7.5 in). Clean white slides, Salesforce navy `#032D60` titles, Salesforce blue
  `#0176D3` accent, muted gray `#6B7280` support text.
- Outcome color coding: Added = green `#2E844A`, Modified = blue `#0176D3`, Rejected = red `#EA001E`.
- Every content slide: left accent rule, kicker label, title, footer with page number.
- Screenshots fit-to-box (aspect preserved), centered, subtle 1px gray border.

## Out of scope

- Prose definitions for each status (Koa: "just list them").
- Requestor-facing how-to, exec metrics narrative — this is the internal SOP only.
