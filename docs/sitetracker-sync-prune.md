# SiteTracker Sync: orphan prune (self-healing)

## Pending verification — check 2026-05-21 (or first session after the push lands)

The prune was added on 2026-05-20. **Push status: committed locally, NOT yet pushed**
(GCM auth failed in the non-interactive shell). Koa must run:

```
git -C C:\Users\cass\repos\Automation push origin main
```

Once pushed, the first daily run (cron `0 8 * * *` = 8 AM UTC) after the push will
exercise the prune. Verify with:

1. **Push landed?**
   `git -C C:\Users\cass\repos\Automation log --oneline -1 origin/main`
   → should be the "self-heal orphaned mirror rows" commit (`e1e6ce0`).
   If not, the cron ran the old code; push first, then re-check next day.
2. **Sync ran?** `python SalesForce/scripts/analysis/check_sitetracker_sync_health.py`
   → most rows `<= 26h (healthy)`. (Credential-free proxy for "the Action ran".)
3. **No orphans?** `python SalesForce/scripts/analysis/find_orphaned_sitetracker_mirrors.py`
   → expect `ORPHAN 0`. Today it is already 0, so a clean run stays 0.
4. **Prune ledger delta?** Check `C:/Users/cass/repos/Automation/sitetracker/removal-log.csv`
   (committed back by the workflow). 14 seed rows from the 2026-05-20 manual cleanup;
   any rows beyond that with `source_script = sitetracker/sync_sitetracker.py` are
   auto-prunes. The Action also commits this file back on prune days.
5. (Optional) GitHub Actions run conclusion for "SiteTracker Sync" — needs `gh` or the
   web UI; not installed locally, so steps 2-4 are the primary signal.

Delete this section once verified clean.

## What the prune does

Lives in `Ubiquity-SoCal/Automation` repo: `sitetracker/sync_sitetracker.py`,
function `prune_orphans()`, called from `main()` after the upsert.

- The sync upserts live `MDU_Fiber__c` records into `SiteTracker_Project__c` (main org)
  keyed on `SiteTracker_Record_Id__c`. It never deleted, so records hard-deleted in
  SiteTracker lingered as stale mirrors holding **false Opportunity links** (the
  P-005799 case, 2026-05-20).
- Prune diffs the mirror against the **unfiltered** `MDU_Fiber__c` id set (`SELECT Id
  FROM MDU_Fiber__c`, no WHERE) and deletes rows whose source id is absent. Using the
  unfiltered set means records merely *Cancelled* / missing build status (still present,
  just out of the active-sync filter) are **not** pruned. Only true deletes go.
- **Safety cap:** skips + warns if SiteTracker returns 0 ids, or if orphans exceed 100
  rows / 25% of the mirror. A partial/failed ST query can't nuke the table.
- Every removal is appended to `sitetracker/removal-log.csv` (full row detail for audit +
  rollback). The workflow (`.github/workflows/sitetracker-sync.yml`) commits the ledger
  back (`permissions: contents: write` + a commit step), since the runner is ephemeral.

## Related local tooling (manual, re-runnable)

- `SalesForce/scripts/analysis/find_orphaned_sitetracker_mirrors.py` — orphan scan (read-only).
- `SalesForce/scripts/fix/2026-05-20-prune-orphaned-sitetracker-mirrors.py` — standalone prune
  (snapshot + ledger + dry-run), used for the initial 2026-05-20 cleanup of 14 rows.
- Local `SalesForce/scripts/sync_sitetracker.py` is a **stale divergent copy** (missing Taylor's
  milestone fields) driven only by the disabled `SiteTrackerSync` Windows task + the Flask admin
  dashboard. The Automation repo is canonical; point the admin dashboard at it or retire the copy.
