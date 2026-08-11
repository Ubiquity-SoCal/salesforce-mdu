# Bill's SAQ Master List → SF Opportunity Stage sync

**Date:** 2026-06-24
**Source:** `C:\Users\cass\Downloads\Master List MDU Assignments.xlsm` (`Opportunities` tab, 389 site rows)
**Target:** Salesforce Opportunity `StageName` + dependent reason fields
**Org:** Production (`fun-power-747`), creds at `SalesForce/api/Salesforce_Credentials.txt`

## Goal

Reconcile the statuses Bill maintains in his MDU assignments workbook against current SF
Opportunity stages, surface the deltas for Koa's review, then apply the approved set with a
full audit trail. SF stages are curated (Taylor is the MDU gatekeeper), so **no blind bulk
overwrite** — review gates the write.

## Decisions (locked with Koa 2026-06-24)

- **Scope:** all 389 rows.
- **Target field:** Opportunity `StageName` (+ reason fields), not a new SAQ field.
- **Conflict policy:** diff first, then apply. Koa reviews the Phase A diff; Taylor sign-off not required.
- **`Closed - Contact Info` (136 rows):** → `Closed Lost`, Loss Reason = **No Contact Info**.

## Status mapping (SAQ Status → SF Stage)

| Bill's SAQ Status | count | → SF Stage | Reason field |
|---|---|---|---|
| Engaged | 53 | Engaged | — |
| Proposal Sent | 25 | Proposal Sent | — |
| Proposal Review | 15 | Proposal Sent | — (proposal out, owner deciding) |
| Pending Signature | 3 | Contract Negotiations | — (agreement in hand, awaiting signature) |
| Completed | 2 | PAL/ROE Complete | — |
| Hold | 12 | On Hold | Hold_Reason (best-effort from notes, else blank) |
| Closed - Lost | 137 | Closed Lost | Loss_Reason (keyword from Closed Notes, default `No Decision / Non-Responsive`) |
| Closed - Contact Info | 136 | Closed Lost | Loss_Reason = `No Contact Info` |
| Data Issue | 6 | **skip** | not a pipeline state (dup addresses) |

Stage and reason picklist values to be **confirmed against the live org** before Phase B —
the values above come from the local `tracker-lwc` metadata mirror.

Loss Reason picklist (mirror): Lost to Competitor, No Budget / Lost Funding,
No Decision / Non-Responsive, Price, Existing Fiber, Not Interested, No Contact Info,
Existing Contract, Rejected by Owner, Other.

## Phase A — Reconcile (read-only)

`SalesForce/scripts/analysis/bill_saq_status_reconcile.py`

1. Load `Opportunities` tab; normalize the 9 SAQ Status values; apply mapping → target stage + reason.
2. Match each row to SF by `Agreement_Name__c` (batched SOQL `IN`), property-name fuzzy fallback
   (same approach as `scripts/import/diff_weekly_mdu_updates.py`).
3. Pull current `StageName` (+ Owner, reason fields) for matched Opps.
4. Classify each row: `no-change`, `advance`, `regress`, `→closed`, `unmatched`, `data-issue-skip`.
5. Output to `SalesForce/data/output/bill-saq-reconcile/`:
   - `reconcile-<date>.csv` — every row, full detail (key, current stage, target stage, reason, class).
   - `reconcile-<date>.md` — summary grouped by Owner and change type for eyeballing.

Read-only. No SF writes. This is the artifact Koa reviews.

## Phase B — Apply (write, gated on Phase A approval)

`SalesForce/scripts/sync/bill_saq_status_apply.py` (built after Koa approves the diff)

- Dry-run by default; `--apply` to commit.
- Writes `StageName` + reason field + `CloseDate` (for closes).
- Validation-rule aware: where a target stage requires a dependent reason, set it or flag the row.
- Every change → `SalesForce/data/output/audit_logs/<date>_bill_saq_status_push.csv`
  (SF_Id / Name / Field / Before / After / Source / Timestamp / Action).
- Idempotent: rows already at target are no-ops; safe to re-run.

## Hard rules

- **Never create Opportunities.** The 51 keyless rows + any unmatched keyed rows are report-only.
- `Data Issue` rows are skipped and listed separately.
- Confirm live picklists before any write.

## Testing

TDD on pure logic in `scripts/analysis/` (or a small `bill_saq_mapping.py` module):
- SAQ Status → (stage, reason) mapping.
- Loss-reason keyword derivation from Closed Notes.
- advance/regress classification via stage ordinal.

Write path verified via dry-run + audit-log inspection; optional `uqpartial` sandbox rehearsal.
