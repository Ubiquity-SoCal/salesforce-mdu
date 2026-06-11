# "By Owner" Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "By Owner" tab to `InsideSalesDashboard.page` showing every active RE owner's pipeline split into three lifecycle tables (Active/In-Progress, Closed-Lost/On-Hold, Activated/Completed).

**Architecture:** One aggregate SOQL (`Owner × StageName`, active owners, same `rtFilter+catFilter+yrFilter` as all panels) appended to the existing `Promise.all`; a client-side `renderByOwner()` pivots the flat rows into three `data-table` tables. No Apex, no schema change. Mirrors the Market Penetration tab pattern.

**Tech Stack:** Visualforce page (client-side JS, `fetch()` to REST `/query`), `sf` CLI metadata deploy, Python `simple_salesforce` probe for ground-truth.

**Spec:** `docs/superpowers/specs/2026-06-11-by-owner-tab-design.md`

**Target file (single):** `tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page`

---

### Task 0: Branch + ground-truth probe

**Files:**
- Create: `SalesForce/scripts/_probes/2026-06-11-byowner-expected.py`

- [ ] **Step 1: Create a feature branch** (don't pollute `ledger-encinitas`)

```bash
cd C:/Users/cass/Work_Projects
git checkout -b dashboard-by-owner-tab
```

- [ ] **Step 2: Write the ground-truth probe** — computes exactly what the MDU view of the tab should show (active owners, Cat 1, MDU RT, bucketed)

```python
# SalesForce/scripts/_probes/2026-06-11-byowner-expected.py
from collections import defaultdict
from simple_salesforce import Salesforce
sf = Salesforce(username="cass1@ubiquitygp.com", password="Hawaiian1984",
                security_token="IBSKT6CFUpSUJWxq1CMm0HkFC")
IN_PROG = {'Prospects','Prospecting','Engaged','Proposal Sent','Contract Negotiations'}
DEAD = {'Closed Lost','On Hold'}
DONE = {'PAL/ROE Complete','Marketing/Bulk In Progress','Marketing/Bulk Complete'}
rows = sf.query_all(
    "SELECT Owner.Name o, StageName s, COUNT(Id) c, SUM(Units__c) u "
    "FROM Opportunity WHERE Owner.IsActive = true AND CreatedDate >= 2026-01-01T00:00:00Z "
    "AND (RecordType.DeveloperName='MDU' OR RecordType.DeveloperName='SFU') "
    "AND Property_Category__c='Cat 1' GROUP BY Owner.Name, StageName")["records"]
buckets = {'IN_PROG': defaultdict(int), 'DEAD': defaultdict(int), 'DONE': defaultdict(int)}
for r in rows:
    b = 'IN_PROG' if r['s'] in IN_PROG else 'DEAD' if r['s'] in DEAD else 'DONE' if r['s'] in DONE else 'IN_PROG'
    buckets[b][r['o']] += r['c']
for b in ['IN_PROG','DEAD','DONE']:
    print(f"\n=== {b} (MDU Cat1, active owners) ===")
    for o, c in sorted(buckets[b].items(), key=lambda kv: -kv[1]):
        print(f"  {o:24} {c}")
    print("  TOTAL:", sum(buckets[b].values()))
```

- [ ] **Step 3: Run it and record the expected numbers**

```bash
cd C:/Users/cass/Work_Projects/SalesForce && python scripts/_probes/2026-06-11-byowner-expected.py
```
Expected: three buckets print with per-owner counts; ONLY active owners appear (no Chuck/Marty/Jeff/inactive-Brett). Save this output — it's the smoke-test oracle.

- [ ] **Step 4: Commit**

```bash
git add SalesForce/scripts/_probes/2026-06-11-byowner-expected.py
git commit -m "probe: ground-truth for By Owner dashboard tab"
```

---

### Task 1: Add the aggregate SOQL query to `Promise.all`

**Files:**
- Modify: `tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page` (insert before line 775, the `]).then(function(results) {` that closes the query array — currently the last entry is the Market-Pen Property_Location query at line 768 + its two Agreement queries; the new query becomes `results[39]`)

- [ ] **Step 1: Insert the query as the last element of the array.** Find the final query line before `        ]).then(function(results) {` and append a comma + this query so it is the last array element:

```javascript
            // ─── BY OWNER TAB (39): active owners × stage, count + units ───
            query("SELECT Owner.Name ownerName, StageName, COUNT(Id) cnt, SUM(Units__c) units FROM Opportunity WHERE Owner.IsActive = true AND " + yrFilter + rtFilter + catFilter + " GROUP BY Owner.Name, StageName ORDER BY Owner.Name")
```

Note: `yrFilter` has no leading "AND"; `rtFilter` and `catFilter` already begin with " AND " (empty string for the All slicer). Result destructures to `results[39]`.

- [ ] **Step 2: Verify the array is still valid** — the element BEFORE this one must end with a comma, and this new line must NOT have a trailing comma (it is last). Re-read lines 769-777 to confirm.

- [ ] **Step 3: Commit**

```bash
git add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git commit -m "feat(dashboard): add By Owner aggregate query"
```

---

### Task 2: Add the `renderByOwner()` function

**Files:**
- Modify: `tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page` (insert between the `switchTab` function close at line 384 `}` and the `/* ─── 3b. renderMarketPen() ... */` comment at line 386)

- [ ] **Step 1: Insert the function**

```javascript
    /* ─── 3a2. renderByOwner() — three lifecycle tables, active owners ── */
    function renderByOwner(rows) {
        var el = document.getElementById('byowner-content');
        if (!el) return;

        var biz = (currentPipeline === 'Business');
        var inProgress = biz
            ? ['Prospects','Prospecting','Engaged','Contract Negotiations']
            : ['Prospects','Prospecting','Engaged','Proposal Sent','Contract Negotiations'];
        var dead = ['Closed Lost','On Hold'];
        var done = biz
            ? ['Under Contract','Closed Won']
            : ['PAL/ROE Complete','Marketing/Bulk In Progress','Marketing/Bulk Complete'];

        // Pivot flat rows -> byOwner[owner][stage] = {cnt, units}
        var byOwner = {};
        rows.forEach(function(r) {
            var o = r.ownerName || '(unknown)';
            var s = r.StageName || '(none)';
            if (!byOwner[o]) byOwner[o] = {};
            byOwner[o][s] = { cnt: (r.cnt || 0), units: (r.units || 0) };
        });

        function cell(o, s) { return (byOwner[o] && byOwner[o][s]) || { cnt: 0, units: 0 }; }

        function bucketTable(title, stages) {
            var owners = Object.keys(byOwner).filter(function(o) {
                return stages.some(function(s) { return cell(o, s).cnt > 0; });
            });
            if (owners.length === 0) {
                return '<h2 class="section-h">' + escHtml(title) + '</h2>'
                     + '<div class="empty-state">No active-owner deals in this bucket.</div>';
            }
            function tot(o) { return stages.reduce(function(a, s) { return a + cell(o, s).cnt; }, 0); }
            owners.sort(function(a, b) { return tot(b) - tot(a); });

            var grand = {}; stages.forEach(function(s) { grand[s] = { cnt: 0, units: 0 }; });
            var gTot = 0, gUnits = 0;

            var h = '<h2 class="section-h">' + escHtml(title) + '</h2>';
            h += '<table class="data-table"><thead><tr><th>Owner</th>';
            stages.forEach(function(s) { h += '<th class="num">' + escHtml(s) + '</th>'; });
            h += '<th class="num">Total</th><th class="num">Units</th></tr></thead><tbody>';
            owners.forEach(function(o) {
                var rt = 0, ru = 0;
                h += '<tr><td>' + escHtml(o) + '</td>';
                stages.forEach(function(s) {
                    var c = cell(o, s);
                    rt += c.cnt; ru += c.units; grand[s].cnt += c.cnt; grand[s].units += c.units;
                    h += '<td class="num">' + (c.cnt || '') + '</td>';
                });
                gTot += rt; gUnits += ru;
                h += '<td class="num">' + rt + '</td><td class="num">' + ru.toLocaleString() + '</td></tr>';
            });
            h += '<tr style="font-weight:700;background:#f3f3f3;"><td>GRAND TOTAL</td>';
            stages.forEach(function(s) { h += '<td class="num">' + (grand[s].cnt || '') + '</td>'; });
            h += '<td class="num">' + gTot + '</td><td class="num">' + gUnits.toLocaleString() + '</td></tr>';
            h += '</tbody></table>';
            return h;
        }

        var scope = (currentPipeline === 'MDU') ? 'Cat 1 in-network MDU/SFU'
                  : (currentPipeline === 'all' || !currentPipeline) ? 'all record types'
                  : currentPipeline;
        var html = '<div class="mp-header"><h3>Pipeline Progress by RE Owner</h3>'
                 + '<div class="mp-source">Active owners only · ' + escHtml(scope)
                 + ' view · live from Salesforce.</div></div>';
        html += bucketTable('① Active / In Progress', inProgress);
        html += bucketTable('② Closed Lost / On Hold', dead);
        html += bucketTable('③ Activated / Completed', done);
        el.innerHTML = html;
    }
```

- [ ] **Step 2: Commit**

```bash
git add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git commit -m "feat(dashboard): add renderByOwner three-table renderer"
```

---

### Task 3: Wire up the tab (button + container + dispatch)

**Files:**
- Modify: `tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page` at three spots (line ~347, ~1765, ~1869)

- [ ] **Step 1: Add the tab button** — immediately AFTER line 347 (the `My Pipeline` tab button):

```javascript
        h += '<div class="tab" data-tab="byowner" onclick="switchTab(\'byowner\',this)">By Owner</div>';
```

- [ ] **Step 2: Add the tab-content container** — immediately BEFORE line 1765 (the `<div id="tab-marketpen"` block). Insert:

```javascript
            // ═══════════════════════════════════════════════════════════
            // 4i-BO. RENDER: BY OWNER TAB — container (filled by renderByOwner)
            // ═══════════════════════════════════════════════════════════
            html += '<div id="tab-byowner" class="tab-content' + (currentTab === 'byowner' ? ' active' : '') + '">';
            html += '  <div id="byowner-content">Loading...</div>';
            html += '</div>'; // end byowner tab
```

- [ ] **Step 3: Add the dispatch call** — immediately AFTER line 1869 (the `renderMarketPen(recs(results[36])...)` call), so the container exists in the DOM first:

```javascript
            renderByOwner(recs(results[39]));
```

- [ ] **Step 4: Commit**

```bash
git add tracker-lwc/force-app/main/default/pages/InsideSalesDashboard.page
git commit -m "feat(dashboard): wire up By Owner tab (button, container, dispatch)"
```

---

### Task 4: Deploy

**Files:** none (deploy only)

- [ ] **Step 1: Validate (dry-run) the page deploy**

```bash
cd C:/Users/cass/Work_Projects/SalesForce/tracker-lwc && sf project deploy start -m "ApexPage:InsideSalesDashboard" --dry-run --target-org cass1@ubiquitygp.com
```
Expected: `Status: Succeeded`. If it fails, the error names the line — fix and re-validate (most likely a JS-in-VF unescaped-char or a `Promise.all` comma).

- [ ] **Step 2: Deploy for real**

```bash
cd C:/Users/cass/Work_Projects/SalesForce/tracker-lwc && sf project deploy start -m "ApexPage:InsideSalesDashboard" --target-org cass1@ubiquitygp.com
```
Expected: `Deployed Source ... InsideSalesDashboard  ApexPage`.

---

### Task 5: Smoke test in the browser

**Files:** none

- [ ] **Step 1: Open the dashboard** (Koa, in his SF session): the Inside Sales Dashboard VF page → confirm a new **By Owner** tab appears after My Pipeline.

- [ ] **Step 2: MDU slicer check** — select **MDU**; on the By Owner tab confirm:
  - Three tables render (Active/In-Progress, Closed Lost/On Hold, Activated/Completed).
  - Per-owner counts MATCH the Task 0 probe output (e.g. Justin/Melissa/Rosemarie/Tanya/Bill present).
  - **No inactive owner appears** (Chuck, Marty, Jeff Chao, Jeff Wickersham, inactive Brett are absent).
  - Each owner's three-table totals sum to their full Cat 1 MDU opp count.

- [ ] **Step 3: Slicer adaptation check** — switch to **Business Sales**; confirm table ③ header columns change to `Under Contract / Closed Won`, and to **All**; confirm counts grow (all RTs, no Cat 1 filter).

- [ ] **Step 4: If all pass, merge**

```bash
cd C:/Users/cass/Work_Projects && git checkout main && git merge --no-ff dashboard-by-owner-tab
```
(Push only when Koa names the remote — backup origin = `Ubiquity-SoCal/work-projects-backup`.)

---

## Notes / Gotchas

- **Result index 39 is load-order-coupled.** It assumes the By Owner query is appended as the final `Promise.all` element after the three Market-Pen queries (`results[36..38]`). If the array changes, re-derive the index. Task 1 Step 2 verifies position.
- **`escHtml` on stage names** is harmless (no HTML) but keeps the column-header builder consistent with the rest of the page.
- **No `IsClosed` filter** — Closed Lost/On Hold/Closed Won are wanted (tables ② and ③), so the query deliberately omits it.
- **Aggregate aliases:** REST returns `ownerName`, `StageName`, `cnt`, `units`. `StageName` is unaliased (returns under its own name); the three others are aliased. Do not rename without updating `renderByOwner`.
- **Units may be null** — `SUM(Units__c)` returns `null` for owners with all-null units; `(r.units || 0)` guards it.
