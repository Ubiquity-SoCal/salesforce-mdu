import { LightningElement, api, track, wire } from 'lwc';
import candidates from '@salesforce/apex/OutreachSelectionController.candidates';
import preview from '@salesforce/apex/OutreachSelectionController.preview';
import confirmSelection from '@salesforce/apex/OutreachSelectionController.confirmSelection';

/**
 * The screen a rep uses to turn a filtered list of MDU properties into a mailing. The one thing
 * this component exists to say: properties are not recipients. Two properties can share a
 * mailbox (a management company holding several buildings), so a count of selected rows always
 * overstates how many people are about to be emailed. The counter reports both numbers, and a
 * blocked row (no contact, ineligible stage, already mailed) stays visible with its reason
 * instead of being filtered out, because hiding it would hide the real ceiling on this
 * programme's volume.
 *
 * Task 5 adds the preview gate. Koa chose rep self-approval over a named human approver, so
 * there is no second person checking a batch before it reaches real property owners. This
 * mandatory preview IS the approval: Confirm stays disabled until every rendered preview has
 * been opened, and it locks again the instant the selection changes, because a rep who previews
 * three emails and then adds forty more properties has approved nothing about those forty.
 */
export default class MduOutreachSelector extends LightningElement {
    @track rows = [];
    @track previews = [];
    @track previewsSeen = new Set();

    // Both were previously assigned without ever being declared or rendered. `error` was set on
    // the wire failure path and shown nowhere, so an Apex error produced an empty table and no
    // message. `result` was assigned in handleConfirm and dropped on the floor, discarding all
    // five outcome channels the Apex layer deliberately keeps apart.
    @track error;
    @track result;

    // @track, not plain fields: the wire below reacts to these by $ reference, and a plain field
    // reassigned from a handler does not re-provision the wire.
    //
    // stageFilter is deliberately NOT exposed as an input. The spec defaults it to eligible
    // stages, no rep has asked to override it, and an input would need the stage vocabulary,
    // which belongs with the eligibility work rather than here. Omission, not oversight.
    @track city = 'Omaha';
    @track state = 'NE';
    @track stageFilter = null;
    @track minUnits = null;
    @track mineOnly = false;

    // `selected` is an accessor pair, not a plain `@track` field, so that reassigning it from
    // ANYWHERE (a checkbox toggle, selectAllSelectable, or a test poking the property directly)
    // clears the previews as a side effect. That is the entire mechanism behind the re-lock: it
    // is not special-cased in handleToggle or selectAllSelectable, it falls out of both of them
    // already doing `this.selected = next`. Only one of the getter/setter pair needs the `@api`
    // decorator; LWC's compiler treats a decorated getter and its sibling setter as one public
    // property, and decorating both throws a build error (SINGLE_DECORATOR_ON_SETTER_GETTER_PAIR).
    // Removing `@track selected` matters too: a tracked field and an accessor of the same name
    // collide at build time, they are not two independent things layered on top of each other.
    _selected = new Set();

    // Every load of the previews carries a generation number. A load whose number is no longer
    // current lost a race and must not assign. Without this, a rep who toggles a checkbox while
    // preview() is in flight gets the stale list reinstalled AFTER the setter cleared it, marks
    // those three read, and confirms a batch that is not the one they approved. That is the
    // exact failure the re-lock exists to prevent, arriving through the back door.
    _previewToken = 0;

    @api
    get selected() {
        return this._selected;
    }

    set selected(value) {
        this._selected = value;
        this._previewToken++;
        this.previews = [];
        this.previewsSeen = new Set();
    }

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

    // @api so the test (and, in production, whatever wraps this screen) can drive loading the
    // previews directly rather than only through a button click. Without @api this resolves to
    // undefined from outside the component instead of throwing, and a visibility problem reads
    // like a broken loadPreviews implementation.
    @api
    async loadPreviews() {
        const token = ++this._previewToken;
        const loaded = await preview({ opportunityIds: this.selectedIds });
        if (token !== this._previewToken) {
            // Superseded, either by a selection change or by a later load. Assigning here would
            // undo the setter's clear.
            return this.previews;
        }
        this.previews = loaded;
        this.previewsSeen = new Set();
        return this.previews;
    }

    get previewDisabled() {
        return this.selected.size === 0;
    }

    // Every filter handler clears the selection by assigning through the `selected` setter, which
    // is also what drops the previews and re-locks Confirm. A rep who previewed three emails and
    // then changed the filter has approved nothing about the new list. Reusing the setter rather
    // than repeating its body is the same argument as handleToggle and selectAllSelectable.
    handleCityChange(event) {
        this.city = event.detail.value;
        this.selected = new Set();
    }

    handleStateChange(event) {
        this.state = event.detail.value;
        this.selected = new Set();
    }

    handleMinUnitsChange(event) {
        // Apex binds this to a Decimal, and an empty box must mean "no minimum" rather than
        // zero, which would still be a filter.
        const raw = event.detail.value;
        this.minUnits = raw === '' || raw === null || raw === undefined ? null : Number(raw);
        this.selected = new Set();
    }

    handleMineOnlyChange(event) {
        this.mineOnly = event.detail.checked;
        this.selected = new Set();
    }

    handleLoadPreviews() {
        return this.loadPreviews();
    }

    @api
    markPreviewSeen(index) {
        // Same reactivity rule as `selected`: build a NEW Set rather than mutating the existing
        // one, or confirmDisabled would keep reading the stale size.
        const next = new Set(this.previewsSeen);
        next.add(index);
        this.previewsSeen = next;
    }

    /**
     * Confirm unlocks only when every rendered preview has actually been opened. Koa declined a
     * human approver, so this screen is the approver and it must not be skippable. An empty
     * `previews` list (nothing loaded yet) must read as locked, not as vacuously satisfied by an
     * empty Set meeting an empty requirement.
     */
    @api
    get confirmDisabled() {
        if (!this.previews.length) {
            return true;
        }
        return this.previewsSeen.size < this.previews.length;
    }

    handlePreviewSeen(event) {
        this.markPreviewSeen(Number(event.currentTarget.dataset.index));
    }

    /**
     * An Apex error arrives as { body: { message } } from both an imperative call and a wire, but
     * as a plain Error from anywhere else. Reading only one shape is how a message becomes the
     * word "undefined" on screen.
     */
    get errorMessage() {
        if (!this.error) {
            return '';
        }
        return this.error.body ? this.error.body.message : this.error.message;
    }

    async handleConfirm() {
        this.error = undefined;
        try {
            this.result = await confirmSelection({ opportunityIds: this.selectedIds });
            // Assigning `selected` already clears previews and previewsSeen through the setter,
            // so the two explicit assignments this method used to make were redundant.
            this.selected = new Set();
        } catch (e) {
            // On failure the selection is deliberately KEPT, so a rep who is told to set their
            // Phone can fix it and retry without reselecting everything. Without this catch the
            // rejection was unhandled: it lost the message AND, under node, killed the process.
            this.error = e;
        }
    }
}
