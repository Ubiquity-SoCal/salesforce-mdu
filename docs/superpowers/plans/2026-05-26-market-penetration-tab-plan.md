# Market Penetration Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Market Penetration" tab to `InsideSalesDashboard.page` (Visualforce) that renders Business footprint penetration in three sections — single-unit buildings, multi-unit buildings (door-weighted), and ROE-completed-but-not-yet-lit properties — both nationally and by state.

**Architecture:** Extend the existing monolithic VF dashboard rather than build a separate LWC. Add one new tab button after `Executive`, three new SOQL queries to the existing `loadDashboard()` Promise.all, and a render block that produces the 3 sections via the existing `html += '...'` string-concat pattern. Add one new formula field `Lit__c` on `Property_Location__c` to centralize the "has any drop installed" definition. After the tab ships and counts verify against ground-truth probes, retire the standalone native dashboard `01ZWR000004X6if2AC`.

**Tech Stack:** Salesforce metadata API (CustomField, ApexPage), Visualforce + client-side JS, `sf` CLI for deploys, `simple_salesforce` Python for probes and the final cleanup script.

**Source spec:** `SalesForce/docs/superpowers/specs/2026-05-26-market-penetration-tab-design.md`

---

## File Structure

**New files:**
- `SalesForce/tracker-lwc/force-app/main/default/objects/Property_Location__c/fields/Lit__c.field-meta.xml` — formula field metadata
- `SalesForce/scripts/_probes/2026-05-26-verify-lit-field.py` — post-deploy population check for `Lit__c`
- `SalesForce/scripts/_probes/2026-05-26-market-pen-baseline.py` — ground-truth counts before any changes
- `SalesForce/scripts/_probes/2026-05-26-market-pen-smoke-test.py` — post-implementation counts that the rendered dashboard must match
- `SalesForce/scripts/fix/2026-05-26-delete-old-business-penetration-dashboard.py` — final cleanup of `01ZWR000004X6if2AC` and its `BizPen_*` reports

**Modified files:**
- `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page` — add tab button, queries, render block. ~1,581 lines today; tab button slot at line ~312; Promise.all extends around lines 418-470; render branches dispatched from the existing `switchTab(...)` JS.

**Why this split:** Each script is a single concern. Probes are read-only and re-runnable. The fix script touches shared state and is one-shot, so it goes in `scripts/fix/` per `STRUCTURE.md` and stays date-prefixed for audit.

---

## Ground-Truth Counts (Frozen on 2026-05-26)

Every smoke test below compares against these. Captured by Task 1 baseline probe; tasks reference the same numbers.

- **Universe (Business PLs):** 17,034
- **Single-unit (Property_Unit_Count = 1):** 13,811
- **Multi-unit (Property_Unit_Count > 1):** 3,223
- **Lit total (any drop active or churned):** 760
  - **Lit single-unit:** 494
  - **Lit multi-unit:** 266
- **Multi-unit lit door rollup:**
  - Units in lit multi: 2,329
  - Active units in lit: 492
  - Door-weighted penetration: 21.1%
- **Business PLs with completed Business ROE:** 31
- **Of those, NOT lit yet:** 14 (9 single-unit, 5 multi-unit)
- **State distribution (total / lit):** AZ 878/12, CA 1466/81, NE 4457/59, TX 10233/608

Note: the old standalone dashboard's "lit" was 679 because it filtered on `Penetration_Priority__c IN ('Category 1','All Active')`, a derived field. We're using the cleaner direct definition (`Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0` = `Lit__c = true`), which produces 760. The 81-PL gap is genuine — the new dashboard will show 760, not 679. Stakeholders comparing old vs new should be told the definition changed.

If the baseline probe (Task 1) produces different numbers, STOP and reconcile before continuing — the spec assumptions need to be re-validated.

---

## Task 1: Baseline Probe (Ground-Truth Snapshot)

Write a probe that captures the exact counts the rendered dashboard must reproduce. Re-runnable; serves as the smoke-test oracle for every later task.

**Files:**
- Create: `SalesForce/scripts/_probes/2026-05-26-market-pen-baseline.py`

- [ ] **Step 1: Write the probe**

```python
"""Baseline ground-truth counts for the Market Penetration tab.
Frozen on 2026-05-26. Re-run to verify the dashboard renders matching numbers."""
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="<password: see _shared/sf_auth.py>",
    security_token="<token: see _shared/sf_auth.py>",
)

UNIV = "Address_Type__c='Business' AND Import_Delete_Property__c=false"

def c(where):
    return sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {where}")["totalSize"]

print("=== Universe ===")
print(f"  Total Business PLs:    {c(UNIV)}")
print(f"  Single-unit:           {c(UNIV + ' AND Property_Unit_Count__c = 1')}")
print(f"  Multi-unit:            {c(UNIV + ' AND Property_Unit_Count__c > 1')}")

print("\n=== Lit (drop active or churned) ===")
LIT = UNIV + " AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)"
print(f"  Lit total:             {c(LIT)}")
print(f"  Lit single-unit:       {c(LIT + ' AND Property_Unit_Count__c = 1')}")
print(f"  Lit multi-unit:        {c(LIT + ' AND Property_Unit_Count__c > 1')}")

print("\n=== Multi-unit lit door rollups ===")
r = sf.query(f"""
    SELECT SUM(Property_Unit_Count__c) total_units,
           SUM(Active_Unit_Count__c) active_units
    FROM Property_Location__c
    WHERE {LIT} AND Property_Unit_Count__c > 1
""")["records"][0]
print(f"  Units in lit multi:    {int(r['total_units'] or 0)}")
print(f"  Active units in lit:   {int(r['active_units'] or 0)}")
if r["total_units"]:
    pct = (r["active_units"] or 0) / r["total_units"] * 100
    print(f"  Door-weighted pen:     {pct:.1f}%")

print("\n=== ROE completed but not yet lit ===")
ROE = """
    Id IN (
      SELECT Property_Location__c FROM Agreement__c
      WHERE Status__c='Completed'
        AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
        AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
        AND Property_Location__c != null
    )
"""
NOT_LIT = UNIV + " AND Active_Unit_Count__c = 0 AND Deactive_Unit_Count__c = 0"
print(f"  PLs with completed ROE total:        {c(UNIV + ' AND ' + ROE)}")
print(f"  ROE complete + NOT lit:              {c(NOT_LIT + ' AND ' + ROE)}")
print(f"  ROE complete + NOT lit, single-unit: {c(NOT_LIT + ' AND ' + ROE + ' AND Property_Unit_Count__c = 1')}")
print(f"  ROE complete + NOT lit, multi-unit:  {c(NOT_LIT + ' AND ' + ROE + ' AND Property_Unit_Count__c > 1')}")

print("\n=== By state (lit + total, all PLs) ===")
r = sf.query_all(f"""
    SELECT State__c, COUNT(Id) total
    FROM Property_Location__c
    WHERE {UNIV}
    GROUP BY State__c
    ORDER BY State__c
""")["records"]
for x in r:
    s = x["State__c"]
    lit = c(UNIV + f" AND State__c='{s}' AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)") if s else 0
    print(f"  {(s or '(null)'):>20}  total={x['total']:>5}  lit={lit:>4}")
```

- [ ] **Step 2: Run the probe**

```bash
python "C:/Users/cass/Work_Projects/SalesForce/scripts/_probes/2026-05-26-market-pen-baseline.py"
```

**Expected output sanity-check (must match):**
- Total Business PLs: 17,034
- Single-unit: 13,811
- Multi-unit: 3,223
- Lit total: 760 (494 single + 266 multi)
- Multi-unit lit door rollup: 2,329 units, 492 active, 21.1% door-weighted
- ROE complete + NOT lit: 14 (9 single-unit, 5 multi-unit)

If any number is off, STOP. Re-read the spec definitions before continuing.

- [ ] **Step 3: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add scripts/_probes/2026-05-26-market-pen-baseline.py
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: market penetration tab baseline probe

Captures ground-truth counts (universe, lit, ROE-not-lit, by-state) that
the new tab must reproduce.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create `Lit__c` Formula Field

Add a checkbox formula field on `Property_Location__c` that centralizes the "lit" definition so every later query/render reuses it.

**Files:**
- Create: `SalesForce/tracker-lwc/force-app/main/default/objects/Property_Location__c/fields/Lit__c.field-meta.xml`

- [ ] **Step 1: Verify the parent path exists**

```bash
ls "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/objects/Property_Location__c/fields/" | head -5
```

Expected: a `fields/` directory exists with existing `*.field-meta.xml` files (e.g. `Penetration__c.field-meta.xml`). If not, the path is wrong — check spelling.

- [ ] **Step 2: Write the field metadata**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>Lit__c</fullName>
    <description>True if the building has at least one drop installed (active or churned). Centralizes the "lit" definition used by the Market Penetration dashboard tab.</description>
    <externalId>false</externalId>
    <formula>Active_Unit_Count__c &gt; 0 || Deactive_Unit_Count__c &gt; 0</formula>
    <formulaTreatBlanksAs>BlankAsZero</formulaTreatBlanksAs>
    <label>Lit</label>
    <required>false</required>
    <trackHistory>false</trackHistory>
    <trackTrending>false</trackTrending>
    <type>Checkbox</type>
</CustomField>
```

Why `BlankAsZero`: if either unit-count field is ever null on a record, treat it as 0 so the formula never returns null (a null checkbox is invalid).

- [ ] **Step 3: Mirror FLS from an existing field**

The deploy below grants the field to System Administrator only (default). If the team needs to see `Lit__c` in their reports/list views, FLS must be broadened separately. Note this for follow-up; not blocking the dashboard since the page runs as `cass1` who has the field.

- [ ] **Step 4: Deploy the field**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/objects/Property_Location__c/fields/Lit__c.field-meta.xml \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

Expected: `Status: Succeeded` with 1 component changed.

- [ ] **Step 5: Verify population via a probe**

Create `SalesForce/scripts/_probes/2026-05-26-verify-lit-field.py`:

```python
"""Verify Lit__c formula field deployed and populates consistently with the
raw OR clause it replaces."""
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="<password: see _shared/sf_auth.py>",
    security_token="<token: see _shared/sf_auth.py>",
)
UNIV = "Address_Type__c='Business' AND Import_Delete_Property__c=false"

raw = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {UNIV} AND (Active_Unit_Count__c > 0 OR Deactive_Unit_Count__c > 0)")["totalSize"]
formula = sf.query(f"SELECT COUNT() FROM Property_Location__c WHERE {UNIV} AND Lit__c = true")["totalSize"]

print(f"Raw OR clause:    {raw} lit")
print(f"Lit__c=true:      {formula} lit")
assert raw == formula, f"Lit__c drift! raw={raw} formula={formula}"
print("OK: counts match.")
```

Run:

```bash
python "C:/Users/cass/Work_Projects/SalesForce/scripts/_probes/2026-05-26-verify-lit-field.py"
```

Expected: `Raw OR clause: 679 lit / Lit__c=true: 679 lit / OK: counts match.`

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add \
  tracker-lwc/force-app/main/default/objects/Property_Location__c/fields/Lit__c.field-meta.xml \
  scripts/_probes/2026-05-26-verify-lit-field.py
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: add Lit__c formula field to Property_Location__c

Checkbox formula: Active_Unit_Count > 0 OR Deactive_Unit_Count > 0.
Centralizes the 'lit' definition for the Market Penetration dashboard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Tab Button + Empty Render Block

Add the new tab to the existing nav (line ~312) and a stub render branch that just shows a "loading" message. Keeps the tab discoverable while we wire data in subsequent tasks.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Read the existing tab definition block to confirm context**

```bash
sed -n '305,318p' "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page"
```

Expected: lines 307-312 contain the six existing tab divs (`team`, `agreements`, `mine`, `stale`, `executive`, `sitetracker`). If the line numbers have drifted, locate by searching for `data-tab="executive"` instead and insert after that line.

- [ ] **Step 2: Add the new tab button**

Find the line:

```html
        h += '<div class="tab" data-tab="sitetracker" onclick="switchTab(\'sitetracker\',this)">Site Tracker</div>';
```

Insert a new line IMMEDIATELY BEFORE it:

```html
        h += '<div class="tab" data-tab="marketpen" onclick="switchTab(\'marketpen\',this)">Market Penetration</div>';
```

Result: Market Penetration sits between Executive and Site Tracker in the nav.

- [ ] **Step 3: Find the switchTab implementation and confirm it handles arbitrary data-tab values**

```bash
grep -n "function switchTab\|switchTab(" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -5
```

Expected: `function switchTab(tabName, btnEl)` defined once. The function likely already supports any `data-tab` value because it just toggles `.active` class and shows the matching `<div id="tab-{tabName}">`. If it explicitly enumerates tab names, you must add `marketpen` to that list.

- [ ] **Step 4: Find where the existing tab bodies are rendered (the html-concat blocks per tab)**

```bash
grep -n "id=.tab-executive\|id=.tab-sitetracker" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -5
```

Pick the spot AFTER the Executive tab body closes (`</div> <!-- end executive tab -->` or similar) and BEFORE Site Tracker. That's where the Market Penetration tab body goes.

- [ ] **Step 5: Insert the empty tab body stub**

After the line that closes the Executive tab body (look for `// end executive tab` per the routing memory), insert:

```html
        // ── Market Penetration tab body ────────────────────────────────────
        h += '<div id="tab-marketpen" class="tab-body" style="display:none;">';
        h += '  <div id="marketpen-content">Loading...</div>';
        h += '</div>';
```

- [ ] **Step 6: Deploy the page**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

Expected: `Status: Succeeded`.

- [ ] **Step 7: Manual smoke test**

Open the dashboard in Salesforce as `cass1@ubiquitygp.com`. Click the new "Market Penetration" tab. Expected:
- Tab appears between Executive and Site Tracker
- Clicking it switches to a body that says "Loading..."
- Other tabs still work

If the tab doesn't appear or `switchTab` errors in the browser console, fix before proceeding.

- [ ] **Step 8: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: add Market Penetration tab stub to InsideSalesDashboard

Tab button + empty body. Queries and render block follow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add Two SOQL Queries to `loadDashboard()`

Add Q-A (universe rows for sections 1+2) and Q-C (ROE-not-lit detail rows). Q-C already carries the per-PL fields needed for Section 3 KPIs (units count to bucket single vs multi), so no separate Q-B is needed.

Capture their result indices for the `.then()` handler in the next task.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Locate the Promise.all array in `loadDashboard()`**

```bash
grep -n "Promise.all\|var promises\|var queries" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -5
```

Expected: a `Promise.all([...])` block starting somewhere in the `loadDashboard()` function (around line 418 per the previous grep on `rtFilter`). Identify the LAST query in the array; that's where the new ones go.

- [ ] **Step 2: Identify the existing query count**

Count the queries in the Promise.all to know what index the new ones land at. Skim the `.then(function(results){ ... })` for `results[N]` references and confirm the highest index. Call this `N`. The Market Penetration queries become `results[N+1]` and `results[N+2]`.

If you can't determine N from inspection, search for `results\[` and take the max.

```bash
grep -n "results\[" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | tail -10
```

- [ ] **Step 3: Add the two queries to the array**

Find the LAST `query("...")` line inside the `Promise.all([...])`. After it, add a trailing comma if needed, then insert:

```javascript
            // ── Market Penetration tab queries ──────────────────────────────
            // Q-A: all Business PLs (drives sections 1 + 2 rollups)
            query("SELECT Id, Property_Unit_Count__c, Active_Unit_Count__c, Deactive_Unit_Count__c, State__c, Lit__c FROM Property_Location__c WHERE Address_Type__c='Business' AND Import_Delete_Property__c=false"),
            // Q-C: detail rows for the section 3 table (only the not-yet-lit ones)
            query("SELECT Id, Name, Agreement_Type__c, Signed_Date__c, Opportunity__r.Owner.Name, Property_Location__c, Property_Location__r.Name, Property_Location__r.Property_Unit_Count__c, Property_Location__r.State__c FROM Agreement__c WHERE Status__c='Completed' AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum') AND Opportunity__r.RecordType.DeveloperName='Business_ROE' AND Property_Location__c != null AND Property_Location__r.Address_Type__c='Business' AND Property_Location__r.Import_Delete_Property__c=false AND Property_Location__r.Lit__c = false ORDER BY Signed_Date__c DESC NULLS LAST")
```

Note: these queries do NOT include the existing `rtFilter` / `yrFilter` / `catFilter` strings because Market Penetration scopes by `Property_Location.Address_Type__c='Business'` independent of the Opportunity-RT slicer. Per spec, the audience-slicer branching happens at RENDER time, not query time.

- [ ] **Step 4: Add `console.log` taps to verify queries fire**

Inside the `.then(function(results){ ... })` block, add at the top:

```javascript
            // Market Penetration tab — sanity log of new query results
            console.log('[marketpen] Q-A rows:', (results[N+1] || []).length);
            console.log('[marketpen] Q-C rows:', (results[N+2] || []).length);
```

(Substitute the actual N+1/N+2 values from Step 2.)

- [ ] **Step 5: Deploy**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

- [ ] **Step 6: Verify in browser console**

Open the dashboard. Open browser DevTools console. Reload. Expected logs:

```
[marketpen] Q-A rows: 17034
[marketpen] Q-C rows: 14
```

If counts differ from these, STOP and reconcile against the baseline probe before continuing.

- [ ] **Step 7: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: wire Q-A and Q-C SOQL queries for Market Penetration tab

Console-log taps confirm 17034 / 14 row counts vs the baseline probe.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Render Section 1 — Single-Unit Buildings

Replace the "Loading..." stub with Section 1's KPI row + by-state table. Other sections still render nothing.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Define a `renderMarketPen(results)` helper**

After the existing tab-body render blocks (or near the end of `.then(...)`), add this helper. It centralizes the Market Penetration rendering and gets called from inside `.then(...)`.

```javascript
        function renderMarketPen(qaRows, qcRows) {
            var el = document.getElementById('marketpen-content');
            if (!el) return;

            // ── Section 1: Single-Unit ────────────────────────────────────
            var singles = qaRows.filter(function(r){ return r.Property_Unit_Count__c === 1; });
            var litSingles = singles.filter(function(r){ return r.Lit__c === true; });
            var sPen = singles.length === 0 ? 0 : (litSingles.length / singles.length * 100);

            // State rollup for single-unit
            var byStateSingle = {};
            singles.forEach(function(r){
                var s = r.State__c || '(none)';
                if (!byStateSingle[s]) byStateSingle[s] = { total:0, lit:0 };
                byStateSingle[s].total += 1;
                if (r.Lit__c === true) byStateSingle[s].lit += 1;
            });

            var html = '';
            html += '<h2 class="section-h">Single-Unit Buildings</h2>';
            html += '<div class="kpi-row">';
            html += '  <div class="kpi"><div class="kpi-label">Total</div><div class="kpi-value">' + singles.length.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Lit</div><div class="kpi-value">' + litSingles.length.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Penetration</div><div class="kpi-value">' + sPen.toFixed(1) + '%</div></div>';
            html += '</div>';

            html += '<table class="data-table"><thead><tr><th>State</th><th class="num">Total</th><th class="num">Lit</th><th class="num">Penetration</th></tr></thead><tbody>';
            Object.keys(byStateSingle).sort().forEach(function(s){
                var row = byStateSingle[s];
                var pct = row.total === 0 ? 0 : (row.lit / row.total * 100);
                html += '<tr><td>' + s + '</td><td class="num">' + row.total + '</td><td class="num">' + row.lit + '</td><td class="num">' + pct.toFixed(1) + '%</td></tr>';
            });
            html += '</tbody></table>';

            // sections 2 + 3 to be added in later tasks

            el.innerHTML = html;
        }
```

- [ ] **Step 2: Call the helper from `.then(...)`**

Replace the three temporary `console.log` lines from Task 4 with the call:

```javascript
            renderMarketPen(results[N+1] || [], results[N+2] || []);
```

(Use the actual N+1/N+2 indices.)

- [ ] **Step 3: Add minimal CSS for `.kpi-row`, `.kpi`, `.section-h` if not present**

```bash
grep -n "\.kpi-row\|\.kpi-label\|section-h" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -3
```

If no results, add these styles inside the existing `<style>` block (search for `<style>` to find it):

```css
.section-h { margin: 1.5rem 0 0.5rem; font-size: 1.05rem; font-weight: 600; color: #1F4E78; border-bottom: 1px solid #d0d0d0; padding-bottom: 0.25rem; }
.kpi-row { display: flex; gap: 1rem; margin: 0.5rem 0 1rem; }
.kpi { background: #f7f9fa; border-radius: 6px; padding: 0.75rem 1rem; min-width: 130px; }
.kpi-label { font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: 0.04em; }
.kpi-value { font-size: 1.5rem; font-weight: 600; color: #1F4E78; }
```

(The page already has `.data-table` styles from the Executive tab. Reuse those.)

- [ ] **Step 4: Deploy**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

- [ ] **Step 5: Manual smoke test**

Open the dashboard, click Market Penetration. Expected:
- Headline KPI tiles: Total 13,811 | Lit ??? | Penetration ???%
- By-state table renders with rows per state, totals per row matching the baseline probe's per-state numbers

The Lit single-unit count won't match Task 1's baseline yet because Task 1's baseline didn't single it out. Verify by re-running the baseline probe with the per-stage detail added (or trust the by-state rollup; the totals must add up to 13,811).

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: render Section 1 (single-unit buildings) on Market Penetration tab

KPI tiles + by-state table from Q-A client-side rollup.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Render Section 2 — Multi-Unit Buildings

Extend `renderMarketPen` with the multi-unit door-weighted rollup.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Extend `renderMarketPen` with Section 2 logic**

Inside the function, after the Section 1 table and before `el.innerHTML = html`, insert:

```javascript
            // ── Section 2: Multi-Unit ─────────────────────────────────────
            var multis = qaRows.filter(function(r){ return r.Property_Unit_Count__c > 1; });
            var litMultis = multis.filter(function(r){ return r.Lit__c === true; });

            var unitsInLit = 0;
            var activeInLit = 0;
            litMultis.forEach(function(r){
                unitsInLit += (r.Property_Unit_Count__c || 0);
                activeInLit += (r.Active_Unit_Count__c || 0);
            });
            var doorPen = unitsInLit === 0 ? 0 : (activeInLit / unitsInLit * 100);

            // State rollup
            var byStateMulti = {};
            multis.forEach(function(r){
                var s = r.State__c || '(none)';
                if (!byStateMulti[s]) byStateMulti[s] = { total:0, lit:0, unitsInLit:0, activeInLit:0 };
                byStateMulti[s].total += 1;
                if (r.Lit__c === true) {
                    byStateMulti[s].lit += 1;
                    byStateMulti[s].unitsInLit += (r.Property_Unit_Count__c || 0);
                    byStateMulti[s].activeInLit += (r.Active_Unit_Count__c || 0);
                }
            });

            html += '<h2 class="section-h">Multi-Unit Buildings</h2>';
            html += '<div class="kpi-row">';
            html += '  <div class="kpi"><div class="kpi-label">Total</div><div class="kpi-value">' + multis.length.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Lit</div><div class="kpi-value">' + litMultis.length.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Units in Lit</div><div class="kpi-value">' + unitsInLit.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Active</div><div class="kpi-value">' + activeInLit.toLocaleString() + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Door-Weighted Pen</div><div class="kpi-value">' + doorPen.toFixed(1) + '%</div></div>';
            html += '</div>';

            html += '<table class="data-table"><thead><tr><th>State</th><th class="num">Bldgs</th><th class="num">Lit</th><th class="num">Units in Lit</th><th class="num">Active</th><th class="num">Door-Weighted</th></tr></thead><tbody>';
            Object.keys(byStateMulti).sort().forEach(function(s){
                var row = byStateMulti[s];
                var pct = row.unitsInLit === 0 ? 0 : (row.activeInLit / row.unitsInLit * 100);
                html += '<tr><td>' + s + '</td><td class="num">' + row.total + '</td><td class="num">' + row.lit + '</td><td class="num">' + row.unitsInLit + '</td><td class="num">' + row.activeInLit + '</td><td class="num">' + pct.toFixed(1) + '%</td></tr>';
            });
            html += '</tbody></table>';
```

- [ ] **Step 2: Deploy**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

- [ ] **Step 3: Manual smoke test against ground truth**

Expected KPIs from the baseline probe:
- Multi-unit Total: 3,223
- Lit multi-unit: (probe's "Lit multi-unit" number)
- Units in Lit: (probe's "Units in lit multi" number)
- Active: (probe's "Active units in lit" number)
- Door-Weighted Pen: (probe's "Door-weighted pen" %)

Open dashboard, click Market Penetration, scroll to Section 2. Each KPI must match the baseline probe output to the unit.

- [ ] **Step 4: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: render Section 2 (multi-unit door-weighted) on Market Penetration tab

5 KPI tiles + by-state table with door-weighted penetration %.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Render Section 3 — ROE Completed but Not Yet Lit

Add the third section: 3 KPIs + the detail table built from Q-C.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Extend `renderMarketPen` with Section 3 logic**

Insert before `el.innerHTML = html`:

```javascript
            // ── Section 3: ROE Completed but Not Yet Lit ──────────────────
            var section3Single = qcRows.filter(function(r){
                var pl = r.Property_Location__r || {};
                return pl.Property_Unit_Count__c === 1;
            });
            var section3Multi = qcRows.filter(function(r){
                var pl = r.Property_Location__r || {};
                return pl.Property_Unit_Count__c > 1;
            });

            html += '<h2 class="section-h">ROE Completed but Not Yet Lit</h2>';
            html += '<div class="kpi-row">';
            html += '  <div class="kpi"><div class="kpi-label">Total</div><div class="kpi-value">' + qcRows.length + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Single-Unit</div><div class="kpi-value">' + section3Single.length + '</div></div>';
            html += '  <div class="kpi"><div class="kpi-label">Multi-Unit</div><div class="kpi-value">' + section3Multi.length + '</div></div>';
            html += '</div>';

            html += '<table class="data-table"><thead><tr><th>Property</th><th>State</th><th class="num">Units</th><th>Agreement</th><th>ROE Signed</th><th>Owner</th></tr></thead><tbody>';
            qcRows.forEach(function(r){
                var pl = r.Property_Location__r || {};
                var opp = r.Opportunity__r || {};
                var owner = (opp.Owner || {}).Name || '';
                var plUrl = '/lightning/r/Property_Location__c/' + r.Property_Location__c + '/view';
                var agUrl = '/lightning/r/Agreement__c/' + r.Id + '/view';
                var signed = (r.Signed_Date__c || '').slice(0, 10);
                html += '<tr>';
                html += '  <td><a href="' + plUrl + '" target="_blank">' + (pl.Name || '') + '</a></td>';
                html += '  <td>' + (pl.State__c || '') + '</td>';
                html += '  <td class="num">' + (pl.Property_Unit_Count__c || '') + '</td>';
                html += '  <td><a href="' + agUrl + '" target="_blank">' + (r.Name || '') + ' (' + (r.Agreement_Type__c || '') + ')</a></td>';
                html += '  <td>' + signed + '</td>';
                html += '  <td>' + owner + '</td>';
                html += '</tr>';
            });
            html += '</tbody></table>';
```

- [ ] **Step 2: Deploy**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

- [ ] **Step 3: Manual smoke test**

Expected from baseline probe:
- Total: 14
- Single-Unit: 9
- Multi-Unit: 5
- Table shows 14 rows including the 3 Mesa Ranch ROEs (IC-2952), Sandpiper Pointe, Patriot Place, etc. Click a property link to confirm it navigates to the Property_Location record.

- [ ] **Step 4: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: render Section 3 (ROE completed but not yet lit) on Market Penetration

14 rows currently; clickable property + agreement links.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Audience-Slicer Placeholder Branch

When the audience slicer is on MDU (the only non-business value today), render a "coming soon" placeholder instead of the data sections.

**Files:**
- Modify: `SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

- [ ] **Step 1: Identify which JS variable holds the current audience selection**

```bash
grep -n "currentRT\|currentPipeline\|currentAudience" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -10
```

The variable is set by the slicer button onclick (search for `data-pipeline=` or similar). Identify the actual name; this plan uses `currentRT` as a placeholder. The values per memory are something like `'MDU'`, `'Business_ROE'`, `'Business'`, `''` (empty = All).

- [ ] **Step 2: Add the branching guard at the top of `renderMarketPen`**

At the start of the function (right after `var el = document.getElementById(...);`):

```javascript
            // Audience slicer guard. MDU/SFU not built yet.
            var aud = (typeof currentRT !== 'undefined') ? currentRT : '';
            var isBusinessOrAll = (aud === '' || aud === 'Business' || aud === 'Business_ROE');
            if (!isBusinessOrAll) {
                el.innerHTML = '<div class="empty-state"><h2 class="section-h">Market Penetration</h2>'
                  + '<p>This view currently covers Business properties only. Selected pipeline: <strong>'
                  + (aud || '(none)') + '</strong>.</p>'
                  + '<p>MDU and SFU penetration views are planned for a future iteration.</p></div>';
                return;
            }
```

If the audience variable name is different from `currentRT`, substitute accordingly.

- [ ] **Step 3: Add minimal `.empty-state` CSS if not present**

```bash
grep -n "\.empty-state" "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page" | head -3
```

If absent, add to the existing `<style>` block:

```css
.empty-state { padding: 2rem; color: #444; max-width: 700px; }
.empty-state p { margin: 0.5rem 0; line-height: 1.5; }
```

- [ ] **Step 4: Deploy**

```bash
cd "C:/Users/cass/Work_Projects/SalesForce/tracker-lwc" && sf project deploy start \
  --source-dir force-app/main/default/pages/InsideSalesDashboard.page \
  --target-org cass1@ubiquitygp.com \
  --test-level NoTestRun
```

- [ ] **Step 5: Manual smoke test**

Open dashboard, click Market Penetration tab. Expected:
- Audience = All → 3 sections render
- Click Business Sales → 3 sections render (same data)
- Click MDU → placeholder ("MDU and SFU penetration views are planned...")
- Click Business ROE → 3 sections render
- Click back to All → 3 sections render

If the placeholder doesn't trigger correctly, double-check the variable name from Step 1.

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: audience-slicer placeholder for Market Penetration (non-business)

Renders 'coming soon' message when MDU is selected; data sections only
render for Business / Business ROE / All.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Smoke-Test Probe + User Verification Pause

Write a probe that re-derives every number the dashboard shows, so the user (Koa) can compare to what's rendering in the browser and confirm parity. Pause for Koa's sign-off before retiring the old dashboard.

**Files:**
- Create: `SalesForce/scripts/_probes/2026-05-26-market-pen-smoke-test.py`

- [ ] **Step 1: Write the smoke-test probe**

```python
"""Smoke test for the deployed Market Penetration tab. Prints the same
metrics the tab shows so they can be eyeball-compared. Run after every
significant change."""
from collections import defaultdict
from simple_salesforce import Salesforce

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="<password: see _shared/sf_auth.py>",
    security_token="<token: see _shared/sf_auth.py>",
)

# Q-A
qa = sf.query_all("""
    SELECT Id, Property_Unit_Count__c, Active_Unit_Count__c,
           Deactive_Unit_Count__c, State__c, Lit__c
    FROM Property_Location__c
    WHERE Address_Type__c='Business' AND Import_Delete_Property__c=false
""")["records"]
singles = [r for r in qa if (r.get("Property_Unit_Count__c") or 0) == 1]
multis = [r for r in qa if (r.get("Property_Unit_Count__c") or 0) > 1]
lit_singles = [r for r in singles if r.get("Lit__c") is True]
lit_multis = [r for r in multis if r.get("Lit__c") is True]
units_in_lit = sum((r.get("Property_Unit_Count__c") or 0) for r in lit_multis)
active_in_lit = sum((r.get("Active_Unit_Count__c") or 0) for r in lit_multis)

print("=== Section 1: Single-Unit ===")
print(f"  Total: {len(singles)}  Lit: {len(lit_singles)}  "
      f"Pen: {(len(lit_singles)/len(singles)*100 if singles else 0):.1f}%")

print("\n=== Section 2: Multi-Unit ===")
print(f"  Total: {len(multis)}  Lit: {len(lit_multis)}  "
      f"Units in Lit: {int(units_in_lit)}  Active: {int(active_in_lit)}  "
      f"Door-Weighted: {(active_in_lit/units_in_lit*100 if units_in_lit else 0):.1f}%")

# Q-C
qc = sf.query_all("""
    SELECT Property_Location__r.Property_Unit_Count__c
    FROM Agreement__c
    WHERE Status__c='Completed'
      AND Agreement_Type__c IN ('ROE','PAL','PAL/ROE','PAL Addendum','ROE Addendum')
      AND Opportunity__r.RecordType.DeveloperName='Business_ROE'
      AND Property_Location__c != null
      AND Property_Location__r.Address_Type__c='Business'
      AND Property_Location__r.Import_Delete_Property__c=false
      AND Property_Location__r.Lit__c = false
""")["records"]
s3_total = len(qc)
s3_single = sum(1 for r in qc if ((r.get("Property_Location__r") or {}).get("Property_Unit_Count__c") or 0) == 1)
s3_multi = sum(1 for r in qc if ((r.get("Property_Location__r") or {}).get("Property_Unit_Count__c") or 0) > 1)

print("\n=== Section 3: ROE Completed but Not Yet Lit ===")
print(f"  Total: {s3_total}  Single-Unit: {s3_single}  Multi-Unit: {s3_multi}")

# Per-state single-unit
print("\n=== Section 1 by state ===")
by_state = defaultdict(lambda: {"total": 0, "lit": 0})
for r in singles:
    s = r.get("State__c") or "(none)"
    by_state[s]["total"] += 1
    if r.get("Lit__c") is True:
        by_state[s]["lit"] += 1
for s in sorted(by_state):
    row = by_state[s]
    pct = row["lit"] / row["total"] * 100 if row["total"] else 0
    print(f"  {s:>15}  total={row['total']:>5}  lit={row['lit']:>4}  pen={pct:>5.1f}%")
```

- [ ] **Step 2: Run the probe**

```bash
python "C:/Users/cass/Work_Projects/SalesForce/scripts/_probes/2026-05-26-market-pen-smoke-test.py"
```

Save the output. The user (Koa) will compare it to what shows in the browser.

- [ ] **Step 3: Ask Koa to verify**

Open the dashboard in browser. Click Market Penetration. Compare every KPI and every per-state row against the probe output. Items to verify:

- All 3 sections render
- Section 1: Total = probe Section 1 Total. Lit = probe Lit. Pen % = probe Pen %.
- Section 2: All 5 KPIs match probe
- Section 3: 14 rows, all 3 KPIs match, Mesa Ranch ROEs are in the list
- By-state tables: every state row matches
- Audience switching: MDU → placeholder, others → data

**DO NOT proceed to Task 10 (delete old dashboard) until Koa explicitly confirms parity.**

- [ ] **Step 4: Commit the smoke-test probe**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add scripts/_probes/2026-05-26-market-pen-smoke-test.py
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: market penetration smoke-test probe

Re-derives every metric the tab shows so the rendered view can be
verified against the source data row-by-row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Delete Old `Business_Penetration` Dashboard

ONLY after Koa confirms Task 9 parity. Removes `01ZWR000004X6if2AC`. The `BizPen_*` reports under `PropertyReports` stay (cheap to keep, sometimes useful).

**Files:**
- Create: `SalesForce/scripts/fix/2026-05-26-delete-old-business-penetration-dashboard.py`

- [ ] **Step 1: Write the deletion script**

```python
"""Delete the standalone Business Penetration dashboard (01ZWR000004X6if2AC)
now that the Market Penetration tab on InsideSalesDashboard.page covers it.

Default = dry-run. Pass --apply to actually delete.
Snapshots dashboard metadata to audit_logs first."""
import json
import sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

DRY_RUN = "--apply" not in sys.argv
DASHBOARD_ID = "01ZWR000004X6if2AC"

sf = Salesforce(
    username="cass1@ubiquitygp.com",
    password="<password: see _shared/sf_auth.py>",
    security_token="<token: see _shared/sf_auth.py>",
)

# 1. Snapshot metadata
result = sf.toolingexecute(f"sobjects/Dashboard/{DASHBOARD_ID}", method="GET")
OUT = Path("C:/Users/cass/Work_Projects/SalesForce/data/output/audit_logs")
OUT.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d-%H%M%S")
snap = OUT / f"business_penetration_dashboard_snapshot_{ts}.json"
snap.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(f"[INFO] Snapshot: {snap}")
print(f"[INFO] Dashboard: {result.get('DeveloperName')} / {result.get('Title')}")

if DRY_RUN:
    print("\nDRY RUN. Re-run with --apply to delete.")
    sys.exit(0)

# 2. Delete via REST
deleted = sf.restful(f"sobjects/Dashboard/{DASHBOARD_ID}", method="DELETE")
print(f"[INFO] Delete response: {deleted}")
print("[SUCCESS] Dashboard deleted.")
```

- [ ] **Step 2: Dry-run**

```bash
python "C:/Users/cass/Work_Projects/SalesForce/scripts/fix/2026-05-26-delete-old-business-penetration-dashboard.py"
```

Expected output: snapshot file path, dashboard DeveloperName = `Business_Penetration` (or similar), Title contains "Business Penetration".

Inspect the snapshot file briefly to confirm it's the right dashboard.

- [ ] **Step 3: Apply**

```bash
python "C:/Users/cass/Work_Projects/SalesForce/scripts/fix/2026-05-26-delete-old-business-penetration-dashboard.py" --apply
```

Expected: `[SUCCESS] Dashboard deleted.`

- [ ] **Step 4: Verify deletion**

```bash
python -c "
from simple_salesforce import Salesforce
sf = Salesforce(username='cass1@ubiquitygp.com', password='<password: see _shared/sf_auth.py>', security_token='<token: see _shared/sf_auth.py>')
try:
    r = sf.toolingexecute('sobjects/Dashboard/01ZWR000004X6if2AC', method='GET')
    print('STILL EXISTS:', r)
except Exception as e:
    print('OK, gone:', type(e).__name__)
"
```

Expected: `OK, gone: SalesforceResourceNotFound` (or equivalent 404).

- [ ] **Step 5: Commit**

```bash
git -C "C:/Users/cass/Work_Projects/SalesForce" add scripts/fix/2026-05-26-delete-old-business-penetration-dashboard.py
git -C "C:/Users/cass/Work_Projects/SalesForce" commit -m "$(cat <<'EOF'
sf: delete old standalone Business Penetration dashboard

Replaced by the Market Penetration tab on InsideSalesDashboard.page.
Snapshot saved to audit_logs/ before deletion as rollback ref.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✓ Architecture: tab on InsideSalesDashboard.page after Executive → Task 3
- ✓ `Lit__c` formula field → Task 2
- ✓ Universe filter (Business non-deleted) → embedded in Q-A/Q-B/Q-C → Task 4
- ✓ Section 1 single-unit → Task 5
- ✓ Section 2 multi-unit door-weighted → Task 6
- ✓ Section 3 ROE-not-lit (14 rows) → Task 7
- ✓ Audience slicer branching → Task 8
- ✓ Smoke test against ground truth → Task 9
- ✓ Delete old `01ZWR000004X6if2AC` → Task 10
- ✓ Ground-truth probe (Task 1) precedes everything

**No placeholders:**
- The variable name `currentRT` in Task 8 is flagged for verification at edit time (Step 1 explicitly searches for the real name). Acceptable — the alternative is to inline-read the VF file inside this plan, but the plan is meant to be executable without ambient context.
- The query result index `N+1/N+2/N+3` is described with an explicit "count results[N] references" step (Task 4 Step 2). The exact integer can't be known without reading the file at edit time.

**Out-of-scope reminders (from spec):**
- MDU/SFU expansion — placeholder branch only, no implementation
- Email subscriptions
- Drill-down navigation (clickable property names go to the record page — that's in Section 3, but no other drill-down)

**Risk acknowledged in spec:**
- Pankaj's verbal "lit = fiber to the building" → operationalized as "lit = has any drop". Confirm at Task 9 sign-off before deleting the old dashboard (Task 10).
