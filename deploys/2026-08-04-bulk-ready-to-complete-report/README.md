# 2026-08-04 Bulk In Progress: Ready to Complete

Closes a blind spot in the MDU Cleanup Dashboard. IronClad sync **Phase 2** candidates (Opps ready
to advance `Marketing/Bulk In Progress` -> `Marketing/Bulk Complete`) had nowhere to surface, so
they existed only in the Phase 2 probe output and whatever session ran it. With Taylor Mauney out
on leave they would have sat unseen until her return.

## Deployed

| Component | Developer name |
| --- | --- |
| Report | `MDU_Sales_Reports/Cleanup_Bulk_In_Progress_Ready_Complete` ("Cleanup: Bulk Ready to Complete", `00OWR00000MrbJJ2AZ`) |
| Dashboard | `MDU_Sales_Dashboards/MDU_Cleanup_Dashboard` — 9th component "Bulk In Progress: Ready to Complete", middle section |

Verified live: returns exactly Bradley Arms + Saffari Apartments, matching the Phase 2 probe.

## The rule, and why it is two cross filters

Phase 2 (from `_probes/2026-05-20-phase2-stage-advance-check.py`): stage is
`Marketing/Bulk In Progress`, **every** agreement is settled (none at Create/Review/Sign/Paused),
**and** at least one EMA/Bulk reached Completed or Archive.

**Do not try to express "all settled" with `Active_EMA_Bulk_Count__c`.** That rollup counts
*non-cancelled* EMA/Bulk, not *unsettled* ones — Bradley Arms and Saffari both show
`Active_EMA_Bulk_Count__c = 1` while their only EMA sits at Archive. A first attempt using
`= 0` returned zero rows and looked like the candidates did not exist. The settled test has to be a
`without` cross filter on `Status__c`, not a rollup comparison.

So:
- cross filter 1 — **with** `Agreement__c` where `Agreement_Type__c IN (EMA, Bulk)` AND `Status__c IN (Completed, Archive)`
- cross filter 2 — **without** `Agreement__c` where `Status__c IN (Create, Review, Sign, Paused)`

Cross filter 2 is deliberately un-typed: the probe requires *all* agreements settled, not just EMA/Bulk.

## Metadata gotchas hit (all cost a dry-run cycle)

- Inside `<crossFilters><criteriaItems>` the `<column>` is **relative to `relatedTable`** — use
  `Status__c`, NOT `Agreement__c.Status__c`. The prefixed form fails
  `no CustomField named Agreement__c.Agreement__c.Status__c found`.
- Report `<name>` max **40** chars; `<description>` max **255**. Both fail only at deploy time.
- **Deploy the report before the dashboard.** A single manifest containing both fails with
  `no Report named ... found` because the dashboard component reference is validated against what is
  already in the org. Hence `package-report.xml` then `package-dash.xml`.
- `sf project retrieve start -m "Dashboard:<Folder>/<Name>"` needs **developer** names on both parts.
  Folder/report *labels* return "Nothing retrieved" with a misleading "cannot be found" warning.

## Re-running

```bash
cd SalesForce/deploys/2026-08-04-bulk-ready-to-complete-report
sf project deploy start --manifest package-report.xml --dry-run   # validate
sf project deploy start --manifest package-report.xml
sf project deploy start --manifest package-dash.xml
```

Production is atomic-only, so always `--dry-run` first.
