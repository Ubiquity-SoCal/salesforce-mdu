import { createElement } from 'lwc';
import MduOutreachSelector from 'c/mduOutreachSelector';
import candidates from '@salesforce/apex/OutreachSelectionController.candidates';

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

function build() {
    const element = createElement('c-mdu-outreach-selector', { is: MduOutreachSelector });
    document.body.appendChild(element);
    return element;
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
