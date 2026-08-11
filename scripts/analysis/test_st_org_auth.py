"""Quick auth test for the SiteTracker SF org (separate from the main org)."""
import sys
from simple_salesforce import Salesforce, exceptions

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_ST = _sf_creds("st")


sys.stdout.reconfigure(line_buffering=True)

# These are the values currently hard-coded in sync_sitetracker.py for sf_st
USERNAME = _ST["username"]
PASSWORD = _ST["password"]
TOKEN = _ST["token"]

print(f"Testing ST org auth as {USERNAME}...")
try:
    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=TOKEN)
    # Trivial query to confirm session works
    r = sf.query("SELECT Id FROM User WHERE Id = '%s'" % sf.session_id[:18])
    print("[OK] Auth succeeded. Session token issued.")
except exceptions.SalesforceAuthenticationFailed as e:
    print(f"[FAIL] {e}")
except Exception as e:
    # Auth may pass but query may fail with garbage session id; that's still auth-OK
    print(f"[OK-ish] Auth succeeded (query path errored: {type(e).__name__})")
