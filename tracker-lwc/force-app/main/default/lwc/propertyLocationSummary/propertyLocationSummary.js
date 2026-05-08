import { LightningElement, api, wire } from 'lwc';
import getSummary from '@salesforce/apex/PropertyLocationSummaryController.getSummary';

export default class PropertyLocationSummary extends LightningElement {
    @api recordId;
    summary;
    error;

    @wire(getSummary, { opportunityId: '$recordId' })
    wiredSummary({ error, data }) {
        if (data) {
            this.summary = data;
            this.error = undefined;
        } else if (error) {
            this.error = error;
            this.summary = undefined;
        }
    }

    get hasPL() {
        return this.summary && this.summary.plId;
    }

    get plUrl() {
        return this.summary && this.summary.plId ? '/' + this.summary.plId : '#';
    }

    get oppCount() {
        return this.summary && this.summary.oppCount != null ? this.summary.oppCount : 0;
    }

    get unitCount() {
        return this.summary && this.summary.unitCount != null ? this.summary.unitCount : 0;
    }

    get activeUnitCount() {
        return this.summary && this.summary.activeUnitCount != null ? this.summary.activeUnitCount : 0;
    }
}
