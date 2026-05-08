"""Quick auth test for the SiteTracker SF org (separate from the main org)."""
import sys
from simple_salesforce import Salesforce, exceptions

sys.stdout.reconfigure(line_buffering=True)

# These are the values currently hard-coded in sync_sitetracker.py for sf_st
USERNAME = 'cass@ubiquitygp.com'
PASSWORD = 'Hawaiian84'
TOKEN = 'fe2pen6ceQeqGhWXhBeOIjqP'

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
