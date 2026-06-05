# MDU Tracker: config and behavior notes

Notes on the MDU Tracker (trackerGrid LWC + TrackerController Apex, in `tracker-lwc/`). Captures decisions that are easy to undo by accident.

## Past Due filter definition (changed 2026-06-01)
The "Past Due" date-range filter is defined in **`TrackerController.cls`** in **two** identical clauses (the main list query and the aggregate count query). Keep them in sync.

A row is Past Due when:
```
Projected_Close_Date__c < TODAY
  AND Projected_Close_Date__c != null
  AND ST_Activation_Actual__c = null            -- not yet activated (not done)
  AND StageName NOT IN ('Closed Lost','Closed Won','Under Contract','On Hold','Marketing/Bulk Complete')
```
Why: completed/activated properties were showing as Past Due (Melissa's report). The fix drops activated rows and Marketing/Bulk Complete. **PAL/ROE Complete and Marketing/Bulk In Progress remain Past-Due-eligible on purpose** (still in flight toward activation). `Under Contract` / `Closed Won` are kept for the Business app, which shares this controller.

## MDU Activation column
`ST_Activation_Actual__c` ("SiteTracker Activation (Actual)") is appended as a read-only column at the end of every MDU view. It is populated by the daily SiteTracker GitHub Action sync (see auto-runs), not entered by hand. `editable: false` in the column config prevents inline edits.

## Row highlighting (config-driven, no code deploy to change)
Tracker views are `Tracker_View__c` records; columns and conditional formatting live in the `Config__c` JSON, read by the grid's `formatting_rules` engine. A `target: "row"` rule applies its style to the whole row; **first matching rule wins** (order = precedence).

Current MDU row rules, in precedence order (first match wins; provisional colors, pending Melissa's sign-off):
1. **Green `#d4edda`** when `ST_Activation_Actual__c` > `2015-01-01` -> MDU activated. **Green is reserved for activation only.** Uses a date threshold rather than "has any date" because engineering sometimes enters placeholder dates like `1900-01-01`, which must NOT read as activated. The Past Due filter applies the same threshold (`null OR < 2015-01-01` = not activated).
2. **Gray `#e2e3e5`** when `Substatus__c` (Pursuit Status) is in the stalled set: Owner Unresponsive, Budget Not Approved / Business Case, Chose Another Provider, Bulk/Marketing Rejected, ISP or Funding Needed, Incumbent EMA -> not actively proceeding.
3. **Blue `#cfe2ff`** when `StageName` in (Marketing/Bulk Complete, PAL/ROE Complete) -> at an advanced stage, in progress, not yet activated. `No Marketing/Bulk Needed` rows fall here (they still need activation; they just skip the bulk step).

So at the two terminal-ish stages a row reads as: green = activated, gray = stalled, blue = still in progress. Applied to every MDU view, so the colors mean the same thing on every tab.

To recolor: edit the `style` value in each MDU view's `Config__c`. No deploy needed.

**Gotcha:** the formatting engine can only evaluate fields that are actually queried. A rule on a field that is not a column silently never fires. So `TrackerController.cls` force-queries `StageName`, `Substatus__c`, and `ST_Activation_Actual__c` for Opportunity views (see the "row-highlighting rules depend on" block) even when a view config does not list them as columns. The gray (stalled) rule keys off `Substatus__c`, NOT `Sub_Bucket__c`, because the `Sub_Bucket__c` formula does not surface Substatus for the Marketing/Bulk In Progress stage.

## Sort
Per-view sort lives in `Config__c.sort` as `{field, direction, nulls, field2, direction2, nulls2}`. `nulls`/`nulls2` are optional and default to `LAST` (`TrackerController` only honors `FIRST` or `LAST`); `field2` (optional) is a secondary tiebreaker. Column-header clicks override with a single field, `NULLS LAST`. The controller always appends `Id ASC` as a final unique tiebreaker so `OFFSET`-based "Load More" paging is deterministic (without it, rows tied on the sort key reshuffle across pages and order appears lost).

**Marketing/Bulk Complete and PAL/ROE Complete views** default to `{field: ST_Activation_Actual__c DESC NULLS FIRST, field2: Substatus__c ASC NULLS FIRST}`. Primary pulls the not-yet-activated rows (no activation date) to the top and sinks activated (green) to the bottom; secondary orders that block by Pursuit Status so blue (no stalled status -> null Substatus) leads gray (stalled). Net top-to-bottom: blue (in progress) -> gray (stalled) -> green (activated). Minor wrinkle on PAL/ROE Complete: `No Marketing/Bulk Needed` rows render blue but, because the secondary sort is alphabetical on Substatus, they land inside the gray block (between "Incumbent EMA" and "Owner Unresponsive") rather than with the plain blue rows. Negligible at 2 rows; would need a computed rank field to place perfectly.

## How these were applied / rollback
- Script: `scripts/fix/2026-06-01-tracker-add-activation-and-highlights.py` (idempotent; preview by default, `--apply` to write).
- Pre-change snapshot of every MDU view `Config__c`: `data/output/tracker_view_snapshots/mdu_tracker_views_<timestamp>.json`. Restore by writing the saved `Config__c` back to each `Id`.
