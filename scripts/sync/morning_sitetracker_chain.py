"""Once-a-day local run of the SiteTracker Automation chain, triggered from a Claude Code
SessionStart hook (see Work_Projects/.claude/settings.json).

WHY THIS EXISTS
---------------
The chain is supposed to run nightly as three GitHub Actions in Ubiquity-SoCal/Automation.
Those have been dead since 2026-07-13 because a Salesforce credential rotation was never
copied into the repo secrets, and the gap has had to be closed by hand three times (7/24,
8/4, 8/10). This makes the local close automatic instead of dependent on someone noticing.

THE TRAP THIS DELIBERATELY AVOIDS
---------------------------------
A local run that just syncs every morning would make the data permanently fresh, which would
make `sync_health_monitor.py` report OK forever and hide the fact that CI is still broken.
That is the exact failure mode that cost 22 days in July: silence read as success. So this
script also answers "is CI alive?" every morning and surfaces the verdict.

**Freshness is NOT the CI signal.** That was the first cut of this script and it was wrong:
after a local run the data stays inside the 36h window for a day and a half, so a
freshness check would report CI healthy when CI had done nothing. The real signal is whether
the mirror's newest `Last_Synced__c` has advanced PAST the value our own last local run left
behind. Only something other than us - i.e. the cron - can move it.

  * stamp advanced past our last local run -> CI_HEALTHY. Skip the chain, no redundant
                                              prod writes.
  * stamp still sitting where we left it    -> CI_DEAD. Run the chain, and keep saying
                                              CI_DEAD so the broken cron stays visible.

The verdict is what the hook injects into Claude's context at session start.

MODES
-----
  --report   Fast, no network. Prints the last run's verdict as hook JSON
             (hookSpecificOutput.additionalContext). Safe on every session start.
  (default)  Do the work, at most once per local calendar day. A failed attempt does not
             stamp the day, so the next session retries.
  --force    Ignore the once-a-day stamp (manual re-run).

EXIT CODES
----------
0 = handled (ran, skipped, or already done today). 2 = FAILED, and 2 specifically, because the
hook is registered `asyncRewake: true` and that only interrupts Claude on exit code 2. See
EXIT_FAIL below before changing any exit path.

Writes morning-chain.log (append), morning-chain-status.json and morning-chain.lock next to
this script; all three are gitignored. The snapshot probe runs first, so there is always a
rollback CSV in SalesForce/data/output/audit_logs/ before anything writes.

ONE WRITER AT A TIME
--------------------
The once-a-day stamp is only written when a chain FINISHES, so for the ~2 minutes a run takes
it is not yet set, and a second SessionStart in that window (a /clear, or a restart during the
morning run) would start a second chain writing to production Salesforce alongside the first.
A lock file closes that window; see acquire_lock().
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds  # noqa: E402

WORK = Path(r"C:\Users\cass\Work_Projects")
AUTO = WORK / "Automation" / "sitetracker"
SNAPSHOT = WORK / "SalesForce" / "scripts" / "_probes" / "2026-08-04-snapshot-sitetracker-state.py"
LOG = Path(__file__).with_name("morning-chain.log")
STATUS = Path(__file__).with_name("morning-chain-status.json")
LOCK = Path(__file__).with_name("morning-chain.lock")

# How long before a held lock is assumed abandoned. The full chain runs in about 2 minutes;
# 30 leaves a slow day plenty of room while still letting a killed run recover the same morning.
LOCK_STALE_MINUTES = 30

# Only used on the very first run, before we have a prior local stamp to compare against.
STALE_HOURS = 36

# EVERY failure path must exit with exactly this code. The SessionStart hook is registered with
# `asyncRewake: true`, which wakes Claude mid-session ONLY on exit code 2 - any other nonzero
# code is treated as an ordinary background failure and stays silent until the next session's
# --report. So a failed morning sync must not exit 1 or 3, or nobody hears about it today.
# For the same reason the hook command must NOT be wrapped in `|| true`: that would rewrite
# every failure to exit 0 and silently disarm the rewake.
EXIT_FAIL = 2

# Order matters: mirror sync -> link new projects -> surface onto Opportunity -> the
# mirror-bypass for Taylor's handoff fields. Same sequence the two GH workflows run.
CHAIN = [
    ("snapshot", SNAPSHOT),
    ("sync_sitetracker", AUTO / "sync_sitetracker.py"),
    ("link_sitetracker_opportunities", AUTO / "link_sitetracker_opportunities.py"),
    ("surface_to_opportunity", AUTO / "surface_to_opportunity.py"),
    ("surface_design_inputs_direct", AUTO / "surface_design_inputs_direct.py"),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def log(line):
    stamp = now().strftime("%Y-%m-%d %H:%M UTC")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {line}\n")
    print(line, flush=True)


def read_status():
    if not STATUS.exists():
        return {}
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_status(**kw):
    kw["written_utc"] = now().isoformat(timespec="seconds")
    STATUS.write_text(json.dumps(kw, indent=2), encoding="utf-8")


def acquire_lock():
    """Take the single-writer lock. True if we hold it, False if another run already does.

    Time-based only, deliberately: there is no PID liveness check because on Windows
    `os.kill(pid, 0)` does NOT probe the process the way it does on POSIX - it calls
    TerminateProcess, so a "is it still alive?" check would kill the very chain it was asking
    about, mid-write, against production. If you want liveness here, use a real Win32 handle
    query (OpenProcess/GetExitCodeProcess), never os.kill.
    """
    if LOCK.exists():
        held, started = {}, None
        try:
            held = json.loads(LOCK.read_text(encoding="utf-8"))
            started = datetime.datetime.fromisoformat(held["started_utc"])
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            started = None
        if started is None:
            log("lock file present but unreadable; taking it over")
        else:
            age_min = (now() - started).total_seconds() / 60
            if age_min < LOCK_STALE_MINUTES:
                log(f"another chain run (pid {held.get('pid', '?')}, started "
                    f"{age_min:.1f}m ago) holds the lock; standing down")
                return False
            log(f"stale lock from pid {held.get('pid', '?')} ({age_min:.0f}m old, cutoff "
                f"{LOCK_STALE_MINUTES}m) - that run died without releasing it; taking it over")
    LOCK.write_text(json.dumps({"pid": os.getpid(),
                                "started_utc": now().isoformat(timespec="seconds")}),
                    encoding="utf-8")
    return True


def release_lock():
    try:
        LOCK.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log(f"could not remove the lock file: {e}. It will age out in {LOCK_STALE_MINUTES}m.")


def sf_env():
    """The Automation scripts read SF_MAIN_*/SF_ST_* directly (CI style) and exit if unset."""
    env = dict(os.environ)
    for org, prefix in (("main", "SF_MAIN"), ("st", "SF_ST")):
        c = creds(org)
        env[f"{prefix}_USERNAME"] = c["username"]
        env[f"{prefix}_PASSWORD"] = c["password"]
        env[f"{prefix}_TOKEN"] = c["token"]
    return env


def connect():
    from simple_salesforce import Salesforce
    c = creds("main")
    return Salesforce(username=c["username"], password=c["password"], security_token=c["token"])


def newest_sync(sf):
    r = sf.query("SELECT MAX(Last_Synced__c) m FROM SiteTracker_Project__c")["records"][0]["m"]
    return r or None


def age_hours(ts):
    if not ts:
        return None
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (now() - dt).total_seconds() / 3600


def report():
    """Print hook JSON describing the last run. No network, no writes."""
    s = read_status()
    v = s.get("ci_verdict")
    when = s.get("written_utc", "?")
    if not s:
        ctx = ("SiteTracker morning chain: no run recorded yet. It fires on the first Claude Code "
               "session of each day and reports whether the GitHub Actions cron is alive.")
    elif v == "CI_HEALTHY":
        ctx = (f"SiteTracker morning chain ({when}): the mirror's Last_Synced advanced past our "
               f"last local run, so the GitHub Actions cron IS working again - the July "
               f"credential outage looks resolved. Local chain skipped, no redundant writes.")
    elif v == "CI_DEAD":
        ctx = (f"SiteTracker morning chain ({when}): the GitHub Actions cron is STILL DEAD - the "
               f"mirror's Last_Synced had not moved since our own last local run. Repo secrets "
               f"were never updated after the 2026-07-13 SF credential rotation. The local chain "
               f"ran and closed the gap: {json.dumps(s.get('chain', {}))}. Salesforce is current "
               f"but CI is NOT fixed; the SF_MAIN_* secrets still need pasting into "
               f"github.com/Ubiquity-SoCal/Automation (Settings > Secrets and variables > "
               f"Actions). Mention this to Koa.")
    elif v == "CI_DEAD_NO_ACTION":
        ctx = (f"SiteTracker morning chain ({when}): CI is still dead, but the data was already "
               f"current from a manual run, so the chain was skipped this time. The SF_MAIN_* "
               f"repo secrets still need fixing at github.com/Ubiquity-SoCal/Automation.")
    else:
        ctx = (f"SiteTracker morning chain ({when}): last attempt FAILED - "
               f"{s.get('error', 'unknown error')}. Salesforce may be stale; check "
               f"SalesForce/scripts/sync/morning-chain.log.")

    # A SUCCESSFUL chain never speaks: the rewake only fires on exit 2, and the async half
    # writes the status file a couple of minutes AFTER this report already printed. So on the
    # first session of a day this line necessarily describes yesterday, and a stale date reads
    # as "the sync didn't run" when it is running right then. Say which day it is out loud.
    if s and s.get("ran_on_date") != datetime.date.today().isoformat():
        ctx += (" NOTE: that verdict is from a PRIOR day, not today. Today's chain is starting in "
                "the background right now (about two minutes; it interrupts the session only if "
                "it fails). Its result lands in SalesForce/scripts/sync/morning-chain-status.json "
                "and morning-chain.log, and surfaces in this line at the NEXT session start. If "
                "Koa asks whether today's sync ran, read the log rather than trusting this line.")

    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}
    }))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print last verdict as hook JSON")
    ap.add_argument("--force", action="store_true", help="ignore the once-a-day stamp")
    args = ap.parse_args()

    if args.report:
        report()
        return

    today = datetime.date.today().isoformat()
    prev = read_status()
    if not args.force and prev.get("ran_on_date") == today:
        log(f"already handled today ({today}); nothing to do")
        return

    # Losing this race is a normal outcome, not a failure: the other process is doing the work.
    # Must stay exit 0 so it does not trip the asyncRewake and cry wolf at Koa.
    if not acquire_lock():
        return
    try:
        run_chain(today, prev)
    finally:
        # finally, not a trailing call: run_chain exits via sys.exit(EXIT_FAIL) on every failure
        # path, and SystemExit would otherwise carry us past the release and wedge tomorrow's run
        # until the 30m cutoff.
        release_lock()


def run_chain(today, prev):
    """The chain itself. Caller holds the lock. Exits EXIT_FAIL on any failure."""
    try:
        sf = connect()
        current = newest_sync(sf)
    except Exception as e:
        log(f"FAILED to reach Salesforce: {type(e).__name__}: {str(e)[:200]}")
        log("The SiteTracker mirror was NOT refreshed. If this is an auth error, check whether the "
            "SF password/token rotated again (SalesForce/api/Salesforce_Credentials.txt).")
        write_status(ci_verdict="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}")
        sys.exit(EXIT_FAIL)

    baseline = prev.get("synced_at_after_local_run")
    age = age_hours(current)

    # --- is CI alive? The stamp must have moved past what OUR last run left behind. ---
    if baseline is None:
        # No prior local run to compare against. Fall back to plain staleness for the
        # run/skip decision and refuse to claim CI is healthy on this evidence.
        ci_alive = False
        needs_run = age is None or age > STALE_HOURS
        log(f"no prior local baseline; newest Last_Synced age="
            f"{'none' if age is None else f'{age:.1f}h'} -> "
            f"{'running chain' if needs_run else 'data already current, skipping'}")
    else:
        ci_alive = current is not None and current > baseline
        needs_run = not ci_alive
        log(f"baseline from our last local run: {baseline} | now: {current} -> "
            f"CI {'ALIVE' if ci_alive else 'DEAD'}")

    if ci_alive:
        log("GitHub Actions cron is working; skipping the local chain")
        write_status(ci_verdict="CI_HEALTHY", age_hours=None if age is None else round(age, 1),
                     ran_on_date=today, synced_at_after_local_run=baseline, chain={})
        return

    if not needs_run:
        log("CI is dead but the data is already current (recent manual run); skipping the chain")
        write_status(ci_verdict="CI_DEAD_NO_ACTION",
                     age_hours=None if age is None else round(age, 1),
                     ran_on_date=today, synced_at_after_local_run=current, chain={})
        return

    log("running the local chain to close the gap")
    results = {}
    for name, script in CHAIN:
        if not script.exists():
            log(f"  [{name}] SKIPPED - script not found at {script}")
            results[name] = "missing"
            continue
        proc = subprocess.run([sys.executable, "-u", str(script)],
                              env=sf_env(), capture_output=True, text=True, cwd=str(WORK))
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"--- {name} (exit {proc.returncode}) ---\n")
            fh.write((proc.stdout or "") + "\n")
            if proc.returncode != 0:
                fh.write("STDERR:\n" + (proc.stderr or "") + "\n")
        if proc.returncode != 0:
            log(f"  [{name}] FAILED exit {proc.returncode}: {(proc.stderr or '')[:200]}")
            results[name] = f"exit {proc.returncode}"
            # No ran_on_date -> the next session retries instead of waiting a day.
            write_status(ci_verdict="ERROR", chain=results,
                         synced_at_after_local_run=baseline,
                         error=f"{name} exited {proc.returncode}")
            log(f"Chain ABORTED at {name}. Steps so far: {json.dumps(results)}. Salesforce may be "
                f"partially updated - full output in {LOG.name}, rollback CSVs in "
                f"SalesForce/data/output/audit_logs/.")
            sys.exit(EXIT_FAIL)
        log(f"  [{name}] ok: {' | '.join((proc.stdout or '').strip().splitlines()[-2:])}")
        results[name] = "ok"

    # Re-read the stamp our own run just wrote. This becomes the baseline that lets the
    # NEXT run tell CI's writes apart from ours.
    try:
        after = newest_sync(sf)
    except Exception:
        after = None
    write_status(ci_verdict="CI_DEAD", age_hours=None if age is None else round(age, 1),
                 ran_on_date=today, synced_at_after_local_run=after or current, chain=results)
    log(f"local chain complete; new baseline {after}. Salesforce is current but CI is STILL BROKEN")


if __name__ == "__main__":
    main()
