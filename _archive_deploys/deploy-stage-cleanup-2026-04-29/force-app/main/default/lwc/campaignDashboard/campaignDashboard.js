import { LightningElement, api, wire, track } from 'lwc';
import getCampaignSummary from '@salesforce/apex/CampaignDashboardController.getCampaignSummary';

// SF Opportunity stages in pipeline order. Legacy stages (Qualification, Needs Analysis, etc.)
// are intentionally excluded — not used for MDU/Business pipelines.
const PIPELINE_STAGES = [
    'Prospecting',
    'Engaged',
    'PAL/ROE Complete',
    'Contract Negotiations',
        'Ready for Engineering',
    'Under Construction',
    'Activation',
    'Closed Won'
];
// On Hold and Closed Lost don't sit on the linear pipeline. On Hold is always Active,
// Closed Lost is always Resolved.
const OFF_PIPELINE = ['On Hold', 'Closed Lost'];
const STAGE_ORDER = [...PIPELINE_STAGES, 'On Hold', 'Closed Lost'];

const STAGE_COLORS = {
    'Prospecting': '#60a5fa',
    'Engaged': '#818cf8',
    'PAL/ROE Complete': '#4ade80',
    'Contract Negotiations': '#a78bfa',
        'Ready for Engineering': '#22d3ee',
    'Under Construction': '#fbbf24',
    'Activation': '#14b8a6',
    'On Hold': '#94a3b8',
    'Closed Won': '#10b981',
    'Closed Lost': '#f87171'
};

export default class CampaignDashboard extends LightningElement {
    @api recordId;
    @track summary;
    @track error;
    @track activeTab = 'pipeline';
    @track searchTerm = '';
    @track stateFilter = '';
    @track roleView = 'all';  // 'all' | 're' | 'sales'

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

    // Resolution threshold: stage at which an Opp is considered resolved for this project.
    // Falls back to 'Closed Won' if not set on the Campaign.
    get resolutionStage() {
        return this.summary?.campaign?.Resolution_Stage__c || 'Closed Won';
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
            return stage === 'Closed Won';
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
        for (const stage of STAGE_ORDER) stages[stage] = { count: 0, units: 0, subStatus: {} };

        for (const o of opps) {
            const stage = o.StageName;
            if (!stages[stage]) continue;
            stages[stage].count += 1;
            stages[stage].units += Number(o.Units__c || 0);
            if (o.Sales_Status__c) {
                const ss = o.Sales_Status__c;
                if (!stages[stage].subStatus[ss]) stages[stage].subStatus[ss] = { count: 0, units: 0 };
                stages[stage].subStatus[ss].count += 1;
                stages[stage].subStatus[ss].units += Number(o.Units__c || 0);
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
            const subs = Object.entries(d.subStatus)
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

    // ---- Tab: 2026 PAL/ROE Complete ----
    get roe2026() {
        return this.filteredOpps
            .filter(o => o.StageName === 'PAL/ROE Complete')
            .filter(o => {
                const d = o.LastStageChangeDate || o.CloseDate;
                if (!d) return false;
                return String(d).startsWith('2026');
            })
            .sort((a, b) => String(b.LastStageChangeDate || '').localeCompare(String(a.LastStageChangeDate || '')))
            .map(o => ({
                id: o.Id,
                name: o.Name,
                state: o.Property_State__c,
                units: o.Units__c,
                date: (o.LastStageChangeDate || o.CloseDate || '').slice(0, 10),
                owner: o.Owner?.Name,
                url: `/lightning/r/Opportunity/${o.Id}/view`
            }));
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
    handleClear() { this.searchTerm = ''; this.stateFilter = ''; this.roleView = 'all'; }
    handleRoleView(e) { this.roleView = e.currentTarget.dataset.role; }

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