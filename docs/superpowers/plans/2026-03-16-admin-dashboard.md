# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Admin Dashboard with a Flask backend that lets Koa trigger and monitor Salesforce sync scripts from a browser.

**Architecture:** Single Flask server at localhost:5050 serves the HTML dashboard and exposes API endpoints. Sync scripts run as subprocesses with stdout streamed to the browser via Server-Sent Events. One .bat launcher starts everything.

**Tech Stack:** Python 3, Flask, simple_salesforce, HTML/CSS/JS (vanilla)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `SalesForce/admin/admin_server.py` | Create | Flask app: serves HTML, sync registry, API routes, SSE streaming, status queries |
| `SalesForce/admin/templates/admin.html` | Create | Dashboard UI: tabs, status cards, progress bar, log panel, SSE client |
| `SalesForce/scripts/sync_sitetracker.py` | Create | Refactored sync: upsert, structured `[INFO]/[PROGRESS]/[SUCCESS]/[ERROR]` output |
| `SalesForce/Launch_Admin_Dashboard.bat` | Create | Installs Flask, starts server, opens browser |

---

## Task 1: Install Flask and verify it works

**Files:**
- None created yet, just verifying the environment

- [ ] **Step 1: Install Flask**

```bash
pip install flask
```

Expected: `Successfully installed flask-X.X.X` (or already satisfied)

- [ ] **Step 2: Verify Flask imports**

```bash
python -c "from flask import Flask; print('Flask OK')"
```

Expected: `Flask OK`

---

## Task 2: Create the refactored sync script

**Files:**
- Create: `SalesForce/scripts/sync_sitetracker.py`

This is a refactored copy of `load_sitetracker_data.py` with two changes: upsert instead of create, and structured output prefixes.

- [ ] **Step 1: Create the `scripts/` directory**

```bash
mkdir -p /c/Users/cass/Work_Projects/SalesForce/scripts
```

- [ ] **Step 2: Write `scripts/sync_sitetracker.py`**

```python
import sys
from simple_salesforce import Salesforce
from datetime import datetime

# Force unbuffered output so SSE receives lines immediately
sys.stdout.reconfigure(line_buffering=True)

# Connect to both orgs
print("[INFO] Connecting to main Salesforce org...")
sf_main = Salesforce(
    username='cass1@ubiquitygp.com',
    password='<password: see _shared/sf_auth.py>',
    security_token='<token: see _shared/sf_auth.py>'
)

print("[INFO] Connecting to SiteTracker org...")
sf_st = Salesforce(
    username='cass@ubiquitygp.com',
    password='<password: see _shared/sf_auth.py org=st>',
    security_token='<token: see _shared/sf_auth.py org=st>'
)

# Step 1: Pull all MDU Fiber records from SiteTracker (not cancelled)
print("[INFO] Pulling MDU Fiber data from SiteTracker...")
query = """SELECT Id, Name,
    Project__r.sitetracker__Site__r.Name,
    Project__r.sitetracker__Site__r.Monday_com_name__c,
    Project__r.sitetracker__Site__r.sitetracker__City__c,
    Project__r.sitetracker__Site__r.sitetracker__State__c,
    Project__r.sitetracker__Site__r.sitetracker__Site_Status__c,
    Project__r.sitetracker__Site__r.MDU_Site_Category__c,
    MDU_Build_Status__c,
    MDU_Activation_F__c,
    MDU_Activation_A__c,
    Premise_Access_License_PAL_A__c
    FROM MDU_Fiber__c
    WHERE Project__r.sitetracker__Site__r.sitetracker__Site_Type__c = 'MDU'
    AND Project__r.sitetracker__Project_Status__c != 'Cancelled'
    ORDER BY Name"""

st_records = []
result = sf_st.query(query)
st_records.extend(result['records'])
while not result['done']:
    result = sf_st.query_more(result['nextRecordsUrl'], True)
    st_records.extend(result['records'])

print(f"[INFO] Pulled {len(st_records)} MDU Fiber records from SiteTracker")

# Step 2: Get all Opportunities from main org for matching
print("[INFO] Getting MDU Opportunities from main org...")
opps = sf_main.query_all(
    "SELECT Id, Name FROM Opportunity WHERE RecordType.Name = 'MDU'"
)
opp_map = {}
for o in opps['records']:
    opp_map[o['Name'].strip().lower()] = o['Id']
print(f"[INFO] Got {len(opp_map)} MDU Opportunities for matching")

# Step 3: Build records for upsert
now_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
to_upsert = []
matched = 0
unmatched = 0

for r in st_records:
    site = (r.get('Project__r') or {}).get('sitetracker__Site__r') or {}
    monday_name = site.get('Monday_com_name__c') or ''
    site_name = site.get('Name') or ''

    opp_id = None
    if monday_name:
        opp_id = opp_map.get(monday_name.strip().lower())
    if not opp_id and site_name:
        opp_id = opp_map.get(site_name.strip().lower())
        if not opp_id and '_MDU_' in site_name:
            short_name = site_name.split('_MDU_', 1)[1]
            opp_id = opp_map.get(short_name.strip().lower())

    if opp_id:
        matched += 1
    else:
        unmatched += 1

    record = {
        'Name': r['Name'],
        'Site_Name__c': site_name,
        'Monday_Name__c': monday_name or site_name,
        'City__c': site.get('sitetracker__City__c'),
        'State__c': site.get('sitetracker__State__c'),
        'Site_Status__c': site.get('sitetracker__Site_Status__c'),
        'Build_Status__c': r.get('MDU_Build_Status__c'),
        'PAL_Signed_Date__c': r.get('Premise_Access_License_PAL_A__c'),
        'Activation_Forecast__c': r.get('MDU_Activation_F__c'),
        'Activation_Actual__c': r.get('MDU_Activation_A__c'),
        'MDU_Category__c': site.get('MDU_Site_Category__c'),
        'SiteTracker_Record_Id__c': r['Id'],
        'Last_Synced__c': now_str,
    }
    if opp_id:
        record['Opportunity__c'] = opp_id

    to_upsert.append(record)

print(f"[INFO] Matched to Opportunities: {matched}")
print(f"[INFO] No match (standalone): {unmatched}")
print(f"[INFO] Total to upsert: {len(to_upsert)}")

# Step 4: Upsert into main org using SiteTracker_Record_Id__c as external ID
print("[INFO] Upserting into main Salesforce org...")
total = len(to_upsert)
success_count = 0
error_count = 0

for i, rec in enumerate(to_upsert):
    st_id = rec.pop('SiteTracker_Record_Id__c')
    try:
        sf_main.SiteTracker_Project__c.upsert(
            f"SiteTracker_Record_Id__c/{st_id}", rec
        )
        success_count += 1
    except Exception as e:
        error_count += 1
        print(f"[ERROR] {rec.get('Name', 'unknown')} - {e}")

    # Progress every 25 records or on the last one
    if (i + 1) % 25 == 0 or (i + 1) == total:
        print(f"[PROGRESS] {i + 1}/{total}")

if error_count > 0:
    print(f"[ERROR] Completed with {error_count} errors. {success_count}/{total} succeeded, {matched} matched, {unmatched} standalone")
else:
    print(f"[SUCCESS] Done! {success_count} synced, {matched} matched, {unmatched} standalone, 0 errors")
```

- [ ] **Step 3: Test the script standalone**

```bash
cd /c/Users/cass/Work_Projects/SalesForce && python scripts/sync_sitetracker.py
```

Expected: `[INFO]` lines, then `[PROGRESS]` lines, then `[SUCCESS]` at the end. No duplicate errors (upsert is safe). Verify in Salesforce that `Last_Synced__c` updated on a few records.

- [ ] **Step 4: Verify upsert is idempotent — run it again**

```bash
python scripts/sync_sitetracker.py
```

Expected: Same output, same record count, no duplicates created. This confirms upsert is working.

---

## Task 3: Create the Flask server

**Files:**
- Create: `SalesForce/admin/__init__.py` (empty, makes it a package)
- Create: `SalesForce/admin/admin_server.py`

- [ ] **Step 1: Create admin directory**

```bash
mkdir -p /c/Users/cass/Work_Projects/SalesForce/admin/templates
```

- [ ] **Step 2: Write `admin/admin_server.py`**

```python
import os
import sys
import json
import subprocess
import threading
from flask import Flask, render_template, Response, jsonify

# Resolve paths relative to SalesForce/ root (one level up from admin/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# --- Sync Registry ---
SYNCS = {
    "sitetracker": {
        "script": os.path.join(BASE_DIR, "scripts", "sync_sitetracker.py"),
        "label": "SiteTracker Projects",
        "description": "Syncs MDU Fiber records from SiteTracker org into SiteTracker_Project__c"
    },
}

# --- State: track running sync ---
running_sync = {"name": None, "process": None, "lock": threading.Lock()}


@app.route("/")
def index():
    return render_template("admin.html")


@app.route("/syncs")
def list_syncs():
    result = {}
    for key, val in SYNCS.items():
        result[key] = {"label": val["label"], "description": val["description"]}
    return jsonify(result)


@app.route("/run/<sync_name>", methods=["POST"])
def run_sync(sync_name):
    if sync_name not in SYNCS:
        return jsonify({"error": f"Unknown sync: {sync_name}"}), 404

    with running_sync["lock"]:
        if running_sync["name"] is not None:
            return jsonify({"error": f"Sync '{running_sync['name']}' is already running"}), 409
        running_sync["name"] = sync_name

    script = SYNCS[sync_name]["script"]

    def generate():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=BASE_DIR,
                bufsize=1
            )
            running_sync["process"] = proc

            for line in proc.stdout:
                line = line.rstrip("\n")
                yield f"data: {json.dumps({'line': line})}\n\n"

            proc.wait()
            exit_code = proc.returncode
            yield f"data: {json.dumps({'done': True, 'exit_code': exit_code})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'[ERROR] Server error: {e}', 'done': True, 'exit_code': 1})}\n\n"
        finally:
            with running_sync["lock"]:
                running_sync["name"] = None
                running_sync["process"] = None

    return Response(generate(), mimetype="text/event-stream")


@app.route("/status/<sync_name>")
def sync_status(sync_name):
    if sync_name not in SYNCS:
        return jsonify({"error": f"Unknown sync: {sync_name}"}), 404

    # Query Salesforce for status info
    try:
        from simple_salesforce import Salesforce
        sf = Salesforce(
            username='cass1@ubiquitygp.com',
            password='<password: see _shared/sf_auth.py>',
            security_token='<token: see _shared/sf_auth.py>'
        )

        if sync_name == "sitetracker":
            # Get total count and last synced time
            count_result = sf.query(
                "SELECT COUNT() FROM SiteTracker_Project__c"
            )
            total = count_result['totalSize']

            # Get last synced timestamp
            last_sync_result = sf.query(
                "SELECT Last_Synced__c FROM SiteTracker_Project__c "
                "WHERE Last_Synced__c != null "
                "ORDER BY Last_Synced__c DESC LIMIT 1"
            )
            last_synced = None
            if last_sync_result['records']:
                last_synced = last_sync_result['records'][0]['Last_Synced__c']

            # Get matched count (has Opportunity linked)
            matched_result = sf.query(
                "SELECT COUNT() FROM SiteTracker_Project__c "
                "WHERE Opportunity__c != null"
            )
            matched = matched_result['totalSize']

            return jsonify({
                "total": total,
                "matched": matched,
                "standalone": total - matched,
                "last_synced": last_synced,
                "is_running": running_sync["name"] == sync_name
            })

        return jsonify({"error": "Status not implemented for this sync"}), 501

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"Admin Dashboard starting on http://localhost:5050")
    print(f"Base directory: {BASE_DIR}")
    print(f"Registered syncs: {', '.join(SYNCS.keys())}")
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
```

- [ ] **Step 3: Test server starts**

```bash
cd /c/Users/cass/Work_Projects/SalesForce && python admin/admin_server.py
```

Expected: `Admin Dashboard starting on http://localhost:5050`. Kill with Ctrl+C after verifying.

---

## Task 4: Create the dashboard HTML

**Files:**
- Create: `SalesForce/admin/templates/admin.html`

- [ ] **Step 1: Write `admin/templates/admin.html`**

This is the full dashboard page. Key features:
- Dynamically builds tabs from `GET /syncs`
- Each tab has: status card, run button + progress bar, collapsible log panel
- SSE client connects to `POST /run/<sync_name>` and streams output
- Parses `[PROGRESS]`, `[SUCCESS]`, `[ERROR]`, `[INFO]` prefixes
- On completion, calls `GET /status/<sync_name>` to refresh the status card
- Control panel aesthetic: dark header, muted colors, Segoe UI + Consolas

The HTML is self-contained (embedded CSS + JS, no external dependencies).

Layout structure:
```
+---------------------------------------+
| Admin Dashboard          [green dot]  |  <- dark header bar
+---------------------------------------+
| [SiteTracker] [future tabs...]        |  <- tab buttons
+---------------------------------------+
| SiteTracker Projects                  |
| Syncs MDU Fiber records from...       |
|                                       |
| Last Synced: 2026-03-16 08:15:00     |
| Records: 384 total, 47 matched       |  <- status card
| Status: [Ready]                       |
|                                       |
| [  Run Sync  ]                        |  <- action button
| [==========>          ] 50/384        |  <- progress bar (hidden until running)
|                                       |
| v Log Output                          |  <- collapsible
| [INFO] Connecting to SiteTracker...   |
| [INFO] Pulled 384 records...          |
| [PROGRESS] 50/384                     |
+---------------------------------------+
```

- [ ] **Step 2: Start the server and verify dashboard loads**

```bash
cd /c/Users/cass/Work_Projects/SalesForce && python admin/admin_server.py
```

Open `http://localhost:5050` in browser. Expected: dashboard loads, SiteTracker tab visible, status card shows current data from Salesforce.

- [ ] **Step 3: Test the Run Sync button**

Click "Run Sync" on the SiteTracker tab. Expected:
- Button disables, shows spinner
- Progress bar appears and fills
- Log panel expands and shows streaming output
- On completion: status badge turns green, status card refreshes with new timestamp

- [ ] **Step 4: Test concurrency lock**

While a sync is running, open a second browser tab and try clicking Run Sync. Expected: button should be disabled or show "already running" message.

---

## Task 5: Create the launcher .bat file

**Files:**
- Create: `SalesForce/Launch_Admin_Dashboard.bat`

- [ ] **Step 1: Write `Launch_Admin_Dashboard.bat`**

```bat
@echo off
cd /d "%~dp0"
pip install flask >nul 2>&1
start "Admin Dashboard Server" python admin/admin_server.py
timeout /t 2 /nobreak >nul
start "" http://localhost:5050
echo.
echo Admin Dashboard server is running.
echo Close this window to stop the server.
pause >nul
```

- [ ] **Step 2: Test the launcher**

Double-click `Launch_Admin_Dashboard.bat`. Expected:
- Flask installs silently (or skips if already installed)
- Server starts in a background window
- Browser opens to `http://localhost:5050`
- Dashboard loads with SiteTracker tab

- [ ] **Step 3: Test full end-to-end flow**

From the launcher:
1. Dashboard loads
2. Status card shows current SF data
3. Click "Run Sync" -> watch live progress -> see success
4. Status card refreshes with new timestamp
5. Close the command window to stop the server

---

## Task 6: Final cleanup and verification

- [ ] **Step 1: Verify file structure matches spec**

```
SalesForce/
  admin/
    admin_server.py
    templates/
      admin.html
  scripts/
    sync_sitetracker.py
  Launch_Admin_Dashboard.bat
  load_sitetracker_data.py      (original, unchanged)
  sync_sitetracker.py           (original, unchanged)
```

- [ ] **Step 2: Run the sync twice via the dashboard to confirm no duplicates**

Run sync, note record count. Run again. Record count should stay the same (upsert, not create).

- [ ] **Step 3: Verify Last_Synced__c updated in Salesforce**

Check a SiteTracker_Project__c record in SF — Last_Synced__c should show the most recent sync time.
