# DEPLOY PROTOCOL — READ BEFORE EDITING SALESFORCE METADATA

**Koa uses Lightning App Builder and Setup UI to make changes directly in the org.
If you edit XML here based on a stale repo file and deploy, you will silently
overwrite his work. This has happened. Do not repeat it.**

## The rule

Before editing ANY `.flexipage-meta.xml`, `.layout-meta.xml`, `.profile-meta.xml`,
`.object-meta.xml`, or similar metadata file in `force-app/main/default/`:

1. **Retrieve the live org version first.**
   ```
   cd tracker-lwc
   sf project retrieve start --metadata "FlexiPage:MDU_Opportunity_Record_Page" --target-org cass1@ubiquitygp.com
   ```
   This overwrites the local file with whatever is currently live in the org.

2. **Only then make your changes and deploy.**

3. **After a clean deploy, the repo and org are in sync — until someone touches
   Lightning App Builder again.** Always retrieve again next time.

## Known metadata that drifts frequently

- `FlexiPage:MDU_Opportunity_Record_Page` — Koa edits this in App Builder
- `FlexiPage:Business_Opportunity_Record_Page` — same
- `FlexiPage:Opportunity_Record_Page_Three_Column` — same
- `FlexiPage:Campaign_Record_Page` — newer, subject to drift
- Any Layout file under `layouts/`
- Any Profile file under `profiles/`

## Exceptions

- Files I just deployed in the same session — already known-current, skip retrieve.
- LWC bundle files (`lwc/*`, `classes/*`) — Koa doesn't edit those in the org UI,
  safe to edit from repo without retrieve.

## When drift is detected after retrieve

Don't silently reconcile. Point out the diff to Koa. His UI changes are the
intended state unless he says otherwise.

## Why this matters

Koa stopped making his own UI changes because my deploys kept reverting them.
That's a broken workflow — he shouldn't have to stop using the UI to protect
his changes from me.

See also:
- `~/.claude/projects/.../memory/feedback-sf-metadata-retrieve-first.md`
- `~/.claude/projects/.../memory/tracker-lwc-deployment.md`
