# Admin Dashboard - Design Spec

> Local control panel for running and monitoring Salesforce sync operations. Lives in the SalesForce project folder, launched via .bat file, runs a Flask server that serves the HTML and executes sync scripts on demand.

---

## File Structure

```
SalesForce/
  admin/
    admin_server.py              # Flask app (serves HTML + API endpoints)
    templates/
      admin.html                 # Dashboard page
  scripts/
    sync_sitetracker.py          # Refactored sync (upsert, structured output)
  Launch_Admin_Dashboard.bat     # Starts Flask server + opens browser
  load_sitetracker_data.py       # Original script (reference, unchanged)
  sync_sitetracker.py            # Original script (reference, unchanged)
```

---

## Server Architecture

### Technology
- **Flask** (`pip install flask`) — single process serves HTML and API
- Runs on `localhost:5050`
- Single .bat file starts the server and opens the browser

### Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serves the admin dashboard HTML |
| `/syncs` | GET | Returns available syncs as JSON (for dynamic tab building) |
| `/run/<sync_name>` | POST | Triggers sync script as subprocess, streams stdout via SSE |
| `/status/<sync_name>` | GET | Returns last sync time + record counts from Salesforce |

### Sync Registry

A config dict in `admin_server.py` maps sync names to their scripts and metadata:

```python
SYNCS = {
    "sitetracker": {
        "script": "scripts/sync_sitetracker.py",
        "label": "SiteTracker Projects",
        "description": "Syncs MDU Fiber records from SiteTracker org into SiteTracker_Project__c"
    },
    # Future syncs added here:
    # "monday": {
    #     "script": "scripts/sync_monday.py",
    #     "label": "Monday.com Import",
    #     "description": "Imports Opportunities from Monday.com"
    # }
}
```

Adding a new sync = add a dict entry + drop a script in `scripts/`.

### Execution Flow

1. User clicks "Run Sync" on SiteTracker tab
2. JS sends `POST /run/sitetracker`
3. Flask spawns `scripts/sync_sitetracker.py` as a subprocess
4. stdout is piped line-by-line back to the browser via Server-Sent Events (SSE)
5. HTML parses prefixed lines to update progress card and log panel
6. On completion, JS calls `GET /status/sitetracker` to refresh the status card with live data from Salesforce

### Concurrency

Only one sync can run at a time. If a sync is already running, the button is disabled and the endpoint returns a 409.

---

## Dashboard HTML

### Layout

Control panel aesthetic -- functional, clean, utility-focused. Not the blue dashboard header style.

**Top Bar:**
- Title: "Admin Dashboard"
- Server status indicator (green dot = connected)

**Tabbed Interface:**
- One tab per sync, built dynamically from `GET /syncs`
- Starts with one tab: SiteTracker

**Each Sync Tab Contains:**

#### Status Card (top of tab)
- Sync name + description
- Last Synced: timestamp (from `Last_Synced__c` in SF)
- Record Count: total synced, matched to Opportunities, standalone
- Status badge: Ready (gray) / Running (blue) / Success (green) / Error (red)

#### Action Area (middle)
- "Run Sync" button -- disabled while running, shows spinner
- Progress bar that fills as `[PROGRESS]` lines arrive

#### Log Panel (bottom, collapsible)
- Monospace scrolling text output
- Auto-scrolls to bottom as new lines arrive
- Collapsed by default, expands when sync starts
- Color-coded lines: green for `[SUCCESS]`, red for `[ERROR]`, default for `[INFO]`

### Color Scheme
- Dark or muted header (control panel feel)
- Light content area
- Status colors: green (#22c55e), red (#ef4444), yellow (#eab308), blue (#2563eb), gray (#64748b)
- Monospace font for log panel (Consolas)
- Segoe UI for labels and headers (consistent with Koa's other projects)

---

## Sync Script: `scripts/sync_sitetracker.py`

Refactored from `load_sitetracker_data.py` with two changes:

### 1. Upsert Instead of Create

Use `SiteTracker_Record_Id__c` as the external ID for upsert operations. Safe to re-run anytime -- updates existing records, creates new ones, no duplicates.

```python
sf_main.SiteTracker_Project__c.upsert(
    f"SiteTracker_Record_Id__c/{rec['SiteTracker_Record_Id__c']}",
    rec
)
```

### 2. Structured Output for Parsing

Print statements use prefixed format so the HTML can parse progress:

```
[INFO] Connecting to SiteTracker org...
[INFO] Pulled 384 MDU Fiber records
[INFO] Matched 47 to Opportunities, 337 standalone
[PROGRESS] 50/384
[PROGRESS] 100/384
[PROGRESS] 200/384
[PROGRESS] 384/384
[SUCCESS] Done! 384 synced, 47 matched, 337 standalone, 0 errors
[ERROR] Failed: P-002258 - some error message
```

- `[PROGRESS] N/TOTAL` -- updates progress bar
- `[SUCCESS]` -- final line on success, updates status card to green
- `[ERROR]` -- individual errors shown in log, final status turns red if any errors
- `[INFO]` -- informational, goes to log panel only

### Credentials

Same approach as original script -- credentials in the script file, read from `salesforce-connection.md` pattern. No change to auth.

### Logic

Same as `load_sitetracker_data.py`:
1. Connect to both SF orgs (main + SiteTracker)
2. Query MDU Fiber records from SiteTracker org (WHERE Site_Type = 'MDU' AND Status != 'Cancelled')
3. Get MDU Opportunities from main org for name matching
4. Match by Monday.com name, site name, or extracted MDU name
5. Upsert into SiteTracker_Project__c with `Last_Synced__c` = now

---

## Launcher

### `Launch_Admin_Dashboard.bat`

```bat
@echo off
cd /d "%~dp0"
pip install flask >nul 2>&1
start "" python admin/admin_server.py
timeout /t 2 >nul
start "" http://localhost:5050
```

- Ensures Flask is installed (silent, idempotent)
- Starts the server in background
- Waits 2 seconds for startup
- Opens browser to the dashboard

---

## Future Extensibility

- New sync = new entry in SYNCS dict + new script in `scripts/`
- Tabs auto-populate from the registry
- Monday.com sync is the likely next addition
- Could add scheduled runs (cron-style) later, but not in scope now
