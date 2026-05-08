import { LightningElement, api, wire } from 'lwc';
import getBuildingOpps from '@salesforce/apex/PLBuildingOppsController.getBuildingOpps';

export default class PropertyLocationBuildingOpps extends LightningElement {
    @api recordId;
    rows;
    error;

    @wire(getBuildingOpps, { propertyLocationId: '$recordId' })
    wired({ error, data }) {
        if (data) {
            this.rows = data;
            this.error = undefined;
        } else if (error) {
            this.error = error;
            this.rows = undefined;
        }
    }

    get hasRows() {
        return this.rows && this.rows.length > 0;
    }

    get count() {
        return this.rows ? this.rows.length : 0;
    }

    get cardTitle() {
        return `Building-Level Opportunities (${this.count})`;
    }
}
