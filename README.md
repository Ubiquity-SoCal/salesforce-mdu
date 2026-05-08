# SalesForce/

Salesforce metadata, scripts, and data for the MDU Sales / Inside Sales / Address
Management apps. Connects to:

- **Main org** (cass1@ubiquitygp.com) — MDU/Business pipeline, Property_Location/Unit, Agreements
- **SiteTracker org** (separate SF) — construction tracking, FDH activation source

For project context (current status, architecture, decisions), see auto-memory
`mdu-salesforce-project.md`. For org-level docs see `docs/salesforce-connection.md`.

## Layout

Follows `Work_Projects/STRUCTURE.md`.

```
SalesForce/
├── README.md                   # this file
├── api/                        # SF credentials + tokens (gitignored)
├── docs/                       # connection docs, screenshots, decision logs
├── scripts/
│   ├── sync/                   # active sync scripts (e.g. sync_vetro_to_salesforce.py)
│   ├── import/                 # data imports
│   ├── analysis/               # re-runnable analytical scripts
│   ├── fix/                    # one-off remediations (date-prefixed)
│   ├── cleanup/                # bigger cleanup workflows (per-project subfolders)
│   ├── deploy/                 # SFDX deploy helpers
│   ├── setup/                  # initial / one-time setup scripts
│   ├── dashboard/              # admin Flask dashboard scripts
│   └── _probes/                # throwaway diagnostics
├── deploys/                    # SF metadata deploys, one folder per deploy (date-prefixed)
├── data/
│   ├── input/                  # source data dropped by hand
│   │   └── powerbi-imports-archive/
│   └── output/                 # generated artifacts
│       ├── audit_logs/         # mutation provenance from sync/fix scripts
│       ├── migration-reports/
│       └── roe-925-import/
├── admin/                      # Flask admin dashboard
├── tracker-lwc/                # Tracker LWC source (deployed via sf CLI)
├── _archive/                   # done one-offs, frozen snapshots, point-in-time data
│   ├── baselines/              # 2026-04-17 metadata snapshots
│   ├── legacy-metadata/        # old XML/page/flexipage backups
│   ├── old-data/               # one-off JSON/CSV outputs no longer current
│   └── old-projects/           # completed sub-projects (e.g. CA_MDU_Merge)
└── _archive_deploys/           # 28 historical SF metadata deploy bundles (post-deploy)
```

## Active scripts

- `scripts/sync/sync_vetro_to_salesforce.py` — Vetro+SiteTracker bronze (Databricks) ->
  Property_Location/Unit. Canonical copy in `Automation/vetro-sync/`. Manual trigger.
  See `vetro-sync-runbook.md` memory for the workflow.
- `scripts/sync/sync_sitetracker.py` — local copy of the SiteTracker org-to-org sync.
- `scripts/sync/run_sitetracker_sync.bat` — convenience launcher.
- `scripts/cleanup/` — bigger multi-step cleanup workflows (Taylor's substatus push,
  EMA/Bulk cleanup phases, etc.). Date-stamped per workflow.

## Conventions

- **Audit logs** (mutation provenance) land in `data/output/audit_logs/`. Every
  mutating script appends one CSV per run with Before/After/Source/Timestamp/Action.
- **One-off fix scripts** in `scripts/fix/<date>-<purpose>.py`.
- **SF metadata deploys** in `deploys/<date>-<purpose>/`. Move to `_archive_deploys/`
  once deployed.
- **API credentials** in `api/` (gitignored — see `api/Salesforce_Credentials.txt`).

## Recent restructure

2026-05-08: `Work_Projects/SalesForce/_restructure-log-2026-05-08.md` documents the
move-by-move reorganization to comply with `Work_Projects/STRUCTURE.md`. The
`_restructure-before-2026-05-08.txt` snapshot captures the prior state in case anything
was misplaced.
