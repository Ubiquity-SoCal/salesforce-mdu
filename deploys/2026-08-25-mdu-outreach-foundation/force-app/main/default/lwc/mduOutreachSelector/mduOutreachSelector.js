import { LightningElement, api, track, wire } from 'lwc';
import candidates from '@salesforce/apex/OutreachSelectionController.candidates';

/**
 * The screen a rep uses to turn a filtered list of MDU properties into a mailing. The one thing
 * this component exists to say: properties are not recipients. Two properties can share a
 * mailbox (a management company holding several buildings), so a count of selected rows always
 * overstates how many people are about to be emailed. The counter reports both numbers, and a
 * blocked row (no contact, ineligible stage, already mailed) stays visible with its reason
 * instead of being filtered out, because hiding it would hide the real ceiling on this
 * programme's volume.
 */
export default class MduOutreachSelector extends LightningElement {
    @track rows = [];
    @track selected = new Set();

    city = 'Omaha';
    state = 'NE';
    stageFilter = null;
    minUnits = null;
    mineOnly = false;

    @wire(candidates, {
        city: '$city', state: '$state', stageFilter: '$stageFilter',
        minUnits: '$minUnits', mineOnly: '$mineOnly'
    })
    wiredCandidates({ data, error }) {
        if (data) {
            // notSelectable, not !selectable: LWC template expressions cannot negate, so the
            // template needs the row to already carry the sense it will read.
            this.rows = data.map((row) => ({ ...row, notSelectable: !row.selectable }));
            this.error = undefined;
        } else if (error) {
            this.error = error;
            this.rows = [];
        }
    }

    // @api, not a plain getter: this engine enforces the public/private boundary on custom
    // element instances, so a caller outside the component (the confirm screen in Task 5, this
    // component's own jest tests) gets `undefined` back from an unexposed member rather than the
    // real value. The Interfaces section calls this "a component exposing selectedIds"; @api is
    // what actually exposes it.
    @api
    get selectedIds() {
        return Array.from(this.selected);
    }

    /**
     * Recipients, not properties. Two selected properties sharing one address are one email, and
     * the counter has to say so before the rep confirms, not after.
     */
    get recipientCount() {
        const keys = new Set();
        for (const row of this.rows) {
            if (this.selected.has(row.opportunityId) && row.emailKey) {
                keys.add(row.emailKey);
            }
        }
        return keys.size;
    }

    /**
     * `recipients` stays plural even at exactly one; the awkward "1 recipients" reads better
     * than a second branch nobody tests.
     */
    get counterText() {
        const properties = this.selected.size;
        const noun = properties === 1 ? 'property' : 'properties';
        return `${properties} ${noun} selected, ${this.recipientCount} recipients after dedupe`;
    }

    handleToggle(event) {
        const id = event.currentTarget.dataset.id;
        const row = this.rows.find((r) => r.opportunityId === id);
        if (!row || !row.selectable) {
            return;
        }
        // A Set returned from a getter is not reactive on mutation, so every change builds a NEW
        // Set rather than calling .add/.delete on the existing one; mutating in place leaves the
        // template unaware anything changed.
        const next = new Set(this.selected);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        this.selected = next;
    }

    @api
    selectAllSelectable() {
        const next = new Set();
        for (const row of this.rows) {
            if (row.selectable) {
                next.add(row.opportunityId);
            }
        }
        this.selected = next;
    }
}
