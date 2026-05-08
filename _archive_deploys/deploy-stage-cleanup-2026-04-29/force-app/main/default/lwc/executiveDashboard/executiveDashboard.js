import { LightningElement, track } from 'lwc';
import getExecutiveDashboardData from '@salesforce/apex/TrackerController.getExecutiveDashboardData';

const STAGE_COLORS = [
    '#1F3A68', // Prospecting (deepest navy)
    '#2C5BA0', // Engaged
    '#3a7bd5', // PAL/ROE Complete
    '#4D9DE0', // Contract Negotiations
    '#2E7D32', // (was Under Contract; now PAL/ROE Complete)
    '#43A047', // EMA/Bulk In Progress
    '#66BB6A'  // EMA/Bulk Complete
];

const FUNNEL_VIEWBOX_W = 600;
const FUNNEL_VIEWBOX_H = 350;
const FUNNEL_TOP_PCT    = 1.0;   // segment 0 width = 100% of viewbox
const FUNNEL_BOTTOM_PCT = 0.3;   // segment N width = 30% of viewbox

export default class ExecutiveDashboard extends LightningElement {
    @track data;
    @track error;
    isLoading = true;

    connectedCallback() {
        this.loadData();
    }

    async loadData() {
        this.isLoading = true;
        try {
            this.data = await getExecutiveDashboardData();
            this.error = undefined;
        } catch (e) {
            this.error = e.body ? e.body.message : e.message;
            this.data = undefined;
        }
        this.isLoading = false;
    }

    handleRefresh() {
        this.loadData();
    }

    // ── Computed ──

    get hasData() {
        return this.data != null;
    }

    get hasPastDue() {
        return this.data && this.data.pastDueCount > 0;
    }

    get hasNext90() {
        return this.data && this.data.next90DaysDetails && this.data.next90DaysDetails.length > 0;
    }

    get hasOver90() {
        return this.data && this.data.over90DaysDetails && this.data.over90DaysDetails.length > 0;
    }

    get currentYear() {
        return new Date().getFullYear();
    }

    // ── Funnel (real SVG trapezoid) ──

    get funnelSegments() {
        if (!this.data || !this.data.funnelStages) return [];
        const stages = this.data.funnelStages;
        const n = stages.length;
        const segH = FUNNEL_VIEWBOX_H / n;

        return stages.map((s, i) => {
            const topPct = FUNNEL_TOP_PCT - ((FUNNEL_TOP_PCT - FUNNEL_BOTTOM_PCT) * (i / n));
            const botPct = FUNNEL_TOP_PCT - ((FUNNEL_TOP_PCT - FUNNEL_BOTTOM_PCT) * ((i + 1) / n));
            const topW = FUNNEL_VIEWBOX_W * topPct;
            const botW = FUNNEL_VIEWBOX_W * botPct;
            const topX1 = (FUNNEL_VIEWBOX_W - topW) / 2;
            const topX2 = topX1 + topW;
            const botX1 = (FUNNEL_VIEWBOX_W - botW) / 2;
            const botX2 = botX1 + botW;
            const yTop = i * segH;
            const yBot = (i + 1) * segH;
            const points = `${topX1},${yTop} ${topX2},${yTop} ${botX2},${yBot} ${botX1},${yBot}`;
            const labelX = FUNNEL_VIEWBOX_W / 2;
            const labelY = yTop + segH / 2;
            return {
                key: s.stage,
                stage: s.stage,
                count: s.count,
                units: s.units,
                points,
                fill: STAGE_COLORS[i % STAGE_COLORS.length],
                labelX,
                labelY,
                stageLabelY: labelY - 8,
                countLabelY: labelY + 10,
                hasUnits: s.units > 0,
                unitText: s.units > 0 ? `${s.count} sites · ${this._fmt(s.units)} units` : `${s.count} sites`
            };
        });
    }

    _fmt(n) {
        if (n == null) return '';
        return n.toLocaleString();
    }

    get funnelViewBox() {
        return `0 0 ${FUNNEL_VIEWBOX_W} ${FUNNEL_VIEWBOX_H}`;
    }

    // ── Monthly bars ──

    get monthlyBars() {
        if (!this.data || !this.data.completedByMonth) return [];
        const max = Math.max(...this.data.completedByMonth.map(m => m.count), 1);
        const currentMonth = new Date().getMonth() + 1;
        return this.data.completedByMonth
            .filter(m => m.month <= currentMonth)
            .map(m => ({
                key: m.monthName,
                monthName: m.monthName,
                count: m.count,
                barStyle: `width:${max > 0 ? Math.max((m.count / max) * 100, 4) : 4}%; background:#1b96ff;`,
                hasCount: m.count > 0
            }));
    }

    // ── Lane forecasts ──

    get palLane() {
        return this._buildLane(this.data?.palForecast, 'PAL Forecast', 'Brett Spivey (Inside Sales)');
    }

    get emaBulkLane() {
        return this._buildLane(this.data?.emaBulkForecast, 'EMA/Bulk Forecast', 'Melissa Baker');
    }

    get saqLane() {
        return this._buildLane(this.data?.saqForecast, 'SAQ Forecast', 'Bill Holick (Site Acquisition)');
    }

    _buildLane(lane, title, subtitle) {
        if (!lane) return null;
        return {
            title,
            subtitle,
            pastDueCount: lane.pastDueCount || 0,
            pastDueUnits: lane.pastDueUnits || 0,
            next90Count:  lane.next90Count  || 0,
            next90Units:  lane.next90Units  || 0,
            over90Count:  lane.over90Count  || 0,
            over90Units:  lane.over90Units  || 0,
            pastDueRows: this._formatDetails(lane.pastDueDetails),
            next90Rows:  this._formatDetails(lane.next90Details),
            over90Rows:  this._formatDetails(lane.over90Details),
            hasPastDue: (lane.pastDueCount || 0) > 0,
            hasNext90:  (lane.next90Count  || 0) > 0,
            hasOver90:  (lane.over90Count  || 0) > 0,
            isEmpty:    !((lane.pastDueCount || 0) || (lane.next90Count || 0) || (lane.over90Count || 0))
        };
    }

    // ── Aggregate detail rows (kept for backward-compat sections) ──

    get pastDueRows() {
        return this._formatDetails(this.data?.pastDueDetails);
    }

    get next90Rows() {
        return this._formatDetails(this.data?.next90DaysDetails);
    }

    get over90Rows() {
        return this._formatDetails(this.data?.over90DaysDetails);
    }

    get hasInProgressSiteTrackers() {
        return this.data && this.data.inProgressSiteTrackers && this.data.inProgressSiteTrackers.length > 0;
    }

    get inProgressSiteTrackerRows() {
        const rows = this.data?.inProgressSiteTrackers || [];
        return rows.map(r => ({
            id: r.id,
            name: r.name,
            buildStatus: r.buildStatus,
            siteStatus: r.siteStatus,
            formattedActivation: this._formatDate(r.activationForecast),
            oppName: r.oppName,
            oppUrl: r.oppId ? '/' + r.oppId : null,
            stUrl: '/' + r.id,
            state: r.state,
            units: r.units,
            ownerName: r.ownerName
        }));
    }

    _formatDetails(details) {
        if (!details) return [];
        return details.map(d => ({
            ...d,
            formattedDate: this._formatDate(d.closeDate),
            url: '/' + d.id
        }));
    }

    _formatDate(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr + 'T00:00:00');
        return (d.getMonth() + 1) + '/' + d.getDate() + '/' + d.getFullYear();
    }
}