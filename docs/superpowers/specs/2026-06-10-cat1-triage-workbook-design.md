# CAT1 Triage Workbook — Design

**Date:** 2026-06-10
**Status:** Approved (design)
**Author:** Work Claude + Koa

## Purpose

One-time Excel workbook to drive the CAT1 opportunity cleanup. It lists every
open CAT1 opportunity, classifies *why each isn't being worked* from its
Salesforce notes, and gives editable columns for the team to mark an assignment
or a "can't be worked" Pursuit Status. The workbook is the working artifact for
the meeting; a bulk update back into Salesforce is a **separate, later** step
(out of scope here) that the editable columns are shaped to feed.

## Context

- 192 of the 696 open CAT1 opps are owned by **inactive users** (Chuck McNeely,
  Marty Samuels, Jeff Chao, Jeff Wickersham, + a disabled Brett Spivey login).
- Reading the 1,666 notes on those 192 showed they are not all neglected live
  deals: ~67 already won/built, ~59 legitimately dead/blocked (the biggest
  driver = an existing Bulk contract with a competitor), ~5 route, ~61 genuinely
  workable but orphaned.
- `Substatus__c` (label **"Pursuit Status"**) is the SF field that classifies an
  opp as stuck/not-workable; setting it drops the opp out of the active-work
  view. Its 7 values map closely to the note-derived buckets.

## Scope

- **In:** generate the workbook from a live SF pull + the notes categorizer.
- **Out (deferred):** writing decisions back to SF (bulk owner reassign /
  Pursuit Status set). Likely a follow-on script.

## Architecture

- `SalesForce/scripts/lib/cat1_notes.py` — categorization logic extracted from
  the probe (`_probes/2026-06-10-cat1-notes-categorize.py`) into a reusable
  module: the keyword `RULES`, `categorize()`, note-text `clean()`, the
  action-group rollup, and the note-story → Pursuit-Status suggestion map. One
  source of truth shared by the workbook and any later bulk-update.
- `SalesForce/scripts/analysis/cat1_triage_workbook.py` — re-runnable generator:
  1. Connect to main SF org (`api/Salesforce_Credentials.txt`).
  2. Pull all open `Property_Category__c = 'Cat 1'` opps with context fields +
     `Owner.IsActive`.
  3. Pull ContentNotes (ContentDocumentLink → ContentVersion `TextPreview`).
  4. Categorize each opp (Action Group, Note Story, snippet, Suggested Pursuit
     Status) via `cat1_notes`.
  5. Write the workbook with `openpyxl`.
- **Output:** `SalesForce/data/output/2026-06-10-cat1-triage.xlsx`.

## Workbook structure

### Sheet `Triage`
One row per opp, sorted *inactive-owner first → Action Group → State*. Frozen
header row, autofilter on all columns.

- **Context (read-only):** Opp Name · Opp link (Lightning URL) · Owner ·
  Owner Active? · Stage · current Pursuit Status · State · City · Units ·
  Agreements · IronClad? · Created · Last Modified
- **From notes (read-only):** Action Group (A Done / B Dead / C Route /
  D Workable) · Note Story (12 categories) · Note snippet (evidence) ·
  Suggested Pursuit Status (a real `Substatus__c` value, **advisory only**)
- **Editable (data-validation dropdowns):** Proposed Owner (blank; dropdown of
  active reps) · Proposed Pursuit Status (blank; dropdown of the 7 real values) ·
  Decision / notes (free text)

Action Group is conditionally color-coded. The Suggested column never
pre-fills the editable Proposed column — the categorization is keyword-derived
and fuzzy, so a human copies it across deliberately with the snippet in view.

### Sheet `Summary`
Action Group × Owner-Active counts, and Note Story × State counts. Opens the
meeting on the numbers.

### Sheet `Legend`
What each Action Group / Note Story means + the Note-Story → Pursuit-Status
mapping, so the team trusts the suggestions.

## Note-Story → Suggested Pursuit Status map

| Note story | Suggested `Substatus__c` |
|---|---|
| Existing Bulk / incumbent (competitor locked) | Incumbent EMA |
| Owner denial / declined / halted | Chose Another Provider |
| Low return / not viable | Budget Not Approved / Business Case |
| Unresponsive / no contact | Owner Unresponsive |
| Blocked — moratorium / exclusivity | (blank — no clean match) |
| Disqualified / not a target | No Marketing/Bulk Needed |
| Built / Activated, Secured, Workable, Route, Sold, Construction | (blank — not a "stuck" reason) |

## Decisions

1. Editable column set = Proposed Owner + Proposed Pursuit Status + Decision/notes.
2. Suggested Pursuit Status is advisory; it does not auto-fill the editable column.
3. All 696 opps live in one `Triage` sheet (Owner Active? column + autofilter),
   not split active/inactive.

## Out of scope / future

- Bulk update back to SF (owner reassign + Pursuit Status set) with rollback
  snapshot + audit log + dry-run, driven by the completed workbook.
