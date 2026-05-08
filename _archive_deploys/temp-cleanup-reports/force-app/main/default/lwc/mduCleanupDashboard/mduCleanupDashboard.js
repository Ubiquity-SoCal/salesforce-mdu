import { LightningElement, wire } from 'lwc';
import { NavigationMixin } from 'lightning/navigation';
import { refreshApex } from '@salesforce/apex';
import getCleanupSummary from '@salesforce/apex/MduCleanupDashboardController.getCleanupSummary';

export default class MduCleanupDashboard extends NavigationMixin(LightningElement) {
    wiredResult;
    categories = [];
    error;
    expandedKey;
    ownerFilter = '';

    @wire(getCleanupSummary)
    wiredCleanup(result) {
        this.wiredResult = result;
        if (result.data) {
            this.categories = result.data.map(c => ({
                ...c,
                tileClass: this.tileClassFor(c.severity, c.count),
                blank: c.count === 0,
                isExpanded: false
            }));
            this.error = undefined;
        } else if (result.error) {
            this.error = result.error.body ? result.error.body.message : String(result.error);
            this.categories = [];
        }
    }

    tileClassFor(severity, count) {
        if (count === 0) return 'tile tile-blank';
        switch (severity) {
            case 'critical': return 'tile tile-critical';
            case 'warning':  return 'tile tile-warning';
            case 'info':     return 'tile tile-info';
            default:         return 'tile';
        }
    }

    handleTileClick(event) {
        const key = event.currentTarget.dataset.key;
        this.expandedKey = (this.expandedKey === key) ? null : key;
        this.categories = this.categories.map(c => ({
            ...c,
            isExpanded: c.key === this.expandedKey
        }));
    }

    handleRowClick(event) {
        const recordId = event.currentTarget.dataset.id;
        const recordType = event.currentTarget.dataset.type;
        const objectApiName = recordType === 'Agreement' ? 'Agreement__c' : 'Opportunity';
        this[NavigationMixin.Navigate]({
            type: 'standard__recordPage',
            attributes: { recordId, objectApiName, actionName: 'view' }
        });
    }

    handleOppClick(event) {
        event.stopPropagation();
        const oppId = event.currentTarget.dataset.id;
        this[NavigationMixin.Navigate]({
            type: 'standard__recordPage',
            attributes: { recordId: oppId, objectApiName: 'Opportunity', actionName: 'view' }
        });
    }

    handleRefresh() {
        return refreshApex(this.wiredResult);
    }

    handleOwnerFilterChange(event) {
        this.ownerFilter = (event.target.value || '').trim().toLowerCase();
    }

    get expandedCategory() {
        if (!this.expandedKey) return null;
        const cat = this.categories.find(c => c.key === this.expandedKey);
        if (!cat) return null;
        const filter = this.ownerFilter;
        const filteredRows = filter
            ? cat.rows.filter(r =>
                (r.oppOwner && r.oppOwner.toLowerCase().includes(filter)) ||
                (r.reAssigned && r.reAssigned.toLowerCase().includes(filter))
              )
            : cat.rows;
        return { ...cat, filteredRows, filteredCount: filteredRows.length };
    }

    get totalIssues() {
        return this.categories.reduce((sum, c) => sum + c.count, 0);
    }

    get allClear() {
        return this.categories.length > 0 && this.totalIssues === 0;
    }
}
