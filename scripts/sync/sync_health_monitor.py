"""Out-of-band sync health monitor. Runs on Koa's PC via a local Windows Scheduled Task,
NOT on GitHub Actions - deliberately, so it survives the exact failure it exists to catch.

Background: on 2026-07-13 the SiteTracker nightly sync silently died and stayed dead 11 days.
Nobody knew until Koa asked. The GitHub `sitetracker-health.yml` canary would have caught it,
but that canary runs as a fourth job in the SAME scheduler that died, so it died too and emitted
nothing. Silence read as success. A monitor must live in a different failure domain than the
thing it watches. This one runs locally.

What it alerts on (exit 2 = ALERT):
  * SiteTracker mirror `Last_Synced__c` older than --max-age-hours (default 36). This is the ONLY
    truly-automated sync, so it is the only hard alert. 36h spans a normal skipped/drifted run
    plus a weekend margin.
  * Cannot connect to Salesforce at all (exit 3).

What it reports but does NOT alert on: the manual syncs (Vetro -> Property_Location/Unit,
IronClad -> Agreement). They are run by hand, so daily staleness is expected, not a failure -
alerting on them would be noise. They appear in the status line so a human can eyeball them.

Exit codes (the PS wrapper keys off these): 0 healthy, 2 stale/alert, 3 connect error.
Writes a one-line status to sync-health-status.txt next to this script every run, so there is a
durable record even when no toast fires.
"""
import argparse
import datetime
import sys
from pathlib import Path

API = Path(r"C:\Users\cass\Work_Projects\SalesForce\api")
STATUS_FILE = Path(__file__).with_name("sync-health-status.txt")
NOW = datetime.datetime.now(datetime.timezone.utc)


def creds(fname):
    out = {}
    for line in (API / fname).read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def age_h(ts):
    if not ts:
        return None
    t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (NOW - t).total_seconds() / 3600


def write_status(line):
    stamp = NOW.strftime("%Y-%m-%d %H:%M UTC")
    STATUS_FILE.write_text(f"[{stamp}] {line}\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-hours", type=int, default=36)
    args = ap.parse_args()

    try:
        from simple_salesforce import Salesforce
        c = creds("Salesforce_Credentials.txt")
        sf = Salesforce(username=c["username"], password=c["password"],
                        security_token=c["security token"])
    except Exception as e:
        msg = f"ALERT: cannot connect to Salesforce to check sync health: {type(e).__name__}: {str(e)[:150]}"
        print(msg)
        write_status(msg)
        sys.exit(3)

    def newest(obj, field):
        r = sf.query(f"SELECT {field} FROM {obj} WHERE {field} != null "
                     f"ORDER BY {field} DESC LIMIT 1")["records"]
        return r[0][field] if r else None

    # --- primary alert: the automated SiteTracker sync ---
    st_ts = newest("SiteTracker_Project__c", "Last_Synced__c")
    st_age = age_h(st_ts)

    # --- informational: manual syncs ---
    pl_age = age_h(newest("Property_Location__c", "LastModifiedDate"))
    ag_age = age_h(newest("Agreement__c", "LastModifiedDate"))
    info = (f"Vetro->PropertyLocation {pl_age/24:.0f}d | "
            f"IronClad->Agreement {ag_age/24:.1f}d  (both manual, not alerted)")

    if st_age is None:
        msg = ("ALERT: SiteTracker mirror has NO Last_Synced__c at all - the sync has never "
               f"stamped a record. {info}")
        print(msg)
        write_status(msg)
        sys.exit(2)

    if st_age > args.max_age_hours:
        # Do NOT assert a cause here. This monitor observes ONE fact: the data is stale. It
        # cannot see GitHub, so it cannot distinguish "cron stopped" from "cron ran and failed".
        # The original wording claimed "the GitHub Actions cron likely stopped" and that guess
        # was WRONG for 22 days (2026-07-13 -> 08-04): the cron was firing on schedule every
        # day and failing in ~20s on Salesforce auth, because the SF password/token was rotated
        # 2026-07-13 locally and the GitHub Secrets were never updated to match. The confident
        # wrong cause is what sent the investigation away from the Actions tab. State the fact,
        # point at where the answer actually lives.
        msg = (f"ALERT: SiteTracker nightly sync is STALE - newest Last_Synced {st_age:.1f}h ago "
               f"(threshold {args.max_age_hours}h). Cause UNKNOWN from this PC - check the "
               f"Actions tab at github.com/Ubiquity-SoCal/Automation: runs failing (open the "
               f"newest run's log) vs no runs at all (scheduler/billing) are different problems. "
               f"If runs fail fast on auth, re-check the SF_MAIN_* repo secrets against "
               f"SalesForce/api/Salesforce_Credentials.txt. {info}")
        print(msg)
        write_status(msg)
        sys.exit(2)

    msg = f"OK: SiteTracker sync fresh ({st_age:.1f}h ago, threshold {args.max_age_hours}h). {info}"
    print(msg)
    write_status(msg)
    sys.exit(0)


if __name__ == "__main__":
    main()
