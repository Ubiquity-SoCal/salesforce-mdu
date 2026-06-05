import { LightningElement, api, wire, track } from 'lwc';
import getCampaignSummary from '@salesforce/apex/CampaignDashboardController.getCampaignSummary';

// MDU pipeline stages in pipeline order, post 2026-04-29 stage restructure.
// Old stages (ROE Secured, Under Construction, Activation, Ready for Engineering, Closed Won)
// were retired for MDU and are intentionally excluded. Business RT keeps Under Contract — not
// represented here because this dashboard is MDU-focused.
const PIPELINE_STAGES = [
    'Prospects',
    'Prospecting',
    'Engaged',
    'Proposal Sent',
    'Contract Negotiations',
    'PAL/ROE Complete',
    'Marketing/Bulk In Progress',
    'Marketing/Bulk Complete'
];
// On Hold and Closed Lost don't sit on the linear pipeline. On Hold is always Active,
// Closed Lost is always Resolved.
const OFF_PIPELINE = ['On Hold', 'Closed Lost'];
const STAGE_ORDER = [...PIPELINE_STAGES, 'On Hold', 'Closed Lost'];

const STAGE_COLORS = {
    'Prospects': '#cbd5e1',
    'Prospecting': '#60a5fa',
    'Engaged': '#818cf8',
    'Proposal Sent': '#a78bfa',
    'Contract Negotiations': '#c084fc',
    'PAL/ROE Complete': '#4ade80',
    'Marketing/Bulk In Progress': '#fbbf24',
    'Marketing/Bulk Complete': '#10b981',
    'On Hold': '#94a3b8',
    'Closed Lost': '#f87171'
};

export default class CampaignDashboard extends LightningElement {
    @api recordId;
    @track summary;
    @track error;
    @track activeTab = 'pipeline';
    @track searchTerm = '';
    @track stateFilter = '';
    @track roleView = 'all';     // 'all' | 're' | 'sales'
    @track rtFilter = 'all';     // 'all' | 'Business_ROE' | 'Business' | <other>


    @wire(getCampaignSummary, { campaignId: '$recordId' })
    wired({ data, error }) {
        if (data) {
            this.summary = data;
            this.error = undefined;
        } else if (error) {
            this.error = (error.body && error.body.message) || JSON.stringify(error);
            this.summary = undefined;
        }
    }

    get isLoading() { return !this.summary && !this.error; }
    get isEmpty() { return this.summary && (!this.summary.opps || this.summary.opps.length === 0); }
    get campaignName() { return this.summary?.campaign?.Name; }

    get filteredOpps() {
        if (!this.summary?.opps) return [];
        let opps = this.summary.opps;
        if (this.rtFilter && this.rtFilter !== 'all') {
            opps = opps.filter(o => (o.RecordType?.DeveloperName) === this.rtFilter);
        }
        if (this.stateFilter) {
            opps = opps.filter(o => o.Property_State__c === this.stateFilter);
        }
        if (this.searchTerm) {
            const q = this.searchTerm.toLowerCase();
            opps = opps.filter(o =>
                (o.Name || '').toLowerCase().includes(q) ||
                (o.Property_City__c || '').toLowerCase().includes(q) ||
                (o.Agreement_Name__c || '').toLowerCase().includes(q)
            );
        }
        // Sales View: only Opps Sales would be working.
        //   - Any Opp with Submitted_to_FiberFirst__c = true (regardless of stage — includes
        //     Prospecting/Closed Lost that were FF-assigned)
        //   - OR open Opps at Resolution_Stage or beyond, excluding Closed Lost (Closed Lost
        //     only lands in Sales view via the FF route above)
        if (this.roleView === 'sales') {
            const thIdx = PIPELINE_STAGES.indexOf(this.resolutionStage);
            opps = opps.filter(o => {
                if (o.Submitted_to_FiberFirst__c) return true;
                if (o.StageName === 'Closed Lost') return false;
                const sIdx = PIPELINE_STAGES.indexOf(o.StageName);
                return sIdx >= 0 && thIdx >= 0 && sIdx >= thIdx;
            });
        }
        // RE View: show all Opps (RE still cares about their historical handoffs), no filter.
        return opps;
    }

    // ---- KPIs ----
    get kpis() {
        const opps = this.filteredOpps;
        const states = {};
        for (const o of opps) {
            const st = o.Property_State__c || '(none)';
            if (!states[st]) states[st] = { sites: 0, units: 0 };
            states[st].sites += 1;
            states[st].units += Number(o.Units__c || 0);
        }
        const total = {
            sites: opps.length,
            units: opps.reduce((a, o) => a + Number(o.Units__c || 0), 0)
        };
        const stateRows = Object.entries(states)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([name, d]) => ({
                name,
                sites: d.sites,
                units: d.units,
                avg: d.sites ? (d.units / d.sites).toFixed(1) : '0'
            }));
        return { total, stateRows };
    }

    get allStates() {
        if (!this.summary?.opps) return [];
        const set = new Set();
        this.summary.opps.forEach(o => o.Property_State__c && set.add(o.Property_State__c));
        return Array.from(set).sort();
    }

    // Record-Type slicer: lists every distinct RT in the campaign with its count.
    // Friendly label override for the two we know about; everything else falls back to RecordType.Name.
    get rtSlicerOptions() {
        if (!this.summary?.opps) return [];
        const counts = {};
        const labels = {};
        for (const o of this.summary.opps) {
            const dn = o.RecordType?.DeveloperName || '(none)';
            counts[dn] = (counts[dn] || 0) + 1;
            if (!labels[dn]) labels[dn] = o.RecordType?.Name || dn;
        }
        const friendly = { 'Business_ROE': 'Business ROE', 'Business': 'Business Sales' };
        return Object.entries(counts)
            .sort(([, a], [, b]) => b - a)
            .map(([dn, n]) => ({
                api: dn,
                label: `${friendly[dn] || labels[dn]} (${n})`,
                cls: 'slicer' + (this.rtFilter === dn ? ' slicer--active' : '')
            }));
    }

    get rtAllSlicerClass() {
        const total = this.summary?.opps?.length || 0;
        return 'slicer' + (this.rtFilter === 'all' ? ' slicer--active' : '');
    }
    get rtAllLabel() {
        const total = this.summary?.opps?.length || 0;
        return `All (${total})`;
    }
    get hasMultipleRts() {
        if (!this.summary?.opps) return false;
        const set = new Set(this.summary.opps.map(o => o.RecordType?.DeveloperName).filter(Boolean));
        return set.size > 1;
    }

    // Resolution threshold: stage at which an Opp is considered resolved for this project.
    // Falls back to 'PAL/ROE Complete' (post-restructure default for ROE-focused campaigns).
    get resolutionStage() {
        return this.summary?.campaign?.Resolution_Stage__c || 'PAL/ROE Complete';
    }

    // Is this stage "resolved" in the current view?
    // - Closed Lost: always resolved
    // - On Hold: always active (waiting to come off hold)
    // - Sales view: only Closed Won is resolved (Sales's finish line is sale closed)
    // - All/RE view: resolved if stage >= Campaign.Resolution_Stage__c threshold
    isResolvedStage(stage) {
        if (stage === 'Closed Lost') return true;
        if (stage === 'On Hold') return false;
        if (this.roleView === 'sales') {
            // Sales view: only Marketing/Bulk Complete (the post-PAL outcome) is resolved.
            return stage === 'Marketing/Bulk Complete';
        }
        const idx = PIPELINE_STAGES.indexOf(stage);
        const thIdx = PIPELINE_STAGES.indexOf(this.resolutionStage);
        if (idx < 0 || thIdx < 0) return false;
        return idx >= thIdx;
    }

    // ---- Tab: Pipeline by State ----
    get pipelineByState() {
        const opps = this.filteredOpps;
        const stages = {};
        for (const stage of STAGE_ORDER) stages[stage] = { count: 0, units: 0, subBucket: {} };

        for (const o of opps) {
            const stage = o.StageName;
            if (!stages[stage]) continue;
            stages[stage].count += 1;
            stages[stage].units += Number(o.Units__c || 0);
            // Sub_Bucket__c is a stage-aware formula: routes to Sales_Status / Substatus /
            // Hold_Reason / Loss_Reason per stage. Only Sales_Status leaks across stages by
            // design (it's not a dependent picklist); the other source fields are stage-scoped.
            const sb = o.Sub_Bucket__c;
            if (sb) {
                if (!stages[stage].subBucket[sb]) stages[stage].subBucket[sb] = { count: 0, units: 0 };
                stages[stage].subBucket[sb].count += 1;
                stages[stage].subBucket[sb].units += Number(o.Units__c || 0);
            }
        }

        const activeStages = STAGE_ORDER.filter(s => !this.isResolvedStage(s));
        const resolvedStages = STAGE_ORDER.filter(s => this.isResolvedStage(s));

        const total = opps.length;
        const totalUnits = opps.reduce((a, o) => a + Number(o.Units__c || 0), 0);
        const activeCount = activeStages.reduce((a, s) => a + stages[s].count, 0);
        const activeUnits = activeStages.reduce((a, s) => a + stages[s].units, 0);
        const resolvedCount = resolvedStages.reduce((a, s) => a + stages[s].count, 0);
        const resolvedUnits = resolvedStages.reduce((a, s) => a + stages[s].units, 0);

        const toRow = stage => {
            const d = stages[stage];
            const subs = Object.entries(d.subBucket)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([name, s]) => ({ name, count: s.count, units: s.units }));
            return {
                stage,
                count: d.count,
                units: d.units,
                pct: total ? ((d.count / total) * 100).toFixed(1) : '0.0',
                dotStyle: `background-color: ${STAGE_COLORS[stage] || '#94a3b8'}`,
                subs,
                hasSubs: subs.length > 0,
                hidden: d.count === 0
            };
        };

        return {
            active: activeStages.map(toRow),
            resolved: resolvedStages.map(toRow),
            total,
            totalUnits,
            activeCount,
            activeUnits,
            activePct: total ? ((activeCount / total) * 100).toFixed(1) : '0',
            resolvedCount,
            resolvedUnits,
            resolvedPct: total ? ((resolvedCount / total) * 100).toFixed(1) : '0',
            resolutionStageLabel: this.resolutionStage
        };
    }

    // ---- Tab: Closed Buckets ----
    get closedBuckets() {
        const closed = this.filteredOpps.filter(o => o.StageName === 'Closed Lost');
        const byReason = {};
        for (const o of closed) {
            const r = o.Loss_Reason__c || '(unspecified)';
            if (!byReason[r]) byReason[r] = { count: 0, units: 0, states: {} };
            byReason[r].count += 1;
            byReason[r].units += Number(o.Units__c || 0);
            const st = o.Property_State__c || '(none)';
            byReason[r].states[st] = (byReason[r].states[st] || 0) + 1;
        }
        const total = closed.length;
        return Object.entries(byReason)
            .sort(([, a], [, b]) => b.count - a.count)
            .map(([reason, d]) => ({
                reason,
                count: d.count,
                units: d.units,
                pct: total ? ((d.count / total) * 100).toFixed(1) : '0',
                states: Object.entries(d.states).sort(([a], [b]) => a.localeCompare(b))
                    .map(([s, c]) => `${s}: ${c}`).join(', ')
            }));
    }

    get closedTotalCount() {
        return this.filteredOpps.filter(o => o.StageName === 'Closed Lost').length;
    }

    // ---- Tab: PAL/ROE Complete ----
    // Show Opps with a Status=Completed ROE/PAL Agreement, grouped by Signed_Date period:
    // current year broken out by month, prior years aggregated, "No Signed Date" last.
    get roeComplete() {
        const agreements = this.summary?.agreements || [];
        const ROE_TYPES = new Set(['ROE', 'PAL', 'PAL Addendum', 'ROE Addendum', 'PAL/ROE']);
        const oppIds = new Set(this.filteredOpps.map(o => o.Id));
        const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const currentYear = new Date().getFullYear();

        // Latest completed ROE/PAL per Opp (controller already filters Status='Completed')
        const latestByOpp = {};
        for (const a of agreements) {
            const oid = a.Opportunity__c;
            if (!oid || !oppIds.has(oid)) continue;
            if (!ROE_TYPES.has(a.Agreement_Type__c)) continue;
            const sd = a.Signed_Date__c || '';
            const cur = latestByOpp[oid];
            if (!cur || sd > (cur.Signed_Date__c || '')) {
                latestByOpp[oid] = a;
            }
        }

        const oppById = new Map(this.filteredOpps.map(o => [o.Id, o]));
        const rows = [];
        for (const [oid, a] of Object.entries(latestByOpp)) {
            const o = oppById.get(oid);
            if (!o) continue;
            const sd = a.Signed_Date__c;
            let period, periodOrder;
            if (!sd) {
                period = 'No Signed Date';
                periodOrder = 999999;
            } else {
                const year = parseInt(sd.slice(0, 4), 10);
                const month = parseInt(sd.slice(5, 7), 10);
                if (year === currentYear) {
                    period = `${monthNames[month - 1]} ${year}`;
                    periodOrder = (9999 - year) * 100 + (12 - month);
                } else {
                    period = String(year);
                    periodOrder = (9999 - year) * 100 + 50;
                }
            }
            rows.push({
                id: o.Id,
                name: o.Name,
                state: o.Property_State__c,
                units: o.Units__c,
                date: (sd || '').slice(0, 10) || '—',
                workflowCompleted: (a.IronClad_Record__r?.Workflow_Completed_Date__c || '').slice(0, 10) || '—',
                owner: o.Owner?.Name,
                url: `/lightning/r/Opportunity/${o.Id}/view`,
                period,
                periodOrder,
                sortKey: sd || '0000'
            });
        }

        const groups = {};
        for (const r of rows) {
            if (!groups[r.period]) groups[r.period] = { period: r.period, periodOrder: r.periodOrder, items: [] };
            groups[r.period].items.push(r);
        }
        return Object.values(groups)
            .sort((a, b) => a.periodOrder - b.periodOrder)
            .map(g => ({
                period: g.period,
                count: g.items.length,
                items: g.items.sort((a, b) => b.sortKey.localeCompare(a.sortKey))
            }));
    }

    get roeCompleteTotal() {
        return this.roeComplete.reduce((sum, g) => sum + g.count, 0);
    }

    get roeCompleteHasData() {
        return this.roeCompleteTotal > 0;
    }

    // ---- Tab: Fiber First ----
    get fiberFirstList() {
        return this.filteredOpps
            .filter(o => o.Submitted_to_FiberFirst__c)
            .sort((a, b) => (a.Property_State__c || '').localeCompare(b.Property_State__c || ''))
            .map(o => ({
                id: o.Id,
                name: o.Name,
                stage: o.StageName,
                state: o.Property_State__c,
                units: o.Units__c,
                re: o.RE_Assigned__r?.Name,
                url: `/lightning/r/Opportunity/${o.Id}/view`
            }));
    }

    // ---- Tab: Submit to Market ----
    get submitMarketList() {
        return this.filteredOpps
            .filter(o => o.Submitted_to_Market__c)
            .sort((a, b) => (a.Property_State__c || '').localeCompare(b.Property_State__c || ''))
            .map(o => ({
                id: o.Id,
                name: o.Name,
                stage: o.StageName,
                state: o.Property_State__c,
                units: o.Units__c,
                re: o.RE_Assigned__r?.Name,
                url: `/lightning/r/Opportunity/${o.Id}/view`
            }));
    }

    // ---- Tab: Build Status (SiteTracker projects) ----
    // Opps at or past PAL/ROE Complete that have NO SiteTracker Project linked.
    // These are "ROE but no build" records — potential sync gaps or not-yet-kicked-off builds.
    get orphanRoes() {
        const opps = this.filteredOpps;
        const projects = this.summary?.siteTrackerProjects || [];
        const linkedOppIds = new Set(projects.map(p => p.Opportunity__c).filter(Boolean));
        const thIdx = PIPELINE_STAGES.indexOf(this.resolutionStage);
        if (thIdx < 0) return [];
        return opps
            .filter(o => {
                const sIdx = PIPELINE_STAGES.indexOf(o.StageName);
                return sIdx >= 0 && sIdx >= thIdx;  // at/past resolution stage
            })
            .filter(o => !linkedOppIds.has(o.Id))
            .sort((a, b) => (a.Property_State__c || '').localeCompare(b.Property_State__c || ''))
            .map(o => ({
                id: o.Id,
                name: o.Name,
                stage: o.StageName,
                state: o.Property_State__c,
                city: o.Property_City__c,
                units: o.Units__c,
                owner: o.Owner?.Name,
                re: o.RE_Assigned__r?.Name,
                url: `/lightning/r/Opportunity/${o.Id}/view`
            }));
    }

    get buildStatus() {
        const projects = this.summary?.siteTrackerProjects || [];
        // Respect state filter and search
        let filtered = projects;
        if (this.stateFilter) {
            filtered = filtered.filter(p => p.Opportunity__r?.Property_State__c === this.stateFilter);
        }
        if (this.searchTerm) {
            const q = this.searchTerm.toLowerCase();
            filtered = filtered.filter(p =>
                (p.Name || '').toLowerCase().includes(q) ||
                (p.Opportunity__r?.Name || '').toLowerCase().includes(q)
            );
        }

        const buckets = {};
        for (const p of filtered) {
            const k = p.Build_Status__c || '(no status)';
            if (!buckets[k]) buckets[k] = { count: 0, units: 0 };
            buckets[k].count += 1;
            buckets[k].units += Number(p.Opportunity__r?.Units__c || 0);
        }
        const total = filtered.length;
        const totalUnits = filtered.reduce((a, p) => a + Number(p.Opportunity__r?.Units__c || 0), 0);
        const rows = Object.entries(buckets)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([name, d]) => ({
                name,
                count: d.count,
                units: d.units,
                pct: total ? ((d.count / total) * 100).toFixed(1) : '0.0'
            }));

        const list = filtered.map(p => ({
            id: p.Id,
            name: p.Name,
            buildStatus: p.Build_Status__c,
            siteStatus: p.Site_Status__c,
            designComplete: (p.Design_Phase_Complete_A__c || '').slice(0, 10),
            oppName: p.Opportunity__r?.Name,
            state: p.Opportunity__r?.Property_State__c,
            units: p.Opportunity__r?.Units__c,
            stUrl: `/lightning/r/SiteTracker_Project__c/${p.Id}/view`,
            oppUrl: p.Opportunity__c ? `/lightning/r/Opportunity/${p.Opportunity__c}/view` : null
        }));

        return { rows, list, total, totalUnits };
    }

    // ---- Tab: Secured Agreements ----
    // Pivots Completed Agreements by Type x Signed Year. Years sorted desc, NoDate last.
    // Scoped to whatever Opps are visible (respects State + Search slicers).
    get securedByType() {
        const oppIds = new Set(this.filteredOpps.map(o => o.Id));
        const ags = (this.summary?.agreements || []).filter(a => oppIds.has(a.Opportunity__c));

        const bucket = {};
        const yearSet = new Set();
        for (const a of ags) {
            const t = a.Agreement_Type__c || '(none)';
            const sd = a.Signed_Date__c;
            const y = sd ? String(sd).slice(0, 4) : 'NoDate';
            if (!bucket[t]) bucket[t] = { total: 0, years: {} };
            bucket[t].total += 1;
            bucket[t].years[y] = (bucket[t].years[y] || 0) + 1;
            yearSet.add(y);
        }

        const dated = [...yearSet].filter(y => y !== 'NoDate').sort().reverse();
        const yearList = [...dated];
        if (yearSet.has('NoDate')) yearList.push('NoDate');

        const rows = Object.entries(bucket)
            .sort(([, a], [, b]) => b.total - a.total)
            .map(([type, d]) => ({
                type,
                total: d.total,
                cells: yearList.map(y => ({ year: y, count: d.years[y] || 0 }))
            }));

        const yearTotals = yearList.map(y => ({
            year: y,
            count: rows.reduce((acc, r) => acc + (r.cells.find(c => c.year === y)?.count || 0), 0)
        }));

        const grandTotal = rows.reduce((a, r) => a + r.total, 0);

        return {
            rows,
            yearHeaders: yearList.map(y => ({ year: y })),
            yearTotals,
            grandTotal,
            hasData: rows.length > 0
        };
    }

    // Detail list backing the Secured tab. Sorted newest signed first, NoDate last.
    get securedList() {
        const oppIds = new Set(this.filteredOpps.map(o => o.Id));
        const ags = (this.summary?.agreements || []).filter(a => oppIds.has(a.Opportunity__c));
        return ags
            .slice()
            .sort((a, b) => {
                const ad = a.Signed_Date__c || '';
                const bd = b.Signed_Date__c || '';
                if (!ad && bd) return 1;
                if (ad && !bd) return -1;
                return bd.localeCompare(ad);
            })
            .map(a => ({
                id: a.Id,
                type: a.Agreement_Type__c,
                signed: (a.Signed_Date__c || '').slice(0, 10) || '—',
                workflowCompleted: (a.IronClad_Record__r?.Workflow_Completed_Date__c || '').slice(0, 10) || '—',
                oppName: a.Opportunity__r?.Name,
                state: a.Opportunity__r?.Property_State__c,
                units: a.Opportunity__r?.Units__c,
                owner: a.Opportunity__r?.Owner?.Name,
                oppUrl: `/lightning/r/Opportunity/${a.Opportunity__c}/view`,
                agUrl: `/lightning/r/Agreement__c/${a.Id}/view`
            }));
    }

    // ---- Tab: All Data ----
    get allDataRows() {
        return this.filteredOpps.map(o => ({
            id: o.Id,
            name: o.Name,
            stage: o.StageName,
            salesStatus: o.Sales_Status__c,
            re: o.RE_Assigned__r?.Name,
            owner: o.Owner?.Name,
            units: o.Units__c,
            state: o.Property_State__c,
            city: o.Property_City__c,
            lossReason: o.Loss_Reason__c,
            closeDate: (o.CloseDate || '').slice(0, 10),
            url: `/lightning/r/Opportunity/${o.Id}/view`
        }));
    }

    // ---- UI handlers ----
    handleTabClick(e) { this.activeTab = e.currentTarget.dataset.tab; }
    handleStateFilter(e) {
        const val = e.currentTarget.dataset.state || '';
        this.stateFilter = this.stateFilter === val ? '' : val;
    }
    handleSearch(e) { this.searchTerm = e.target.value; }
    handleClear() { this.searchTerm = ''; this.stateFilter = ''; this.roleView = 'all'; this.rtFilter = 'all'; }
    handleRoleView(e) { this.roleView = e.currentTarget.dataset.role; }
    handleRtFilter(e) {
        const val = e.currentTarget.dataset.rt || 'all';
        this.rtFilter = this.rtFilter === val ? 'all' : val;
    }

    get roleAllClass() { return 'role-btn' + (this.roleView === 'all' ? ' role-btn--active' : ''); }
    get roleReClass() { return 'role-btn' + (this.roleView === 're' ? ' role-btn--active' : ''); }
    get roleSalesClass() { return 'role-btn' + (this.roleView === 'sales' ? ' role-btn--active' : ''); }

    get tabClass() { return (t) => 'tab' + (this.activeTab === t ? ' tab--active' : ''); }
    get pipelineTabClass() { return 'tab' + (this.activeTab === 'pipeline' ? ' tab--active' : ''); }
    get closedTabClass() { return 'tab' + (this.activeTab === 'closed' ? ' tab--active' : ''); }
    get roeTabClass() { return 'tab' + (this.activeTab === 'roe' ? ' tab--active' : ''); }
    get securedTabClass() { return 'tab' + (this.activeTab === 'secured' ? ' tab--active' : ''); }
    get ffTabClass() { return 'tab' + (this.activeTab === 'ff' ? ' tab--active' : ''); }
    get marketTabClass() { return 'tab' + (this.activeTab === 'market' ? ' tab--active' : ''); }
    get buildTabClass() { return 'tab' + (this.activeTab === 'build' ? ' tab--active' : ''); }
    get dataTabClass() { return 'tab' + (this.activeTab === 'data' ? ' tab--active' : ''); }

    get showPipeline() { return this.activeTab === 'pipeline'; }
    get showClosed() { return this.activeTab === 'closed'; }
    get showRoe() { return this.activeTab === 'roe'; }
    get showSecured() { return this.activeTab === 'secured'; }
    get showFF() { return this.activeTab === 'ff'; }
    get showMarket() { return this.activeTab === 'market'; }
    get showBuild() { return this.activeTab === 'build'; }
    get showData() { return this.activeTab === 'data'; }

    stateBtnClass(st) {
        return 'slicer' + (this.stateFilter === st ? ' slicer--active' : '');
    }
}