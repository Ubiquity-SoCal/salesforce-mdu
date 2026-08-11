import os
import sys
import json
import subprocess
import threading
from flask import Flask, render_template, Response, jsonify

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


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

    try:
        from simple_salesforce import Salesforce
        sf = Salesforce(
            username=_SF["username"],
            password=_SF["password"],
            security_token=_SF["token"]
        )

        if sync_name == "sitetracker":
            count_result = sf.query(
                "SELECT COUNT() FROM SiteTracker_Project__c"
            )
            total = count_result['totalSize']

            last_sync_result = sf.query(
                "SELECT Last_Synced__c FROM SiteTracker_Project__c "
                "WHERE Last_Synced__c != null "
                "ORDER BY Last_Synced__c DESC LIMIT 1"
            )
            last_synced = None
            if last_sync_result['records']:
                last_synced = last_sync_result['records'][0]['Last_Synced__c']

            return jsonify({
                "total": total,
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
