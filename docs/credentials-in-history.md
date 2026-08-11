# Salesforce credentials in this repo's git history

Recorded 2026-08-11.

## What is in the history

Until commit `ab32ab4` ("Route every script through _shared/sf_auth"), 302 files in this repo
each carried a literal Salesforce login. Two credential sets are involved:

| Org | Username | Password | Security token |
|---|---|---|---|
| Main (`cass1@ubiquitygp.com`) | not secret | `Hawa...` | `IBSK...` |
| SiteTracker | not secret | `Kara...` | `Ktc1...` |

Removing them from `HEAD` does not remove them from history. Anyone who can clone this repo
can still recover both sets from any commit before `ab32ab4`.

## Assessment

**All four values are dead.** Verified 2026-08-11 by comparing each against the current
contents of `api/Salesforce_Credentials.txt` and `api/SiteTracker_Credentials.txt`. Neither
password nor either token matches what is live now. The main org rotated on 2026-07-13, which
is the same rotation that broke the GitHub Actions secrets and killed the nightly SiteTracker
cron. The SiteTracker org rotated separately at some point before that.

The repo (`Ubiquity-SoCal/salesforce-mdu`) is private.

So the exposure is historical, not active. There is no credential in this history that grants
access to anything today.

## Why history was NOT rewritten

A `git filter-repo` pass would scrub the literals, and it was rejected on cost:

1. **It orphans the parent repo.** `work-projects-backup` records a submodule pointer to a
   specific SHA in every commit that touched `SalesForce/`. Rewriting rewrites every SHA here,
   so those recorded pointers would reference commits that no longer exist. Checking out any
   historical parent commit and running `git submodule update` would fail from then on. The
   parent's own history would have to be rewritten in lockstep to avoid that, which multiplies
   the blast radius across every project in the repo, not just Salesforce.
2. **It requires a force push to a shared remote.** Any other clone or CI checkout diverges
   and has to be re-cloned.
3. **The benefit is close to zero.** The thing a rewrite protects is already worthless. Trading
   a permanently broken submodule history for scrubbing four dead strings is a bad deal.

The correct response to a leaked credential is rotation, and rotation already happened.

## If that decision changes

It only becomes worth doing if one of these turns out to be true:

- One of the four values is reused somewhere else that is still live (a different system, a
  personal account). Rotate that instead; it is cheaper and actually fixes the problem.
- The repo becomes public, or is shared outside Ubiquity-SoCal. Then scrub before sharing.

If it does have to happen, rewrite the parent and the submodule together in one planned pass,
re-clone every working copy afterward, and expect to fix up the submodule pointers by hand.

## Going forward

`_shared/sf_auth.py` is now the only place credentials are read. It takes environment
variables first (`SF_MAIN_*` / `SF_ST_*`, which is how CI supplies them) and falls back to the
gitignored `api/*_Credentials.txt` files locally. Nothing else should ever hold a literal.

Related: [sf-credential-rotation-breaks-github-secrets] covers the other half of the 7/13
rotation, which is that the same rotation has to be applied in two places (the local creds
file and the repo secrets at github.com/Ubiquity-SoCal/Automation) or CI dies silently while
local runs keep passing.
