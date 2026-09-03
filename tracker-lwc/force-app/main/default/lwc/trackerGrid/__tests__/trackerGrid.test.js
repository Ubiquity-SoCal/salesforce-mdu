import { createElement } from 'lwc';
import TrackerGrid from 'c/trackerGrid';
import getActiveViews from '@salesforce/apex/TrackerController.getActiveViews';
import getTrackerData from '@salesforce/apex/TrackerController.getTrackerData';
import getTrackerSummary from '@salesforce/apex/TrackerController.getTrackerSummary';
import getTrackerDataFullWithCampaign from '@salesforce/apex/TrackerController.getTrackerDataFullWithCampaign';
import getTrackerSummaryFilteredWithCampaign from '@salesforce/apex/TrackerController.getTrackerSummaryFilteredWithCampaign';
import getActiveCampaignsForFilter from '@salesforce/apex/TrackerController.getActiveCampaignsForFilter';
import getActiveUsers from '@salesforce/apex/TrackerController.getActiveUsers';
import getAgreementPicklists from '@salesforce/apex/TrackerController.getAgreementPicklists';
import getContactRoleOptions from '@salesforce/apex/TrackerController.getContactRoleOptions';
import getPicklistValuesApex from '@salesforce/apex/TrackerController.getPicklistValues';

jest.mock(
    '@salesforce/apex/TrackerController.getActiveViews',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getTrackerData',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getTrackerSummary',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getTrackerDataFullWithCampaign',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getTrackerSummaryFilteredWithCampaign',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getActiveCampaignsForFilter',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getActiveUsers',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getAgreementPicklists',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getContactRoleOptions',
    () => ({ default: jest.fn() }),
    { virtual: true }
);
jest.mock(
    '@salesforce/apex/TrackerController.getPicklistValues',
    () => ({ default: jest.fn() }),
    { virtual: true }
);

// The view definition's own default sort. A user who picks a different sort in
// the toolbar must not be silently reset back to this by Refresh.
const VIEW_CONFIG = JSON.stringify({
    columns: [
        { field: 'Name', label: 'Name' },
        { field: 'StageName', label: 'Stage' },
        { field: 'Next_Action__c', label: 'Action', width: 220 }
    ],
    sort: { field: 'Name', direction: 'ASC' },
    formatting_rules: []
});

// 215 chars, the longest Next_Action__c actually in the org. At the grid's 13px
// font that is roughly 1400px of text inside a column configured for 220px.
const LONG_ACTION =
    'AK engaged (owns 18, this + Royal Gardens are the 2 near our fiber). ' +
    'Melissa picking up and addressing 6 items (renewal terms, balloon, ' +
    'flat fee, tenant terms) before the next call with the ownership group.';

const SHORT_ACTION = 'Call owner';

// Niraj Patel and Dana Whitfield are deliberately NOT in the hardcoded team
// lists inside buildOwnerOptions()/buildREAssignedOptions(). They only ever
// reach the dropdowns by being present in the loaded records, so they are the
// names that vanish when the option lists get rebuilt from a filtered slice.
const recordsFull = () => [
    {
        Id: '006000000000001',
        Name: 'Test Property',
        StageName: 'Prospecting',
        Owner: { Name: 'Taylor Mauney' },
        RE_Assigned__r: { Name: 'Justin Barry' },
        Next_Action__c: SHORT_ACTION
    },
    {
        Id: '006000000000002',
        Name: 'Second Property',
        StageName: 'Negotiation',
        Owner: { Name: 'Niraj Patel' },
        RE_Assigned__r: { Name: 'Dana Whitfield' },
        Next_Action__c: LONG_ACTION
    }
];

const recordsNarrow = () => [recordsFull()[0]];

// A distinct second page that, like recordsNarrow, contains no Niraj Patel.
// Distinct Id matters: real paging never repeats a record, and reusing one makes
// LWC log a duplicate row-key error.
const recordsPage2 = () => [
    {
        Id: '006000000000003',
        Name: 'Third Property',
        StageName: 'Prospecting',
        Owner: { Name: 'Taylor Mauney' },
        RE_Assigned__r: { Name: 'Justin Barry' }
    }
];

// hasMore defaults true so the Load More button renders and can be clicked.
const dataPayload = (records = recordsFull(), hasMore = true) => ({
    viewConfig: { Config__c: VIEW_CONFIG },
    records,
    totalCount: records.length,
    hasMore
});

const summaryPayload = () => ({
    totalOpportunities: 1,
    totalUnits: 10,
    totalAgreements: 0,
    agreementsByType: []
});

const flush = () =>
    Promise.resolve()
        .then(() => Promise.resolve())
        .then(() => Promise.resolve());

describe('c-tracker-grid', () => {
    let element;

    beforeEach(async () => {
        getActiveViews.mockResolvedValue([
            { Id: 'a0V000000000001', Name: 'MDU Tracker' },
            { Id: 'a0V000000000002', Name: 'Business Tracker' }
        ]);
        getTrackerData.mockResolvedValue(dataPayload());
        getTrackerSummary.mockResolvedValue(summaryPayload());
        getTrackerDataFullWithCampaign.mockResolvedValue(dataPayload());
        getTrackerSummaryFilteredWithCampaign.mockResolvedValue(summaryPayload());
        getActiveCampaignsForFilter.mockResolvedValue([
            { Id: '701000000000001', Name: 'TX On-Net' }
        ]);
        getActiveUsers.mockResolvedValue([]);
        getAgreementPicklists.mockResolvedValue({});
        getContactRoleOptions.mockResolvedValue([]);
        getPicklistValuesApex.mockResolvedValue({});

        element = createElement('c-tracker-grid', { is: TrackerGrid });
        document.body.appendChild(element);
        await flush();
        await flush();
    });

    afterEach(() => {
        while (document.body.firstChild) {
            document.body.removeChild(document.body.firstChild);
        }
        jest.clearAllMocks();
    });

    const clickRefresh = async () => {
        const buttons = [
            ...element.shadowRoot.querySelectorAll('lightning-button')
        ];
        const refresh = buttons.find((b) => b.label === 'Refresh');
        expect(refresh).toBeDefined();
        refresh.dispatchEvent(new CustomEvent('click'));
        await flush();
        await flush();
    };

    const setCombobox = async (selector, value) => {
        const cb = element.shadowRoot.querySelector(selector);
        expect(cb).not.toBeNull();
        cb.dispatchEvent(new CustomEvent('change', { detail: { value } }));
        await flush();
        await flush();
    };

    const optionValues = (selector) => {
        const cb = element.shadowRoot.querySelector(selector);
        expect(cb).not.toBeNull();
        return (cb.options || []).map((o) => o.value);
    };

    describe('Refresh button', () => {
    it('re-queries with the owner filter still applied', async () => {
        await setCombobox('.owner-selector', 'Taylor Mauney');
        getTrackerDataFullWithCampaign.mockClear();

        await clickRefresh();

        expect(getTrackerDataFullWithCampaign).toHaveBeenCalled();
        expect(getTrackerDataFullWithCampaign.mock.calls[0][0]).toEqual(
            expect.objectContaining({ ownerName: 'Taylor Mauney' })
        );
    });

    it('re-queries with every active filter still applied', async () => {
        await setCombobox('.owner-selector', 'Taylor Mauney');
        await setCombobox('.re-assigned-selector', 'Niraj Patel');
        await setCombobox('.date-range-selector', 'NEXT_90');
        await setCombobox('.campaign-selector', '701000000000001');

        const toggle = element.shadowRoot.querySelector('.hide-closed-toggle');
        expect(toggle).not.toBeNull();
        toggle.checked = true;
        toggle.dispatchEvent(new CustomEvent('change'));
        await flush();
        await flush();

        getTrackerDataFullWithCampaign.mockClear();
        getTrackerSummaryFilteredWithCampaign.mockClear();

        await clickRefresh();

        expect(getTrackerDataFullWithCampaign.mock.calls[0][0]).toEqual(
            expect.objectContaining({
                ownerName: 'Taylor Mauney',
                reAssignedName: 'Niraj Patel',
                dateRange: 'NEXT_90',
                campaignId: '701000000000001',
                hideClosed: true
            })
        );
        // The summary tiles must describe the same filtered set as the grid.
        expect(getTrackerSummaryFilteredWithCampaign.mock.calls[0][0]).toEqual(
            expect.objectContaining({
                ownerName: 'Taylor Mauney',
                reAssignedName: 'Niraj Patel',
                dateRange: 'NEXT_90',
                campaignId: '701000000000001',
                hideClosed: true
            })
        );
    });

    it('never falls back to the unfiltered view loader', async () => {
        await setCombobox('.owner-selector', 'Taylor Mauney');
        getTrackerData.mockClear();

        await clickRefresh();

        expect(getTrackerData).not.toHaveBeenCalled();
    });

    it('keeps the sort the user chose instead of reverting to the view default', async () => {
        await setCombobox('.sort-field', 'StageName');
        getTrackerDataFullWithCampaign.mockClear();

        await clickRefresh();

        expect(getTrackerDataFullWithCampaign.mock.calls[0][0]).toEqual(
            expect.objectContaining({ userSortField: 'StageName' })
        );
    });
    });

    describe('filter dropdown options', () => {
        it('starts with every owner and RE present in the loaded records', () => {
            expect(optionValues('.owner-selector')).toContain('Niraj Patel');
            expect(optionValues('.re-assigned-selector')).toContain(
                'Dana Whitfield'
            );
        });

        it('does not drop owners when a narrowed query comes back', async () => {
            // A sort change re-queries through reloadFromServer(). Any filter the
            // user already had applied narrows the result, and the dropdowns must
            // not shrink to match it.
            getTrackerDataFullWithCampaign.mockResolvedValue(
                dataPayload(recordsNarrow())
            );

            await setCombobox('.sort-field', 'StageName');

            expect(optionValues('.owner-selector')).toContain('Niraj Patel');
        });

        it('does not drop RE names when a narrowed query comes back', async () => {
            getTrackerDataFullWithCampaign.mockResolvedValue(
                dataPayload(recordsNarrow())
            );

            await setCombobox('.sort-field', 'StageName');

            expect(optionValues('.re-assigned-selector')).toContain(
                'Dana Whitfield'
            );
        });

        it('keeps the active selection present as an option', async () => {
            // If the selection disappears from the option list the combobox
            // renders blank while the filter is still being applied.
            await setCombobox('.owner-selector', 'Niraj Patel');
            getTrackerDataFullWithCampaign.mockResolvedValue(
                dataPayload(recordsNarrow())
            );

            await setCombobox('.sort-field', 'StageName');

            expect(optionValues('.owner-selector')).toContain('Niraj Patel');
        });

        it('does not drop owners when loading another page of a filtered set', async () => {
            // handleLoadMore appends, so records only grows. The leak is that the
            // preceding filtered query already narrowed records, and load-more then
            // rebuilds the dropdown off that narrowed accumulation.
            getTrackerDataFullWithCampaign.mockResolvedValue(
                dataPayload(recordsNarrow())
            );
            await setCombobox('.owner-selector', 'Taylor Mauney');
            expect(optionValues('.owner-selector')).toContain('Niraj Patel');

            getTrackerDataFullWithCampaign.mockResolvedValue(
                dataPayload(recordsPage2(), false)
            );
            const loadMore = [
                ...element.shadowRoot.querySelectorAll('lightning-button')
            ].find((b) => b.label === 'Load More');
            expect(loadMore).toBeDefined();
            loadMore.dispatchEvent(new CustomEvent('click'));
            await flush();
            await flush();

            expect(optionValues('.owner-selector')).toContain('Niraj Patel');
        });

        it('resets the lists on a view switch so one view does not leak into the next', async () => {
            // The guard on the fix: options may only grow WITHIN a view.
            getTrackerData.mockResolvedValue(dataPayload(recordsNarrow()));

            await setCombobox('.view-selector', 'a0V000000000002');

            expect(optionValues('.owner-selector')).not.toContain('Niraj Patel');
            expect(optionValues('.re-assigned-selector')).not.toContain(
                'Dana Whitfield'
            );
        });
    });

    describe('overflow tooltips', () => {
        // Addressed by record id, not row index: displayRows is sorted by Name,
        // so index order is not fixture order.
        const cell = (recordId, field) =>
            element.shadowRoot.querySelector(
                `td[data-record-id="${recordId}"][data-field="${field}"]`
            );

        const LONG_ROW = '006000000000002';
        const SHORT_ROW = '006000000000001';

        it('renders one Action cell per row', () => {
            expect(
                element.shadowRoot.querySelectorAll(
                    'td[data-field="Next_Action__c"]'
                )
            ).toHaveLength(2);
        });

        it('puts the full text on a value too long for its column', () => {
            // The column is capped at 220px and clips, so the only way to read a
            // 215-char action is the tooltip.
            expect(cell(LONG_ROW, 'Next_Action__c').title).toBe(LONG_ACTION);
        });

        it('leaves a value that fits without a tooltip', () => {
            expect(cell(SHORT_ROW, 'Next_Action__c').title).toBe('');
        });

        it('marks only the cell being edited so it can widen past the cap', async () => {
            const target = cell(LONG_ROW, 'Next_Action__c');
            expect(target.className).not.toContain('editing-cell');

            target.click();
            await flush();
            await flush();

            expect(
                cell(LONG_ROW, 'Next_Action__c').className
            ).toContain('editing-cell');
            expect(
                cell(SHORT_ROW, 'Next_Action__c').className
            ).not.toContain('editing-cell');
        });

        it('measures against the column width, not a fixed length', () => {
            // Name has no configured width so it falls back to 150px. 'Second
            // Property' is 15 chars, ~116px, which fits. Guards against the
            // threshold being hardcoded rather than read from col.width.
            expect(cell(LONG_ROW, 'Name').title).toBe('');
        });
    });
});
