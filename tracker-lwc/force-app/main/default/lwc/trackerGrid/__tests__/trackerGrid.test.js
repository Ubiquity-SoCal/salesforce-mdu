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
        { field: 'StageName', label: 'Stage' }
    ],
    sort: { field: 'Name', direction: 'ASC' },
    formatting_rules: []
});

const dataPayload = () => ({
    viewConfig: { Config__c: VIEW_CONFIG },
    records: [
        { Id: '006000000000001', Name: 'Test Property', StageName: 'Prospecting' }
    ],
    totalCount: 1,
    hasMore: false
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

describe('c-tracker-grid Refresh button', () => {
    let element;

    beforeEach(async () => {
        getActiveViews.mockResolvedValue([
            { Id: 'a0V000000000001', Name: 'MDU Tracker' }
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
