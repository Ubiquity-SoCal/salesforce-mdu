# SalesForce/ Restructure Log — 2026-05-08

Tracking every move in the migration to `Work_Projects/STRUCTURE.md`.

## Step 1 — Create skeleton

Created: `api/`, `data/input/`, `data/output/`, `data/output/audit_logs/`,
`data/output/migration-reports/`, `data/output/roe-925-import/`,
`data/input/powerbi-imports-archive/`, `deploys/`, `_archive/legacy-metadata/`,
`_archive/old-data/`, `_archive/old-projects/`, `scripts/_probes/`, `docs/screenshots/`.

## Step 2 — Credentials & connection docs

| From | To |
|---|---|
| `Salesforce_Credentials.txt` | `api/` |
| `Security_Token.txt` | `api/` |
| `salesforce-connection.md` | `docs/` |
| `sitetracker-connection.md` | `docs/` |
| `name-cleanup-log.md` | `docs/` |
| `stage_cleanup_team_review.md` | `docs/` |

`api/` added to `.gitignore`.

## Step 3 — Legacy SF metadata

13 XML/page/JSON metadata backup files moved from root → `_archive/legacy-metadata/`:
Contact_Record_Page*, current_opp_layout.xml, Opp_FlexiPage_Current.xml,
Opportunity_Layout_Current.xml, InsideSalesDashboard_*.page, businessSalesDashboard.vfp,
insideSalesDashboard_original.txt, flexipage_modified.json,
flow_backup_new_opp_notification_v9.json, property_unit_flexipage_backup.json,
view_metadata_backup.json.

## Step 4 — One-off scripts

| From | To (date-prefixed per convention) |
|---|---|
| `draft_smb_roe_ff_email.ps1` | `scripts/fix/2026-04-16-draft-smb-roe-ff-email.ps1` |
| `draft_taylor_3questions.ps1` | `scripts/fix/2026-04-24-draft-taylor-3questions.ps1` |
| `draft_taylor_reply.ps1` | `scripts/fix/2026-04-17-draft-taylor-reply.ps1` |
| `google_sheets_connect.py` | `scripts/setup/` |

## Step 5 — Top-level CSVs

| From | To |
|---|---|
| `roe_925_*.csv` (4 files) | `data/output/roe-925-import/` |
| `mdu_prospecting_audit.csv`, `meeting_update_proposal.csv` | `data/output/` |
| `sf_mdu_existing.csv`, `sf_mdu_agreement_names.txt` | `data/output/` |
| `migration_notes_errors.csv`, `migration_opp_errors.csv`, `unsynced_*.csv` (4) | `data/output/migration-reports/` |

## Step 6 — JSON top-level files

| From | To |
|---|---|
| `agr2026.json`, `completed.json`, `funnel.json`, `mbc.json`, `pipeline.json`, `smb_roe_data.json`, `tracker_to_sf_matches.json`, `weekly_tracker_parsed.json` | `data/output/` |
| `ironclad_linker_preview_2026-04-24.json`, `justin_prospecting_audit.json`, `migration_notes_log.json`, `migration_notes_progress.json`, `pre_migration_wipe_backup.json`, `report_ids.json`, `stage_mapping.json`, `vetro_classifier_preview*.json` | `_archive/old-data/` |
| `taylor_*.md`, `taylor_revisions_thread.html`, `taylor-feedback-review.docx` | `_archive/old-data/` |

## Step 7 — XLSX, HTML, BAT, pycache

| From | To |
|---|---|
| `Fiber_First_Assignments.xlsx` | `data/input/` |
| `active_users_report.xlsx`, `stage_cleanup_team_review.xlsx` | `data/output/` |
| `smb-roe-dashboard.html` | `data/output/` |
| `Launch_Admin_Dashboard.bat` | `admin/` |
| `__pycache__/` | DELETED (regenerable) |

## Step 8 — Folders

| From | To |
|---|---|
| `CA_MDU_Merge/` | `_archive/old-projects/` |
| `Layout_Pages/*` (2 jpg) | `docs/screenshots/` |
| `baselines/` | `_archive/baselines/` |
| `PowerBI_Report/Previously_Imported/*` (4 xlsx) | `data/input/powerbi-imports-archive/` |
| `weekly_tracker_import/` | `_archive/old-data/weekly-tracker-import-2026/` |
| `retire-listviews-2026-05-08/` | `_archive_deploys/` |

## Step 9 — audit_logs migration

Moved 129 audit log CSVs from `audit_logs/` → `data/output/audit_logs/`. Old folder removed.

Active scripts updated to point at the new path:
- `scripts/sync/sync_vetro_to_salesforce.py` (default `AUDIT_DIR`)
- `Automation/vetro-sync/sync_vetro_to_salesforce.py` (default `AUDIT_DIR`)
- `Automation/vetro-sync/.env.example` (commented default)
- `Automation/vetro-sync/README.md` (text reference)

Inactive/done one-off scripts (taylor_*, etc.) keep their old hardcoded paths
since they won't be re-run. They will fail if invoked, intentionally — they're
historical record only.

## Step 10 — README + snapshots

- `README.md` — new project README documenting the layout
- `_restructure-before-2026-05-08.txt` — pre-restructure inventory
- `_restructure-after-2026-05-08.txt` — post-restructure inventory
- `_restructure-log-2026-05-08.md` — this file

## Verification

Loose top-level files at the end of restructure:
- `README.md` (new)
- `_restructure-before-*.txt` (audit trail)
- `_restructure-after-*.txt` (audit trail)
- `_restructure-log-*.md` (audit trail)
- `.gitignore`

Everything else lives in a categorized folder. No untracked top-level scripts,
data files, or metadata bundles.

## Rollback

To revert a specific move, consult the From → To column above and run the inverse.
The file content was untouched — only locations changed. Snapshot files capture
the exact pre-state.
