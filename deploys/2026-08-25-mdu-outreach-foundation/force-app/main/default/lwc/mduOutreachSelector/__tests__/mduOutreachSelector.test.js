import { createElement } from 'lwc';
import MduOutreachSelector from 'c/mduOutreachSelector';
import candidates from '@salesforce/apex/OutreachSelectionController.candidates';
import preview from '@salesforce/apex/OutreachSelectionController.preview';

// The brief for this test mocked `candidates` as a plain `jest.fn()` and drove it with
// `mockResolvedValue`. That pattern is correct for an IMPERATIVE Apex call, but this component
// consumes `candidates` through `@wire`, and `@wire` does not call the imported reference as a
// promise-returning function: LWC's wiring engine invokes it as an adapter CONSTRUCTOR, passing
// a data callback, and expects the returned instance to expose connect/update/disconnect/emit.
// Verified directly: with the plain jest.fn() mock, `candidates.mock.calls[0][0]` was the
// engine's own callback function, never the `{city, state, ...}` config object, and the mock's
// resolved value never reached the component; every row-count assertion below failed with 0
// rendered rows against the brief's version of this test. `createApexTestWireAdapter` from
// `@salesforce/wire-service-jest-util` (bundled with sfdx-lwc-jest, the same toolchain this task
// copies from tracker-lwc) builds the real adapter protocol, so `candidates.emit(rows)` pushes
// data through the wire exactly the way a resolved cacheable Apex method would in production.
jest.mock(
    '@salesforce/apex/OutreachSelectionController.candidates',
    () => {
        // eslint-disable-next-line global-require
        const { createApexTestWireAdapter } = require('@salesforce/wire-service-jest-util');
        return { default: createApexTestWireAdapter(jest.fn()) };
    },
    { virtual: true }
);

// preview and confirmSelection are IMPERATIVE Apex calls, not @wire adapters, so unlike
// candidates above, the plain jest.fn() + mockResolvedValue pattern is the correct one here.
jest.mock(
    '@salesforce/apex/OutreachSelectionController.preview',
    () => ({ default: jest.fn() }),
    { virtual: true }
);

// No assertion below drives this one directly, but mduOutreachSelector.js imports it at module
// scope for handleConfirm. Leaving it unmocked would fail module resolution the moment the
// component is required, breaking every test in this file, not just the preview-gate ones.
jest.mock(
    '@salesforce/apex/OutreachSelectionController.confirmSelection',
    () => ({ default: jest.fn() }),
    { virtual: true }
);

const ROWS = [
    { opportunityId: '006A', propertyName: 'Camelot Village', units: 485,
      emailKey: 'mhardy@elevateliving.com', chip: 'Ready', selectable: true },
    { opportunityId: '006B', propertyName: 'The Richards Apartments', units: 30,
      emailKey: 'philbuttner@cox.net', chip: 'Duplicate recipient', selectable: true },
    { opportunityId: '006C', propertyName: 'St Frances Apartments', units: 15,
      emailKey: 'philbuttner@cox.net', chip: 'Duplicate recipient', selectable: true },
    { opportunityId: '006D', propertyName: 'Orphan Property', units: 50,
      emailKey: null, chip: 'No contact', selectable: false }
];

const PREVIEWS = [
    { toAddress: 'pdg@example.com', subject: 'Fiber at The Frederick, no cost to ownership',
      bodyHtml: '<p>Hello Paladino,</p>', propertyCount: 17, totalUnits: 315, variant: 'C' },
    { toAddress: 'philbuttner@cox.net', subject: 'Fiber at The Richards Apartments, no cost to ownership',
      bodyHtml: '<p>Hello Phil,</p>', propertyCount: 3, totalUnits: 53, variant: 'B' },
    { toAddress: 'mhardy@elevateliving.com', subject: 'Fiber at Camelot Village, no cost to ownership',
      bodyHtml: '<p>Hello Michelle,</p>', propertyCount: 1, totalUnits: 485, variant: 'A' }
];

function build() {
    const element = createElement('c-mdu-outreach-selector', { is: MduOutreachSelector });
    document.body.appendChild(element);
    return element;
}

// Several microtask ticks, not one. A single `await Promise.resolve()` is enough when a test
// pokes a property directly, but a DOM-driven test has to let the click handler's promise chain
// settle AND the resulting re-render flush, which is more than one turn of the queue.
async function flush() {
    for (let i = 0; i < 4; i++) {
        // eslint-disable-next-line no-await-in-loop
        await Promise.resolve();
    }
}

describe('c-mdu-outreach-selector', () => {
    afterEach(() => {
        while (document.body.firstChild) {
            document.body.removeChild(document.body.firstChild);
        }
        jest.clearAllMocks();
    });

    it('shows blocked rows rather than hiding them', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        const rendered = element.shadowRoot.querySelectorAll('[data-row]');
        expect(rendered).toHaveLength(4);
    });

    it('counts recipients after dedupe, not properties', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        element.selectAllSelectable();
        await Promise.resolve();

        const counter = element.shadowRoot.querySelector('[data-counter]');
        expect(counter.textContent).toBe('3 properties selected, 2 recipients after dedupe');
    });

    it('refuses to select a blocked row via selectAllSelectable', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        element.selectAllSelectable();
        await Promise.resolve();

        expect(element.selectedIds).not.toContain('006D');
    });

    // The test above only proves that selectAllSelectable's OWN filter skips blocked rows; it
    // never exercises handleToggle, so it would still pass even with the guard clause deleted
    // from handleToggle entirely. A rep does not select rows through selectAllSelectable, they
    // click a checkbox, which is exactly the path this test drives instead. The selectable-row
    // toggle is a positive control: without it, a handler that dropped every event (not just
    // blocked ones) would also make the blocked-row assertion pass for the wrong reason.
    it('refuses to select a blocked row when its own checkbox is toggled', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        const blockedCheckbox = element.shadowRoot.querySelector(
            'lightning-input[data-id="006D"]'
        );
        blockedCheckbox.dispatchEvent(new CustomEvent('change'));
        await Promise.resolve();

        expect(element.selectedIds).not.toContain('006D');

        const readyCheckbox = element.shadowRoot.querySelector(
            'lightning-input[data-id="006A"]'
        );
        readyCheckbox.dispatchEvent(new CustomEvent('change'));
        await Promise.resolve();

        expect(element.selectedIds).toContain('006A');
    });

    it('marks the blocked row disabled without negating an expression in the template', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        const blockedCheckbox = element.shadowRoot.querySelector(
            'lightning-input[data-id="006D"]'
        );
        const readyCheckbox = element.shadowRoot.querySelector(
            'lightning-input[data-id="006A"]'
        );
        expect(blockedCheckbox.disabled).toBe(true);
        expect(readyCheckbox.disabled).toBe(false);
    });

    it('reports zero recipients when nothing is selected', async () => {
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();

        const counter = element.shadowRoot.querySelector('[data-counter]');
        expect(counter.textContent).toBe('0 properties selected, 0 recipients after dedupe');
    });
});

describe('the preview gate', () => {
    afterEach(() => {
        while (document.body.firstChild) {
            document.body.removeChild(document.body.firstChild);
        }
        jest.clearAllMocks();
    });

    // candidates.emit(ROWS) has to come AFTER build(), not before it, even though the brief's
    // version of this test called candidates.mockResolvedValue(ROWS) before build(). The wire
    // adapter's static emit() only pushes to instances already registered in
    // TestWireAdapterTemplate._wireInstances, and connect() only happens once the component is
    // created and inserted; emitting first would land on zero instances, this.rows would stay
    // empty, and selectAllSelectable() would select nothing. The assertions below would still
    // pass in that case only because preview.mockResolvedValue resolves the same PREVIEWS
    // regardless of what opportunityIds it was called with, which is exactly the kind of
    // pass-for-the-wrong-reason the standing question is meant to catch, so this suite keeps the
    // ordering that actually exercises the wired data reaching the rows.
    it('keeps confirm disabled before any preview is opened', async () => {
        preview.mockResolvedValue(PREVIEWS);
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();
        element.selectAllSelectable();
        await element.loadPreviews();

        expect(element.confirmDisabled).toBe(true);
    });

    it('keeps confirm disabled after only some previews are seen', async () => {
        preview.mockResolvedValue(PREVIEWS);
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();
        element.selectAllSelectable();
        await element.loadPreviews();

        element.markPreviewSeen(0);
        element.markPreviewSeen(1);

        expect(element.confirmDisabled).toBe(true);
    });

    it('enables confirm only once every preview has been seen', async () => {
        preview.mockResolvedValue(PREVIEWS);
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();
        element.selectAllSelectable();
        await element.loadPreviews();

        element.markPreviewSeen(0);
        element.markPreviewSeen(1);
        element.markPreviewSeen(2);

        expect(element.confirmDisabled).toBe(false);
    });

    // The one that matters. A rep who previews three emails and then adds forty more properties
    // has approved nothing about those forty; Confirm has to lock again the instant the
    // selection changes, not stay unlocked because it was unlocked a moment ago.
    it('re-locks confirm when the selection changes after previewing', async () => {
        preview.mockResolvedValue(PREVIEWS);
        const element = build();
        candidates.emit(ROWS);
        await Promise.resolve();
        element.selectAllSelectable();
        await element.loadPreviews();
        [0, 1, 2].forEach((i) => element.markPreviewSeen(i));
        expect(element.confirmDisabled).toBe(false);

        element.selected = new Set(['006A']);

        expect(element.confirmDisabled).toBe(true);
    });

    // Every test above this line reaches loadPreviews through @api. That is exactly how a dead
    // Confirm button shipped: ten tests proved the method worked and not one proved anything
    // called it, because the @api decorator added to make it testable is what made the gap
    // invisible. These two go through the DOM, and the first fails on a missing element rather
    // than a wrong value if the wiring is ever removed again.
    describe('the preview trigger', () => {
        it('loads previews when the rep clicks Preview, not only when a test calls the method', async () => {
            preview.mockResolvedValue(PREVIEWS);
            const element = build();
            candidates.emit(ROWS);
            await flush();
            element.selectAllSelectable();
            await flush();

            const button = element.shadowRoot.querySelector('[data-preview]');
            expect(button).not.toBeNull();
            button.click();
            await flush();

            expect(preview).toHaveBeenCalled();
            expect(element.shadowRoot.querySelectorAll('[data-preview-item]')).toHaveLength(3);
        });

        it('does not reinstall a stale preview list when the selection changes mid flight', async () => {
            let release;
            preview.mockReturnValue(new Promise((resolve) => { release = resolve; }));
            const element = build();
            candidates.emit(ROWS);
            await flush();
            element.selectAllSelectable();
            await flush();

            element.shadowRoot.querySelector('[data-preview]').click();
            // The rep changes their mind while the call is still in flight. The setter clears
            // previews; the resolving promise must not put them back, or they mark three stale
            // emails read and confirm a batch they never previewed.
            element.selected = new Set();
            await flush();
            release(PREVIEWS);
            await flush();

            expect(element.shadowRoot.querySelectorAll('[data-preview-item]')).toHaveLength(0);
            expect(element.confirmDisabled).toBe(true);
        });
    });

    describe('the filters', () => {
        it('passes a typed city through to the wire', async () => {
            const element = build();
            candidates.emit(ROWS);
            await flush();

            const input = element.shadowRoot.querySelector('[data-filter-city]');
            expect(input).not.toBeNull();
            input.dispatchEvent(new CustomEvent('change', { detail: { value: 'Lincoln' } }));
            await flush();

            expect(candidates.getLastConfig().city).toBe('Lincoln');
        });

        it('passes a minimum unit count through as a number, not a string', async () => {
            const element = build();
            candidates.emit(ROWS);
            await flush();

            element.shadowRoot.querySelector('[data-filter-min-units]')
                .dispatchEvent(new CustomEvent('change', { detail: { value: '250' } }));
            await flush();

            // Apex takes this as a Decimal. A string would not bind.
            expect(candidates.getLastConfig().minUnits).toBe(250);
        });

        it('clears the selection when a filter changes, so a stale preview cannot be confirmed', async () => {
            preview.mockResolvedValue(PREVIEWS);
            const element = build();
            candidates.emit(ROWS);
            await flush();
            element.selectAllSelectable();
            await flush();
            element.shadowRoot.querySelector('[data-preview]').click();
            await flush();

            // Mark every preview read through the DOM, not markPreviewSeen, so this also proves
            // the read buttons are wired. Confirm must be live BEFORE the filter changes, or the
            // assertion after it proves nothing.
            element.shadowRoot
                .querySelectorAll('[data-preview-item] lightning-button')
                .forEach((b) => b.click());
            await flush();
            expect(element.confirmDisabled).toBe(false);

            element.shadowRoot.querySelector('[data-filter-city]')
                .dispatchEvent(new CustomEvent('change', { detail: { value: 'Lincoln' } }));
            await flush();

            expect(element.selectedIds).toHaveLength(0);
            expect(element.confirmDisabled).toBe(true);
        });
    });
});
