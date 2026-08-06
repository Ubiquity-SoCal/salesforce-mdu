import { LightningElement, api, wire, track } from 'lwc';
import { NavigationMixin } from 'lightning/navigation';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import { getObjectInfo } from 'lightning/uiObjectInfoApi';
import { getPicklistValues } from 'lightning/uiObjectInfoApi';
import getActiveViews from '@salesforce/apex/TrackerController.getActiveViews';
import getActiveViewsForApp from '@salesforce/apex/TrackerController.getActiveViewsForApp';
import getTrackerData from '@salesforce/apex/TrackerController.getTrackerData';
import getTrackerDataPaged from '@salesforce/apex/TrackerController.getTrackerDataPaged';
import getTrackerSummary from '@salesforce/apex/TrackerController.getTrackerSummary';
import getTrackerSummaryFiltered from '@salesforce/apex/TrackerController.getTrackerSummaryFiltered';
import getTrackerDataPagedWithRE from '@salesforce/apex/TrackerController.getTrackerDataPagedWithRE';
import getTrackerDataFull from '@salesforce/apex/TrackerController.getTrackerDataFull';
import getTrackerDataFullWithCampaign from '@salesforce/apex/TrackerController.getTrackerDataFullWithCampaign';
import getTrackerSummaryFilteredWithCampaign from '@salesforce/apex/TrackerController.getTrackerSummaryFilteredWithCampaign';
import getActiveCampaignsForFilter from '@salesforce/apex/TrackerController.getActiveCampaignsForFilter';
// getTrackerSummaryFiltered now accepts 4 params (viewId, ownerName, dateRange, reAssignedName)
import saveRecords from '@salesforce/apex/TrackerController.saveRecords';
import getNotesForRecord from '@salesforce/apex/TrackerController.getNotesForRecord';
import getNotesForRecordPaged from '@salesforce/apex/TrackerController.getNotesForRecordPaged';
import getContactsForRecord from '@salesforce/apex/TrackerController.getContactsForRecord';
import createNote from '@salesforce/apex/TrackerController.createNote';
import getActiveUsers from '@salesforce/apex/TrackerController.getActiveUsers';
import getPicklistValuesApex from '@salesforce/apex/TrackerController.getPicklistValues';
import createAndLinkContact from '@salesforce/apex/TrackerController.createAndLinkContact';
import getContactRoleOptions from '@salesforce/apex/TrackerController.getContactRoleOptions';
import getAgreementsForRecord from '@salesforce/apex/TrackerController.getAgreementsForRecord';
import createAgreement from '@salesforce/apex/TrackerController.createAgreement';
import updateAgreement from '@salesforce/apex/TrackerController.updateAgreement';
import getAgreementPicklists from '@salesforce/apex/TrackerController.getAgreementPicklists';
import getActivitiesForRecord from '@salesforce/apex/TrackerController.getActivitiesForRecord';
import getActivitiesForRecordPaged from '@salesforce/apex/TrackerController.getActivitiesForRecordPaged';
import createActivity from '@salesforce/apex/TrackerController.createActivity';
import updateTaskStatus from '@salesforce/apex/TrackerController.updateTaskStatus';
import OPPORTUNITY_OBJECT from '@salesforce/schema/Opportunity';

export default class TrackerGrid extends NavigationMixin(LightningElement) {
    // App context — set via design property in App Builder
    @api appContext = '';

    // View state
    views = [];
    selectedViewId = '';
    viewConfig = null;
    columns = [];
    formattingRules = [];

    // Data state
    records = [];
    displayRows = [];
    dirtyRecords = new Map();
    isLoading = false;
    isSaving = false;

    // Edit state
    editingCell = null; // { recordId, field }

    // Sort state (client-side)
    sortField = '';
    sortDirection = 'ASC';

    // Filter state (client-side)
    filterField = '';
    filterValue = '';

    // Owner filter
    selectedOwner = '';
    // Hide Closed Sites toggle (server-side filter)
    hideClosed = false;
    ownerOptions = [];

    // Object metadata for picklists
    objectInfo;
    picklistOptionsCache = {};
    ownerOptions = [];

    // Server-side summary (full dataset, not limited by page)
    serverSummary = null;

    // Pagination
    currentOffset = 0;
    hasMoreRecords = false;
    totalRecordCount = 0;
    isLoadingMore = false;

    // Date range filter
    selectedDateRange = '';

    // RE Assigned filter
    selectedREAssigned = '';
    reAssignedOptions = [];

    // Unit Group (property size band) filter
    selectedUnitGroup = '';

    // Campaign filter
    selectedCampaign = '';
    campaignOptions = [];

    // Stage-change reason modal (On Hold / Prospecting / Closed Lost)
    stageReasonModalOpen = false;
    stageReasonModalRecordId = '';
    stageReasonModalRecordName = '';
    stageReasonModalStage = '';
    stageReasonModalField = '';
    stageReasonModalLabel = '';
    stageReasonModalValue = '';
    stageReasonModalOptions = [];
    stageReasonModalOriginalStage = '';

    // Side panel state (notes/activities/contacts)
    panelOpen = false;
    panelRecordId = '';
    panelRecordName = '';
    panelNotes = [];
    notesOffset = 0;
    notesPageSize = 5;
    hasMoreNotes = false;
    loadingMoreNotes = false;
    panelContacts = [];
    panelActivities = [];
    completedActivityOffset = 0;
    completedActivityPageSize = 5;
    hasMoreCompletedActivities = false;
    loadingMoreActivities = false;
    panelLoading = false;
    panelTab = 'notes'; // 'notes', 'activities', or 'contacts'
    newNoteTitle = '';
    newNoteBody = '';
    isSavingNote = false;

    // Agreements panel state (separate icon)
    agreementsPanelOpen = false;
    agreementsPanelRecordId = '';
    agreementsPanelRecordName = '';
    agreementsPanelLoading = false;

    // Activity state
    newActivityType = 'Call';
    newActivitySubject = '';
    newActivityDueDate = '';
    newActivityPriority = 'Normal';
    newActivityDescription = '';
    newActivityStartDate = '';
    newActivityStartTime = '09:00';
    newActivityEndTime = '10:00';
    newActivityLocation = '';
    isAddingActivity = false;

    activityTypeOptions = [
        { label: 'Log a Call', value: 'Call' },
        { label: 'New Task', value: 'Task' },
        { label: 'New Event', value: 'Meeting' },
        { label: 'Send Email', value: 'Email' }
    ];

    activityPriorityOptions = [
        { label: 'Normal', value: 'Normal' },
        { label: 'High', value: 'High' }
    ];

    get isCallActivity() { return this.newActivityType === 'Call'; }
    get isEmailActivity() { return this.newActivityType === 'Email'; }
    get isTaskActivity() { return this.newActivityType === 'Task'; }
    get isEventActivity() { return this.newActivityType === 'Meeting'; }
    get isCallOrEmail() { return this.isCallActivity || this.isEmailActivity; }
    get isTaskType() { return this.isTaskActivity; }
    get isEventType() { return this.isEventActivity; }
    get activityFormLabel() {
        if (this.isCallActivity) return 'Log Call';
        if (this.isEmailActivity) return 'Log Email';
        if (this.isTaskActivity) return 'Create Task';
        if (this.isEventActivity) return 'Create Event';
        return 'Add Activity';
    }
    get activitySubjectPlaceholder() {
        if (this.isCallActivity) return 'Call with...';
        if (this.isEmailActivity) return 'Email about...';
        if (this.isTaskActivity) return 'Follow up on...';
        if (this.isEventActivity) return 'Meeting about...';
        return 'Subject...';
    }
    get activityDescPlaceholder() {
        if (this.isCallOrEmail) return 'Notes about the conversation...';
        if (this.isEventType) return 'Meeting details...';
        return 'Description...';
    }

    // Agreement state
    panelAgreements = [];
    agreementTypeOptions = [];
    agreementStatusOptions = [];
    newAgreementType = '';
    newAgreementStatus = 'Not Started';
    newAgreementRequestedDate = '';
    newAgreementNotes = '';
    isAddingAgreement = false;
    editingAgreementId = '';
    editAgreementData = {};
    isSavingAgreement = false;

    // Add contact state
    newContactFirstName = '';
    newContactLastName = '';
    newContactEmail = '';
    newContactPhone = '';
    newContactRole = '';
    contactRoleOptions = [];
    isAddingContact = false;

    // Track if we have unsaved changes
    get hasUnsavedChanges() {
        return this.dirtyRecords.size > 0;
    }

    get dirtyCount() {
        return this.dirtyRecords.size;
    }

    get noRecords() {
        return !this.isLoading && this.displayRows.length === 0 && this.selectedViewId;
    }

    get viewOptions() {
        return this.views.map(v => ({
            label: v.Name,
            value: v.Id
        }));
    }

    get saveButtonLabel() {
        return 'Save (' + this.dirtyRecords.size + ')';
    }

    get recordCountLabel() {
        if (this.totalRecordCount && this.totalRecordCount > this.records.length) {
            return this.displayRows.length + ' of ' + this.totalRecordCount + ' records (showing ' + this.records.length + ' loaded)';
        }
        return this.displayRows.length + ' records';
    }

    // Summary stats — server data when no text filter, client-side when text filter active
    get _useClientSummary() {
        return this.filterField && this.filterValue;
    }

    get summaryOpps() {
        if (this._useClientSummary) return this.displayRows.length.toLocaleString();
        if (this.serverSummary) return this.serverSummary.totalOpportunities.toLocaleString();
        return this.displayRows.length.toLocaleString();
    }

    get summaryUnits() {
        if (this._useClientSummary) {
            let total = 0;
            for (const row of this.displayRows) {
                const val = row['Units__c'];
                if (val != null) total += Number(val) || 0;
            }
            return total.toLocaleString();
        }
        if (this.serverSummary) return this.serverSummary.totalUnits.toLocaleString();
        return '0';
    }

    get summaryAgreements() {
        if (this._useClientSummary) {
            const counts = {};
            for (const row of this.displayRows) {
                const agrs = row['_agreements'] || [];
                for (const agr of agrs) {
                    if (agr.Status__c === 'Completed') {
                        const t = agr.Agreement_Type__c || 'Other';
                        counts[t] = (counts[t] || 0) + 1;
                    }
                }
            }
            return Object.entries(counts)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => ({ key: type, label: type + ' ' + count, count }));
        }
        if (!this.serverSummary || !this.serverSummary.agreementsByType) return [];
        return this.serverSummary.agreementsByType.map(a => ({
            key: a.agreementType,
            label: a.agreementType + ' ' + a.count,
            count: a.count
        }));
    }

    get hasSummaryAgreements() {
        return this.summaryAgreements.length > 0;
    }

    get summaryTotalAgreements() {
        if (this._useClientSummary) {
            let total = 0;
            for (const row of this.displayRows) {
                for (const agr of (row['_agreements'] || [])) {
                    if (agr.Status__c === 'Completed') total++;
                }
            }
            return total.toLocaleString();
        }
        if (this.serverSummary) return this.serverSummary.totalAgreements.toLocaleString();
        return '0';
    }

    get unsavedLabel() {
        return this.dirtyRecords.size + ' unsaved change(s)';
    }

    get sortableColumns() {
        return this.columns.map(c => ({ label: c.label, value: c.field }));
    }

    get sortDirectionIcon() {
        return this.sortDirection === 'ASC' ? 'utility:arrowup' : 'utility:arrowdown';
    }

    get sortDirectionLabel() {
        return this.sortDirection === 'ASC' ? 'Ascending' : 'Descending';
    }

    get columnHeaders() {
        const col0Width = this.columns.length > 0 ? (this.columns[0].width || 150) : 150;
        const col2Left = 80 + col0Width;
        return this.columns.map((col, idx) => {
            let thClass = 'tracker-th';
            let thStyle = 'width:' + (col.width || 150) + 'px; min-width:' + (col.width || 150) + 'px;';
            if (idx === 0) {
                thClass += ' frozen-col-header-1';
            } else if (idx === 1) {
                thClass += ' frozen-col-header-2';
                thStyle += ' left:' + col2Left + 'px;';
            }
            return { field: col.field, label: col.label, thStyle, thClass };
        });
    }

    get hasViews() {
        return this.views.length > 0;
    }

    // Load object info for picklist values
    @wire(getObjectInfo, { objectApiName: OPPORTUNITY_OBJECT })
    wiredObjectInfo({ data, error }) {
        if (data) {
            this.objectInfo = data;
        }
    }

    // Load views on init
    connectedCallback() {
        this.initializeData();
        window.addEventListener('beforeunload', this.handleBeforeUnload);
    }

    async initializeData() {
        // Load picklists and users first, then views (which trigger grid render)
        await Promise.all([
            this.loadPicklistValues(),
            this.loadOwnerOptions(),
            this.loadContactRoleOptions(),
            this.loadAgreementPicklists(),
            this.loadCampaignOptions()
        ]);
        await this.loadViews();
    }

    async loadCampaignOptions() {
        try {
            const campaigns = await getActiveCampaignsForFilter();
            this.campaignOptions = [
                { label: 'All Campaigns', value: '' },
                ...campaigns.map(c => ({ label: c.Name, value: c.Id }))
            ];
        } catch (e) {
            this.campaignOptions = [{ label: 'All Campaigns', value: '' }];
        }
    }

    async handleCampaignChange(event) {
        this.selectedCampaign = event.detail.value;
        await this.reloadWithFilters();
    }

    disconnectedCallback() {
        window.removeEventListener('beforeunload', this.handleBeforeUnload);
    }

    handleBeforeUnload = (e) => {
        if (this.hasUnsavedChanges) {
            e.preventDefault();
            e.returnValue = '';
        }
    }

    get dateRangeOptions() {
        return [
            { label: 'All Dates', value: '' },
            { label: 'Next 7 Days', value: 'NEXT_7_DAYS' },
            { label: 'Next 30 Days', value: 'NEXT_30_DAYS' },
            { label: 'Next 60 Days', value: 'NEXT_60_DAYS' },
            { label: 'Next 90 Days', value: 'NEXT_90_DAYS' },
            { label: 'Past Due', value: 'PAST_DUE' },
        ];
    }

    async handleDateRangeChange(event) {
        this.selectedDateRange = event.detail.value;
        await this.reloadWithFilters();
    }

    // Stages relevant to each app context
    static MDU_STAGES = [
        'Closed Lost', 'On Hold', 'Prospects', 'Prospecting', 'Engaged',
        'Proposal Sent', 'Contract Negotiations', 'PAL/ROE Complete',
        'Marketing/Bulk In Progress', 'Marketing/Bulk Complete'
    ];

    // Stage transitions that require a dependent reason field
    // Validation rules block save unless the reason is set
    static STAGE_REASON_MAP = {
        'On Hold':     { field: 'Hold_Reason__c',   label: 'Hold Reason' },
        'Prospecting': { field: 'Sales_Status__c',  label: 'Sales Status' },
        'Closed Lost': { field: 'Loss_Reason__c',   label: 'Loss Reason' }
    };

    async loadPicklistValues() {
        try {
            const result = await getPicklistValuesApex({ objectName: 'Opportunity' });
            // Convert Apex PicklistOption objects to plain {label, value} for lightning-combobox
            const cache = {};
            for (const fieldName of Object.keys(result)) {
                cache[fieldName] = result[fieldName].map(opt => ({
                    label: opt.label,
                    value: opt.value
                }));
            }

            // Filter stages based on app context
            if (this.appContext === 'MDU_Sales' && cache['StageName']) {
                cache['StageName'] = cache['StageName'].filter(
                    opt => TrackerGrid.MDU_STAGES.includes(opt.value)
                );
            }

            this.picklistOptionsCache = cache;
        } catch (error) {
            this.picklistOptionsCache = {};
        }
    }

    async loadAgreementPicklists() {
        try {
            const result = await getAgreementPicklists();
            this.agreementTypeOptions = (result['Agreement_Type__c'] || []).map(o => ({ label: o.label, value: o.value }));
            this.agreementStatusOptions = (result['Status__c'] || []).map(o => ({ label: o.label, value: o.value }));
        } catch (error) {
            this.agreementTypeOptions = [];
            this.agreementStatusOptions = [];
        }
    }

    async loadContactRoleOptions() {
        try {
            const result = await getContactRoleOptions();
            this.contactRoleOptions = [{ label: '-- Select Role --', value: '' }].concat(
                result.map(opt => ({ label: opt.label, value: opt.value }))
            );
        } catch (error) {
            this.contactRoleOptions = [];
        }
    }

    async loadOwnerOptions() {
        try {
            this.userOptions = await getActiveUsers();
        } catch (error) {
            this.userOptions = [];
        }
    }

    async loadViews() {
        try {
            this.isLoading = true;
            const views = this.appContext
                ? await getActiveViewsForApp({ appContext: this.appContext })
                : await getActiveViews();
            this.views = views;
            if (views.length > 0) {
                this.selectedViewId = views[0].Id;
                await this.loadViewData();
            }
        } catch (error) {
            this.showToast('Error', 'Failed to load views: ' + this.reduceError(error), 'error');
        } finally {
            this.isLoading = false;
        }
    }

    handleViewChange(event) {
        if (this.hasUnsavedChanges) {
            if (!confirm('You have unsaved changes. Switch views anyway?')) {
                return;
            }
        }
        this.selectedViewId = event.detail.value;
        this.dirtyRecords = new Map();
        this.editingCell = null;
        this.filterField = '';
        this.filterValue = '';
        this.selectedOwner = '';
        this.selectedDateRange = '';
        this.selectedCampaign = '';
        this.selectedREAssigned = '';
        this.selectedUnitGroup = '';
        this.loadViewData();
    }

    async loadViewData() {
        if (!this.selectedViewId) return;
        try {
            this.isLoading = true;
            this.currentOffset = 0;

            // Load data and summary in parallel
            const [result, summary] = await Promise.all([
                getTrackerData({ viewId: this.selectedViewId }),
                getTrackerSummary({ viewId: this.selectedViewId })
            ]);

            const config = JSON.parse(result.viewConfig.Config__c);

            this.columns = config.columns || [];
            this.formattingRules = config.formatting_rules || [];
            this.sortField = config.sort ? config.sort.field : '';
            this.sortDirection = config.sort ? config.sort.direction : 'ASC';

            this.records = result.records.map(rec => this.flattenRecord(rec));
            this.totalRecordCount = result.totalCount || this.records.length;
            this.hasMoreRecords = result.hasMore || false;
            this.currentOffset = this.records.length;
            this.serverSummary = summary;

            this.buildOwnerOptions();
            this.buildREAssignedOptions();
            this.applyDisplayRows();
        } catch (error) {
            this.showToast('Error', 'Failed to load data: ' + this.reduceError(error), 'error');
        } finally {
            this.isLoading = false;
        }
    }

    async reloadFromServer() {
        if (!this.selectedViewId) return;
        try {
            this.isLoading = true;
            this.currentOffset = 0;

            const result = await getTrackerDataFullWithCampaign({
                viewId: this.selectedViewId,
                recordOffset: 0,
                ownerName: this.selectedOwner || null,
                dateRange: this.selectedDateRange || null,
                reAssignedName: this.selectedREAssigned || null,
                userSortField: this.sortField || null,
                userSortDir: this.sortDirection || null,
                filterField: this.filterField || null,
                filterValue: this.filterValue || null,
                campaignId: this.selectedCampaign || null,
                hideClosed: this.hideClosed
            });

            this.records = result.records.map(rec => this.flattenRecord(rec));
            this.totalRecordCount = result.totalCount || this.records.length;
            this.hasMoreRecords = result.hasMore || false;
            this.currentOffset = this.records.length;

            this.buildOwnerOptions();
            this.buildREAssignedOptions();
            this.applyDisplayRows();
        } catch (error) {
            this.showToast('Error', 'Failed to reload: ' + this.reduceError(error), 'error');
        } finally {
            this.isLoading = false;
        }
    }

    async handleLoadMore() {
        if (!this.hasMoreRecords || this.isLoadingMore) return;
        try {
            this.isLoadingMore = true;
            const result = await getTrackerDataFullWithCampaign({
                viewId: this.selectedViewId,
                recordOffset: this.currentOffset,
                ownerName: this.selectedOwner || null,
                dateRange: this.selectedDateRange || null,
                reAssignedName: this.selectedREAssigned || null,
                userSortField: this.sortField || null,
                userSortDir: this.sortDirection || null,
                filterField: this.filterField || null,
                filterValue: this.filterValue || null,
                campaignId: this.selectedCampaign || null,
                hideClosed: this.hideClosed
            });

            const newRecords = result.records.map(rec => this.flattenRecord(rec));
            this.records = [...this.records, ...newRecords];
            this.currentOffset += newRecords.length;
            this.hasMoreRecords = result.hasMore || false;

            this.buildOwnerOptions();
            this.buildREAssignedOptions();
            this.applyDisplayRows();
        } catch (error) {
            this.showToast('Error', 'Failed to load more: ' + this.reduceError(error), 'error');
        } finally {
            this.isLoadingMore = false;
        }
    }

    // Flatten relationship fields (Account.Name -> Account_Name for display key)
    flattenRecord(record) {
        const flat = { Id: record.Id, _agreements: [], _openTasks: [], _upcomingEvents: [], _original: {} };

        // Copy direct fields
        for (const key of Object.keys(record)) {
            if (key === 'Agreements__r') {
                flat._agreements = record[key] || [];
            } else if (key === 'SiteTracker_Projects__r') {
                // Extract Build Status from the first (should be only) related ST project
                const stProjects = record[key] || [];
                if (stProjects.length > 0) {
                    flat['ST_Build_Status'] = stProjects[0].Build_Status__c || '';
                    flat['ST_Site_Status'] = stProjects[0].Site_Status__c || '';
                } else {
                    flat['ST_Build_Status'] = '';
                    flat['ST_Site_Status'] = '';
                }
            } else if (key === 'Tasks') {
                flat._openTasks = record[key] || [];
            } else if (key === 'Events') {
                flat._upcomingEvents = record[key] || [];
            } else if (typeof record[key] === 'object' && record[key] !== null && key !== 'attributes') {
                // Relationship object — flatten its fields, recurse for nested relationships
                this.flattenRelationship(flat, key, record[key]);
            } else if (key !== 'attributes') {
                flat[key] = record[key];
            }
        }

        // Store original values for dirty detection
        flat._original = { ...flat };
        delete flat._original._original;
        delete flat._original._agreements;
        delete flat._original._openTasks;
        delete flat._original._upcomingEvents;

        return flat;
    }

    flattenRelationship(flat, prefix, obj) {
        for (const key of Object.keys(obj)) {
            if (key === 'attributes') continue;
            const val = obj[key];
            if (typeof val === 'object' && val !== null) {
                // Recurse deeper (e.g., Property_Unit__r.Property_Location__r.City__c)
                this.flattenRelationship(flat, prefix + '.' + key, val);
            } else {
                flat[prefix + '.' + key] = val;
            }
        }
    }

    buildOwnerOptions() {
        // Build from loaded records — shows only owners who actually have MDU deals
        const owners = new Map();
        for (const rec of this.records) {
            const ownerName = rec['Owner.Name'];
            if (ownerName && !owners.has(ownerName)) {
                owners.set(ownerName, ownerName);
            }
        }
        // Always include MDU team members even if their records aren't in the current page
        const mduTeam = ['Bill Holick', 'Brett Spivey', 'Chuck McNeely', 'Melissa Baker', 'Taylor Mauney',
                         'Jeff Chao', 'Marty Samuels', 'Jeff Wickersham', 'Tanya Friese',
                         'Rosemarie Shortino', 'Justin Barry', 'Pankaj Gulati'];
        for (const name of mduTeam) {
            if (!owners.has(name)) {
                owners.set(name, name);
            }
        }
        const opts = [{ label: 'All Owners', value: '' }];
        const sorted = [...owners.keys()].sort();
        for (const name of sorted) {
            opts.push({ label: name, value: name });
        }
        this.ownerOptions = opts;
    }

    buildREAssignedOptions() {
        const reNames = new Set();
        for (const rec of this.records) {
            const name = rec['RE_Assigned__r.Name'];
            if (name) reNames.add(name);
        }
        // Always include known RE team
        const reTeam = ['Justin Barry', 'Rosemarie Shortino', 'Tanya Friese'];
        for (const name of reTeam) reNames.add(name);

        const opts = [{ label: 'All RE', value: '' }];
        for (const name of [...reNames].sort()) {
            opts.push({ label: name, value: name });
        }
        this.reAssignedOptions = opts;
    }

    async handleREAssignedChange(event) {
        this.selectedREAssigned = event.detail.value;
        await this.reloadWithFilters();
    }

    // Size bands from the Unit_Group__c formula. Listed by size deliberately:
    // sorted alphabetically these read 25-49, 50-100, < 25, > 100.
    get unitGroupOptions() {
        return [
            { label: 'All Sizes', value: '' },
            { label: '< 25 units', value: '< 25' },
            { label: '25-49 units', value: '25-49' },
            { label: '50-100 units', value: '50-100' },
            { label: '> 100 units', value: '> 100' }
        ];
    }
    async handleUnitGroupChange(event) {
        this.selectedUnitGroup = event.detail.value;
        // Drives the shared text filter so the match runs server-side across the
        // whole dataset rather than only the loaded page. The four band labels are
        // substring-unique, so the Apex LIKE '%band%' cannot cross-match them.
        if (this.selectedUnitGroup) {
            this.filterField = 'Unit_Group__c';
            this.filterValue = this.selectedUnitGroup;
        } else if (this.filterField === 'Unit_Group__c') {
            this.filterField = '';
            this.filterValue = '';
        }
        await this.reloadFromServer();
    }

    async handleOwnerChange(event) {
        this.selectedOwner = event.detail.value;
        await this.reloadWithFilters();
    }

    async handleHideClosedChange(event) {
        this.hideClosed = event.target.checked;
        await this.reloadWithFilters();
    }

    async reloadWithFilters() {
        if (!this.selectedViewId) return;
        try {
            this.isLoading = true;
            this.currentOffset = 0;
            const ownerParam = this.selectedOwner || null;
            const dateParam = this.selectedDateRange || null;
            const reParam = this.selectedREAssigned || null;
            const campaignParam = this.selectedCampaign || null;

            const [result, summary] = await Promise.all([
                getTrackerDataFullWithCampaign({ viewId: this.selectedViewId, recordOffset: 0, ownerName: ownerParam, dateRange: dateParam, reAssignedName: reParam, userSortField: this.sortField || null, userSortDir: this.sortDirection || null, filterField: this.filterField || null, filterValue: this.filterValue || null, campaignId: campaignParam, hideClosed: this.hideClosed }),
                getTrackerSummaryFilteredWithCampaign({ viewId: this.selectedViewId, ownerName: ownerParam, dateRange: dateParam, reAssignedName: reParam, campaignId: campaignParam, hideClosed: this.hideClosed })
            ]);

            const config = JSON.parse(result.viewConfig.Config__c);
            this.columns = config.columns || [];
            this.formattingRules = config.formatting_rules || [];

            this.records = result.records.map(rec => this.flattenRecord(rec));
            this.totalRecordCount = result.totalCount || this.records.length;
            this.hasMoreRecords = result.hasMore || false;
            this.currentOffset = this.records.length;
            this.serverSummary = summary;

            this.applyDisplayRows();
        } catch (error) {
            this.showToast('Error', 'Failed to load data: ' + this.reduceError(error), 'error');
        } finally {
            this.isLoading = false;
        }
    }

    applyDisplayRows() {
        let rows = [...this.records];

        // Owner filter is now server-side (handleOwnerChange reloads data)

        // Client-side filter. Comma/semicolon separated values are OR-matched (e.g. "TX,NE").
        if (this.filterField && this.filterValue) {
            const terms = this.filterValue.toLowerCase().split(/[,;]/).map(t => t.trim()).filter(Boolean);
            if (terms.length) {
                rows = rows.filter(r => {
                    const val = r[this.filterField];
                    if (val == null) return false;
                    const s = String(val).toLowerCase();
                    return terms.some(t => s.includes(t));
                });
            }
        }

        // Client-side sort
        if (this.sortField) {
            const dir = this.sortDirection === 'ASC' ? 1 : -1;
            rows.sort((a, b) => {
                let va = a[this.sortField];
                let vb = b[this.sortField];
                if (va == null) return 1;
                if (vb == null) return -1;
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
                return va < vb ? -dir : va > vb ? dir : 0;
            });
        }

        // Build display rows with formatting
        this.displayRows = rows.map(row => {
            const rowFormatting = this.getRowFormatting(row);
            const cells = this.columns.map((col, colIdx) => {
                const value = row[col.field];
                const isDirty = this.dirtyRecords.has(row.Id) &&
                    this.dirtyRecords.get(row.Id).hasOwnProperty(col.field);
                const isEditing = this.editingCell &&
                    this.editingCell.recordId === row.Id &&
                    this.editingCell.field === col.field;
                const cellFormatting = this.getCellFormatting(row, col.field);

                const fieldType = this.getFieldType(col);
                const isEditable = col.editable !== false && !col.field.includes('.');
                const col0Width = this.columns.length > 0 ? (this.columns[0].width || 150) : 150;
                let tdClass = 'tracker-td';
                if (colIdx === 0) tdClass += ' frozen-col-1';
                else if (colIdx === 1) tdClass += ' frozen-col-2';
                if (isDirty) tdClass += ' dirty-cell';
                tdClass += isEditable ? ' editable-cell' : ' readonly-cell';

                const isLink = col.field === 'Name';
                const isOwner = col.field === 'Owner.Name';
                const isCheckbox = fieldType === 'checkbox';
                const isDate = fieldType === 'date';
                const isNumber = fieldType === 'currency' || fieldType === 'number';
                const isPicklist = fieldType === 'picklist';
                const isText = !isCheckbox && !isDate && !isNumber && !isPicklist && !isOwner;

                // Get picklist options for this field, with selected flag
                let picklistOpts = [];
                if (isPicklist) {
                    const rawOpts = this.picklistOptionsCache[col.field] || [];
                    picklistOpts = rawOpts.map(opt => ({
                        label: opt.label,
                        value: opt.value,
                        selected: opt.value === value
                    }));
                } else if (isOwner) {
                    const rawOpts = this.userOptions || [];
                    const ownerId = row['OwnerId'] || '';
                    picklistOpts = rawOpts.map(opt => ({
                        label: opt.label,
                        value: opt.value,
                        selected: opt.value === ownerId
                    }));
                }

                // Frozen col 2 needs dynamic left based on col 0 width
                let cellStyle = cellFormatting || rowFormatting || '';
                if (colIdx === 1) {
                    const frozenLeft = 80 + col0Width;
                    cellStyle = 'left:' + frozenLeft + 'px;' + (cellStyle ? ' ' + cellStyle : '');
                }

                return {
                    key: row.Id + '-' + col.field,
                    field: col.field,
                    value: this.formatDisplayValue(value, col),
                    rawValue: value,
                    label: col.label,
                    editable: (isEditable || isOwner) && !isLink,
                    isEditing: isEditing,
                    isDirty: isDirty,
                    width: col.width || 150,
                    style: cellStyle,
                    tdClass: isOwner ? tdClass.replace('readonly-cell', 'editable-cell') : tdClass,
                    isCheckbox: isCheckbox,
                    isDate: isDate,
                    isNumber: isNumber,
                    isPicklist: isPicklist || isOwner,
                    isText: isText && !isLink,
                    isLink: isLink,
                    isOwner: isOwner,
                    picklistOptions: picklistOpts
                };
            });

            // Agreement badges
            const agreements = (row._agreements || []).map(a => ({
                key: a.Id,
                label: (a.Agreement_Type__c || '?') + ': ' + (a.Status__c || '?'),
                cssClass: 'agreement-badge badge-' + (a.Status__c || 'unknown').toLowerCase().replace(/\s+/g, '-')
            }));

            const notesCount = row['Notes_Count__c'] || 0;
            const agrCount = (row._agreements || []).length;
            const openTasks = row._openTasks || [];
            const upcomingEvents = row._upcomingEvents || [];
            const openActivityCount = openTasks.length + upcomingEvents.length;

            // Build activity summary badges
            const activityBadges = [];
            for (const t of openTasks) {
                const subtype = t.TaskSubtype || 'Task';
                activityBadges.push({
                    key: t.Id,
                    label: subtype + ': ' + (t.Subject || '(No Subject)'),
                    cssClass: 'activity-grid-badge badge-task'
                });
            }
            for (const e of upcomingEvents) {
                activityBadges.push({
                    key: e.Id,
                    label: 'Event: ' + (e.Subject || '(No Subject)'),
                    cssClass: 'activity-grid-badge badge-event'
                });
            }

            const isActivePanel = (this.panelOpen && this.panelRecordId === row.Id) ||
                                  (this.agreementsPanelOpen && this.agreementsPanelRecordId === row.Id);

            return {
                key: row.Id,
                id: row.Id,
                cells: cells,
                agreements: agreements,
                hasAgreements: agreements.length > 0,
                activityBadges: activityBadges,
                hasActivities: activityBadges.length > 0,
                openActivityCount: openActivityCount,
                isDirty: this.dirtyRecords.has(row.Id),
                rowClass: 'tracker-row' + (this.dirtyRecords.has(row.Id) ? ' dirty-row' : '') + (isActivePanel ? ' active-panel-row' : ''),
                notesCount: notesCount,
                hasNotesCount: notesCount > 0,
                notesIconClass: 'notes-icon' + ((this.panelOpen && this.panelRecordId === row.Id) ? ' notes-icon-active' : ''),
                agrCount: agrCount,
                hasAgrCount: agrCount > 0,
                agrIconClass: 'notes-icon' + ((this.agreementsPanelOpen && this.agreementsPanelRecordId === row.Id) ? ' notes-icon-active' : '')
            };
        });
    }

    getFieldType(col) {
        // Check picklist cache first (from Apex describe)
        if (this.picklistOptionsCache && this.picklistOptionsCache[col.field]) {
            return 'picklist';
        }
        // Fall back to objectInfo wire
        if (!this.objectInfo || !this.objectInfo.fields) return 'text';
        const fieldInfo = this.objectInfo.fields[col.field];
        if (!fieldInfo) return 'text';
        const dt = fieldInfo.dataType;
        if (dt === 'Currency') return 'currency';
        if (dt === 'Double' || dt === 'Int' || dt === 'Percent') return 'number';
        if (dt === 'Date') return 'date';
        if (dt === 'DateTime') return 'datetime';
        if (dt === 'Boolean') return 'checkbox';
        if (dt === 'Picklist') return 'picklist';
        return 'text';
    }

    formatDisplayValue(value, col) {
        if (value == null || value === '') return '';
        const fieldType = this.getFieldType(col);
        if (fieldType === 'currency') {
            return '$' + Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        if (fieldType === 'checkbox') {
            return value ? '✓' : '';
        }
        return String(value);
    }

    getRowFormatting(row) {
        for (const rule of this.formattingRules) {
            if (rule.target === 'row' && this.evaluateRule(rule, row)) {
                return rule.style;
            }
        }
        return '';
    }

    getCellFormatting(row, field) {
        for (const rule of this.formattingRules) {
            if (rule.field === field && rule.target !== 'row' && this.evaluateRule(rule, row)) {
                return rule.style;
            }
        }
        return '';
    }

    evaluateRule(rule, row) {
        const val = row[rule.field];
        const ruleVal = rule.value;

        switch (rule.operator) {
            case 'equals':
                return String(val) === String(ruleVal);
            case 'not_equals':
                return String(val) !== String(ruleVal);
            case 'less_than':
                if (ruleVal === 'TODAY') {
                    return val != null && new Date(val) < new Date();
                }
                return val < ruleVal;
            case 'greater_than':
                if (ruleVal === 'TODAY') {
                    return val != null && new Date(val) > new Date();
                }
                return val > ruleVal;
            case 'contains':
                return val != null && String(val).toLowerCase().includes(String(ruleVal).toLowerCase());
            case 'in_list':
                return Array.isArray(ruleVal) && ruleVal.includes(val);
            default:
                return false;
        }
    }

    // --- Record navigation ---

    handleRecordClick(event) {
        event.stopPropagation();
        const recordId = event.currentTarget.dataset.recordId;
        this[NavigationMixin.GenerateUrl]({
            type: 'standard__recordPage',
            attributes: {
                recordId: recordId,
                objectApiName: 'Opportunity',
                actionName: 'view'
            }
        }).then(url => {
            window.open(url, '_blank');
        });
    }

    // --- Cell editing ---

    handleContainerClick(event) {
        // Close combobox editing when clicking outside any editable cell
        if (!this.editingCell) return;
        const clickedCell = event.target.closest('[data-field]');
        if (!clickedCell) {
            this.editingCell = null;
            this.applyDisplayRows();
        }
    }

    handleCellClick(event) {
        event.stopPropagation();
        const recordId = event.currentTarget.dataset.recordId;
        const field = event.currentTarget.dataset.field;
        const editable = event.currentTarget.dataset.editable === 'true';

        if (!editable) return;

        this.editingCell = { recordId, field };
        this.applyDisplayRows();

        // Focus the input after render
        // eslint-disable-next-line @lwc/lwc/no-async-operation
        setTimeout(() => {
            const editId = `${recordId}-${field}`;
            let input = this.template.querySelector(`[data-edit-id="${editId}"]`);
            if (input) {
                input.focus();
                if (input.select) input.select();
            }
        }, 50);
    }

    handleSelectChange(event) {
        // Native <select> change handler — delegates to shared logic
        const recordId = event.currentTarget.dataset.recordId;
        const field = event.currentTarget.dataset.field;
        const isOwner = event.currentTarget.dataset.isOwner === 'true';
        const value = event.currentTarget.value;
        this._applyFieldChange(recordId, field, isOwner, value);
    }

    handleCellChange(event) {
        const recordId = event.currentTarget.dataset.recordId;
        const field = event.currentTarget.dataset.field;
        const isOwner = event.currentTarget.dataset.isOwner === 'true';
        let value = event.currentTarget.type === 'checkbox'
            ? event.currentTarget.checked
            : (event.detail ? event.detail.value : event.currentTarget.value);
        this._applyFieldChange(recordId, field, isOwner, value);
    }

    _applyFieldChange(recordId, field, isOwner, value) {

        const record = this.records.find(r => r.Id === recordId);
        if (!record) return;

        if (isOwner) {
            // Owner field: save OwnerId, update display name
            const saveField = 'OwnerId';
            const selectedUser = (this.userOptions || []).find(u => u.value === value);
            record['Owner.Name'] = selectedUser ? selectedUser.label : '';
            record['OwnerId'] = value;

            if (value !== record._original['OwnerId']) {
                if (!this.dirtyRecords.has(recordId)) {
                    this.dirtyRecords.set(recordId, {});
                }
                this.dirtyRecords.get(recordId)[saveField] = value;
            } else {
                if (this.dirtyRecords.has(recordId)) {
                    delete this.dirtyRecords.get(recordId)[saveField];
                    if (Object.keys(this.dirtyRecords.get(recordId)).length === 0) {
                        this.dirtyRecords.delete(recordId);
                    }
                }
            }
        } else {
            // Standard field
            if (value !== record._original[field]) {
                if (!this.dirtyRecords.has(recordId)) {
                    this.dirtyRecords.set(recordId, {});
                }
                this.dirtyRecords.get(recordId)[field] = value;
            } else {
                if (this.dirtyRecords.has(recordId)) {
                    delete this.dirtyRecords.get(recordId)[field];
                    if (Object.keys(this.dirtyRecords.get(recordId)).length === 0) {
                        this.dirtyRecords.delete(recordId);
                    }
                }
            }
            record[field] = value;
        }

        // Close editing and refresh display
        this.editingCell = null;
        this.applyDisplayRows();

        // If stage changed to a value that requires a dependent reason, prompt for it
        if (!isOwner && field === 'StageName') {
            const reasonMeta = TrackerGrid.STAGE_REASON_MAP[value];
            if (reasonMeta && !record[reasonMeta.field]) {
                this.openStageReasonModal(record, value, reasonMeta);
            }
        }
    }

    openStageReasonModal(record, newStage, reasonMeta) {
        const options = (this.picklistOptionsCache && this.picklistOptionsCache[reasonMeta.field]) || [];
        this.stageReasonModalRecordId = record.Id;
        this.stageReasonModalRecordName = record.Name || '';
        this.stageReasonModalStage = newStage;
        this.stageReasonModalField = reasonMeta.field;
        this.stageReasonModalLabel = reasonMeta.label;
        this.stageReasonModalValue = '';
        this.stageReasonModalOptions = options;
        this.stageReasonModalOriginalStage = record._original ? record._original.StageName : '';
        this.stageReasonModalOpen = true;
    }

    handleStageReasonChange(event) {
        this.stageReasonModalValue = event.detail ? event.detail.value : event.target.value;
    }

    handleStageReasonSave() {
        if (!this.stageReasonModalValue) {
            this.showToast('Required', this.stageReasonModalLabel + ' is required.', 'warning');
            return;
        }
        const recordId = this.stageReasonModalRecordId;
        const field = this.stageReasonModalField;
        const value = this.stageReasonModalValue;
        const record = this.records.find(r => r.Id === recordId);
        if (record) {
            record[field] = value;
            if (!this.dirtyRecords.has(recordId)) {
                this.dirtyRecords.set(recordId, {});
            }
            this.dirtyRecords.get(recordId)[field] = value;
        }
        this.closeStageReasonModal();
        this.applyDisplayRows();
    }

    handleStageReasonCancel() {
        // Revert the stage change since user bailed on providing the reason
        const recordId = this.stageReasonModalRecordId;
        const originalStage = this.stageReasonModalOriginalStage;
        const record = this.records.find(r => r.Id === recordId);
        if (record) {
            record.StageName = originalStage;
            if (this.dirtyRecords.has(recordId)) {
                delete this.dirtyRecords.get(recordId).StageName;
                if (Object.keys(this.dirtyRecords.get(recordId)).length === 0) {
                    this.dirtyRecords.delete(recordId);
                }
            }
        }
        this.closeStageReasonModal();
        this.applyDisplayRows();
    }

    closeStageReasonModal() {
        this.stageReasonModalOpen = false;
        this.stageReasonModalRecordId = '';
        this.stageReasonModalRecordName = '';
        this.stageReasonModalStage = '';
        this.stageReasonModalField = '';
        this.stageReasonModalLabel = '';
        this.stageReasonModalValue = '';
        this.stageReasonModalOptions = [];
        this.stageReasonModalOriginalStage = '';
    }

    handleCellBlur(event) {
        const recordId = event.currentTarget.dataset.recordId;
        const field = event.currentTarget.dataset.field;

        // Delay blur to allow combobox dropdown clicks to register
        // eslint-disable-next-line @lwc/lwc/no-async-operation
        setTimeout(() => {
            if (this.editingCell && this.editingCell.recordId === recordId && this.editingCell.field === field) {
                this.editingCell = null;
                this.applyDisplayRows();
            }
        }, 200);
    }

    handleCellKeydown(event) {
        if (event.key === 'Tab' || event.key === 'Enter') {
            event.preventDefault();
            // Commit current and move to next editable cell
            this.handleCellBlur(event);

            if (event.key === 'Tab') {
                this.moveToNextCell(
                    event.currentTarget.dataset.recordId,
                    event.currentTarget.dataset.field,
                    event.shiftKey ? -1 : 1
                );
            }
        } else if (event.key === 'Escape') {
            // Revert changes to this cell
            const recordId = event.currentTarget.dataset.recordId;
            const field = event.currentTarget.dataset.field;
            const record = this.records.find(r => r.Id === recordId);
            if (record) {
                record[field] = record._original[field];
                if (this.dirtyRecords.has(recordId)) {
                    delete this.dirtyRecords.get(recordId)[field];
                    if (Object.keys(this.dirtyRecords.get(recordId)).length === 0) {
                        this.dirtyRecords.delete(recordId);
                    }
                }
            }
            this.editingCell = null;
            this.applyDisplayRows();
        }
    }

    moveToNextCell(currentRecordId, currentField, direction) {
        const editableColumns = this.columns.filter(c => c.editable !== false && !c.field.includes('.'));
        const currentColIdx = editableColumns.findIndex(c => c.field === currentField);
        const currentRowIdx = this.displayRows.findIndex(r => r.id === currentRecordId);

        let nextColIdx = currentColIdx + direction;
        let nextRowIdx = currentRowIdx;

        if (nextColIdx >= editableColumns.length) {
            nextColIdx = 0;
            nextRowIdx++;
        } else if (nextColIdx < 0) {
            nextColIdx = editableColumns.length - 1;
            nextRowIdx--;
        }

        if (nextRowIdx >= 0 && nextRowIdx < this.displayRows.length) {
            const nextRecordId = this.displayRows[nextRowIdx].id;
            const nextField = editableColumns[nextColIdx].field;
            this.editingCell = { recordId: nextRecordId, field: nextField };
            this.applyDisplayRows();

            // eslint-disable-next-line @lwc/lwc/no-async-operation
            setTimeout(() => {
                const input = this.template.querySelector(`[data-edit-id="${nextRecordId}-${nextField}"]`);
                if (input) {
                    input.focus();
                    if (input.select) input.select();
                }
            }, 50);
        }
    }

    // --- Column sorting ---

    handleColumnSort(event) {
        const field = event.currentTarget.dataset.field;
        if (this.sortField === field) {
            this.sortDirection = this.sortDirection === 'ASC' ? 'DESC' : 'ASC';
        } else {
            this.sortField = field;
            this.sortDirection = 'ASC';
        }
        this.applyDisplayRows();
    }

    handleSortFieldChange(event) {
        this.sortField = event.detail.value;
        this.reloadFromServer();
    }

    handleSortDirectionToggle() {
        this.sortDirection = this.sortDirection === 'ASC' ? 'DESC' : 'ASC';
        this.reloadFromServer();
    }

    // --- Filtering ---

    handleFilterFieldChange(event) {
        this.filterField = event.detail.value;
        // Keep the Unit Group combobox honest if the user redirects the shared
        // text filter at a different column.
        if (this.filterField !== 'Unit_Group__c') {
            this.selectedUnitGroup = '';
        }
        if (this.filterValue) {
            this.reloadFromServer();
        }
    }

    handleFilterValueChange(event) {
        this.filterValue = event.target.value;
        if (this.selectedUnitGroup && this.filterValue !== this.selectedUnitGroup) {
            this.selectedUnitGroup = '';
        }
        // Debounce: reload after user stops typing
        clearTimeout(this._filterDebounce);
        this._filterDebounce = setTimeout(() => {
            this.reloadFromServer();
        }, 400);
    }

    get filterableColumns() {
        return this.columns.map(c => ({ label: c.label, value: c.field }));
    }

    // --- Save ---

    async handleSave() {
        if (!this.hasUnsavedChanges) return;

        this.isSaving = true;
        try {
            // Build SObject records for update
            const recordsToSave = [];
            for (const [recordId, fields] of this.dirtyRecords) {
                const rec = { Id: recordId, ...fields };
                recordsToSave.push(rec);
            }

            const results = await saveRecords({ records: recordsToSave });

            let successCount = 0;
            let errors = [];
            results.forEach((result, idx) => {
                if (result.success) {
                    successCount++;
                    const recordId = recordsToSave[idx].Id;
                    const record = this.records.find(r => r.Id === recordId);
                    if (record) {
                        record._original = { ...record };
                        delete record._original._original;
                        delete record._original._agreements;
                        delete record._original._openTasks;
                        delete record._original._upcomingEvents;
                    }
                    this.dirtyRecords.delete(recordId);
                } else {
                    errors.push(result.errors.join(', '));
                }
            });

            if (errors.length > 0) {
                this.showToast('Save Errors', errors.join('\n'), 'error');
            }
            if (successCount > 0) {
                this.showToast('Saved', successCount + ' record(s) updated successfully.', 'success');
            }

            this.applyDisplayRows();
        } catch (error) {
            this.showToast('Error', 'Save failed: ' + this.reduceError(error), 'error');
        } finally {
            this.isSaving = false;
        }
    }

    handleDiscard() {
        if (!this.hasUnsavedChanges) return;
        if (!confirm('Discard all unsaved changes?')) return;

        // Revert all dirty records to originals
        for (const [recordId] of this.dirtyRecords) {
            const record = this.records.find(r => r.Id === recordId);
            if (record) {
                for (const key of Object.keys(record._original)) {
                    record[key] = record._original[key];
                }
            }
        }
        this.dirtyRecords = new Map();
        this.editingCell = null;
        this.applyDisplayRows();
    }

    handleRefresh() {
        if (this.hasUnsavedChanges) {
            if (!confirm('You have unsaved changes. Refresh anyway?')) {
                return;
            }
        }
        this.dirtyRecords = new Map();
        this.editingCell = null;
        this.loadViewData();
    }

    // --- Export ---

    handleExport() {
        if (!this.displayRows || this.displayRows.length === 0) {
            this.showToast('Info', 'No data to export.', 'info');
            return;
        }

        const cols = this.columns;
        // Build header row
        const headers = cols.map(c => c.label);
        headers.push('Open Activities', 'Agreements');

        const rows = this.displayRows.map(row => {
            const values = row.cells.map(cell => {
                let val = cell.value != null ? String(cell.value) : '';
                // Escape quotes and wrap in quotes if contains comma, quote, or newline
                if (val.includes('"') || val.includes(',') || val.includes('\n')) {
                    val = '"' + val.replace(/"/g, '""') + '"';
                }
                return val;
            });

            // Open Activities summary
            const activities = (row.activityBadges || []).map(a => a.label).join('; ');
            values.push(activities.includes(',') || activities.includes('"') ? '"' + activities.replace(/"/g, '""') + '"' : activities);

            // Agreements summary
            const agreements = (row.agreements || []).map(a => a.label).join('; ');
            values.push(agreements.includes(',') || agreements.includes('"') ? '"' + agreements.replace(/"/g, '""') + '"' : agreements);

            return values.join(',');
        });

        // Add BOM for Excel UTF-8 compatibility
        const csvContent = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n');
        const viewName = (this.viewOptions.find(v => v.value === this.selectedViewId) || {}).label || 'Export';
        const date = new Date().toISOString().slice(0, 10);
        const filename = viewName.replace(/\s+/g, '_') + '_' + date + '.csv';

        // Navigate to data URI — works within Locker Service
        const encodedCsv = encodeURIComponent(csvContent);
        const dataUri = 'data:text/csv;charset=utf-8,' + encodedCsv;

        // Use NavigationMixin to open the download
        this[NavigationMixin.Navigate]({
            type: 'standard__webPage',
            attributes: {
                url: dataUri
            }
        });
    }

    // --- Side panel ---

    get isNotesTab() {
        return this.panelTab === 'notes';
    }

    get isContactsTab() {
        return this.panelTab === 'contacts';
    }

    get isActivitiesTab() {
        return this.panelTab === 'activities';
    }

    get notesTabClass() {
        return 'panel-tab' + (this.panelTab === 'notes' ? ' panel-tab-active' : '');
    }

    get contactsTabClass() {
        return 'panel-tab' + (this.panelTab === 'contacts' ? ' panel-tab-active' : '');
    }

    get activitiesTabClass() {
        return 'panel-tab' + (this.panelTab === 'activities' ? ' panel-tab-active' : '');
    }

    get hasNotes() {
        return this.panelNotes.length > 0;
    }

    get hasContacts() {
        return this.panelContacts.length > 0;
    }

    get canSaveNote() {
        return this.newNoteTitle.trim() && this.newNoteBody.trim() && !this.isSavingNote;
    }

    get hasActivities() {
        return this.panelActivities.length > 0;
    }

    get canAddActivity() {
        return this.newActivitySubject.trim() && !this.isAddingActivity;
    }

    get hasAgreements() {
        return this.panelAgreements.length > 0;
    }

    get canAddAgreement() {
        return this.newAgreementType && !this.isAddingAgreement;
    }

    get canAddContact() {
        return this.newContactLastName.trim() && !this.isAddingContact;
    }

    get panelContainerClass() {
        return 'tracker-layout' + ((this.panelOpen || this.agreementsPanelOpen) ? ' panel-open' : '');
    }

    handleNotesClick(event) {
        event.stopPropagation();
        const recordId = event.currentTarget.dataset.recordId;
        const row = this.records.find(r => r.Id === recordId);
        const recordName = row ? (row['Name'] || 'Record') : 'Record';

        if (this.panelOpen && this.panelRecordId === recordId) {
            this.panelOpen = false;
            this.panelRecordId = '';
            this.applyDisplayRows();
            return;
        }

        this.agreementsPanelOpen = false;
        this.panelRecordId = recordId;
        this.panelRecordName = recordName;
        this.panelOpen = true;
        this.panelTab = 'notes';
        this.newNoteTitle = '';
        this.newNoteBody = '';
        this.loadPanelData();
        this.applyDisplayRows();
    }

    handleAgreementsClick(event) {
        event.stopPropagation();
        const recordId = event.currentTarget.dataset.recordId;
        const row = this.records.find(r => r.Id === recordId);
        const recordName = row ? (row['Name'] || 'Record') : 'Record';

        if (this.agreementsPanelOpen && this.agreementsPanelRecordId === recordId) {
            this.agreementsPanelOpen = false;
            this.agreementsPanelRecordId = '';
            this.applyDisplayRows();
            return;
        }

        this.panelOpen = false;
        this.agreementsPanelRecordId = recordId;
        this.agreementsPanelRecordName = recordName;
        this.agreementsPanelOpen = true;
        this.loadAgreementsPanelData();
        this.applyDisplayRows();
    }

    async loadAgreementsPanelData() {
        this.agreementsPanelLoading = true;
        try {
            const agreements = await getAgreementsForRecord({ recordId: this.agreementsPanelRecordId });
            this.panelAgreements = agreements.map(a => this.mapAgreement(a));
        } catch (error) {
            this.showToast('Error', 'Failed to load agreements: ' + this.reduceError(error), 'error');
        } finally {
            this.agreementsPanelLoading = false;
        }
    }

    async loadPanelData() {
        this.panelLoading = true;
        this.notesOffset = 0;
        try {
            this.completedActivityOffset = 0;
            const [notes, contacts, activities] = await Promise.all([
                getNotesForRecordPaged({ recordId: this.panelRecordId, limitCount: this.notesPageSize + 1, offsetCount: 0 }),
                getContactsForRecord({ recordId: this.panelRecordId }),
                getActivitiesForRecordPaged({ recordId: this.panelRecordId, completedLimit: this.completedActivityPageSize + 1, completedOffset: 0 })
            ]);

            this.hasMoreNotes = notes.length > this.notesPageSize;
            const displayNotes = this.hasMoreNotes ? notes.slice(0, this.notesPageSize) : notes;
            this.notesOffset = displayNotes.length;
            this.panelNotes = displayNotes.map(n => ({
                ...n,
                formattedDate: this.formatDateTime(n.createdDate),
                bodyHtml: n.body ? n.body.replace(/\n/g, '<br>') : n.preview || ''
            }));

            this.panelContacts = contacts.map(c => ({
                ...c,
                displayPhone: c.phone || '',
                displayEmail: c.email || '',
                displayRole: c.role === 'Other' && c.roleDescription
                    ? 'Other - ' + c.roleDescription
                    : (c.role || '')
            }));

            const mapped = activities.map(a => this.mapActivity(a));
            const open = mapped.filter(a => !a.isCompleted);
            const completed = mapped.filter(a => a.isCompleted);
            this.hasMoreCompletedActivities = completed.length > this.completedActivityPageSize;
            const displayCompleted = this.hasMoreCompletedActivities ? completed.slice(0, this.completedActivityPageSize) : completed;
            this.completedActivityOffset = displayCompleted.length;
            this.panelActivities = [...open, ...displayCompleted];
        } catch (error) {
            this.showToast('Error', 'Failed to load panel data: ' + this.reduceError(error), 'error');
        } finally {
            this.panelLoading = false;
        }
    }

    handlePanelTabClick(event) {
        this.panelTab = event.currentTarget.dataset.tab;
    }

    handleClosePanel() {
        this.panelOpen = false;
        this.panelRecordId = '';
        this.applyDisplayRows();
    }

    handleCloseAgreementsPanel() {
        this.agreementsPanelOpen = false;
        this.agreementsPanelRecordId = '';
        this.applyDisplayRows();
    }

    handleNoteTitleChange(event) {
        this.newNoteTitle = event.target.value;
    }

    handleNoteBodyChange(event) {
        this.newNoteBody = event.target.value;
    }

    async handleSaveNote() {
        if (!this.canSaveNote) return;

        this.isSavingNote = true;
        try {
            await createNote({
                recordId: this.panelRecordId,
                title: this.newNoteTitle.trim(),
                body: this.newNoteBody.trim()
            });

            this.newNoteTitle = '';
            this.newNoteBody = '';
            // Clear the native textarea DOM element (not reactively bound)
            const textarea = this.template.querySelector('.note-body-input');
            if (textarea) textarea.value = '';
            this.showToast('Success', 'Note added.', 'success');

            // Reload notes (reset to first page)
            this.notesOffset = 0;
            const notes = await getNotesForRecordPaged({ recordId: this.panelRecordId, limitCount: this.notesPageSize + 1, offsetCount: 0 });
            this.hasMoreNotes = notes.length > this.notesPageSize;
            const displayNotes = this.hasMoreNotes ? notes.slice(0, this.notesPageSize) : notes;
            this.notesOffset = displayNotes.length;
            this.panelNotes = displayNotes.map(n => ({
                ...n,
                formattedDate: this.formatDateTime(n.createdDate),
                bodyHtml: n.body ? n.body.replace(/\n/g, '<br>') : n.preview || ''
            }));

            // Update notes count in grid
            const record = this.records.find(r => r.Id === this.panelRecordId);
            if (record && record.Notes_Count__c !== undefined) {
                record.Notes_Count__c = (record.Notes_Count__c || 0) + 1;
                this.applyDisplayRows();
            }
        } catch (error) {
            this.showToast('Error', 'Failed to save note: ' + this.reduceError(error), 'error');
        } finally {
            this.isSavingNote = false;
        }
    }

    async handleLoadMoreNotes() {
        this.loadingMoreNotes = true;
        try {
            const notes = await getNotesForRecordPaged({
                recordId: this.panelRecordId,
                limitCount: this.notesPageSize + 1,
                offsetCount: this.notesOffset
            });
            this.hasMoreNotes = notes.length > this.notesPageSize;
            const displayNotes = this.hasMoreNotes ? notes.slice(0, this.notesPageSize) : notes;
            const mapped = displayNotes.map(n => ({
                ...n,
                formattedDate: this.formatDateTime(n.createdDate),
                bodyHtml: n.body ? n.body.replace(/\n/g, '<br>') : n.preview || ''
            }));
            this.panelNotes = [...this.panelNotes, ...mapped];
            this.notesOffset += displayNotes.length;
        } catch (error) {
            this.showToast('Error', 'Failed to load notes: ' + this.reduceError(error), 'error');
        } finally {
            this.loadingMoreNotes = false;
        }
    }

    handleContactClick(event) {
        event.stopPropagation();
        const contactId = event.currentTarget.dataset.contactId;
        this[NavigationMixin.GenerateUrl]({
            type: 'standard__recordPage',
            attributes: {
                recordId: contactId,
                objectApiName: 'Contact',
                actionName: 'view'
            }
        }).then(url => {
            window.open(url, '_blank');
        });
    }

    // --- Activity handlers ---

    handleNewActivityField(event) {
        const field = event.currentTarget.dataset.field;
        const val = event.detail ? event.detail.value : event.target.value;
        if (field === 'type') this.newActivityType = val;
        else if (field === 'subject') this.newActivitySubject = val;
        else if (field === 'dueDate') this.newActivityDueDate = val;
        else if (field === 'priority') this.newActivityPriority = val;
        else if (field === 'startDate') this.newActivityStartDate = val;
        else if (field === 'startTime') this.newActivityStartTime = val;
        else if (field === 'endTime') this.newActivityEndTime = val;
        else if (field === 'location') this.newActivityLocation = val;
    }

    handleNewActivityDescription(event) {
        this.newActivityDescription = event.target.value;
    }

    async handleAddActivity() {
        const missing = [];
        if (!this.newActivitySubject || !this.newActivitySubject.trim()) missing.push('Subject');
        if (this.newActivityType === 'Meeting' && !this.newActivityStartDate) missing.push('Start Date');
        if (missing.length > 0) {
            this.showToast('Required Fields', 'Please fill in: ' + missing.join(', '), 'warning');
            return;
        }
        if (!this.canAddActivity) return;
        this.isAddingActivity = true;
        try {
            await createActivity({
                recordId: this.panelRecordId,
                activityType: this.newActivityType,
                subject: this.newActivitySubject.trim(),
                dueDate: this.newActivityDueDate || null,
                priority: this.newActivityPriority,
                description: this.newActivityDescription.trim() || null,
                startDate: this.newActivityStartDate || null,
                startTime: this.newActivityStartTime || null,
                endTime: this.newActivityEndTime || null,
                location: this.newActivityLocation.trim() || null
            });
            this.newActivitySubject = '';
            this.newActivityDueDate = '';
            this.newActivityDescription = '';
            this.newActivityType = 'Call';
            this.newActivityPriority = 'Normal';
            this.newActivityStartDate = '';
            this.newActivityStartTime = '09:00';
            this.newActivityEndTime = '10:00';
            this.newActivityLocation = '';
            const descArea = this.template.querySelector('.activity-desc-input');
            if (descArea) descArea.value = '';
            this.showToast('Success', 'Activity created.', 'success');
            await this.reloadActivities();
        } catch (error) {
            this.showToast('Error', 'Failed to create activity: ' + this.reduceError(error), 'error');
        } finally {
            this.isAddingActivity = false;
        }
    }

    async reloadActivities() {
        this.completedActivityOffset = 0;
        const activities = await getActivitiesForRecordPaged({
            recordId: this.panelRecordId,
            completedLimit: this.completedActivityPageSize + 1,
            completedOffset: 0
        });
        const mapped = activities.map(a => this.mapActivity(a));
        const open = mapped.filter(a => !a.isCompleted);
        const completed = mapped.filter(a => a.isCompleted);
        this.hasMoreCompletedActivities = completed.length > this.completedActivityPageSize;
        const displayCompleted = this.hasMoreCompletedActivities ? completed.slice(0, this.completedActivityPageSize) : completed;
        this.completedActivityOffset = displayCompleted.length;
        this.panelActivities = [...open, ...displayCompleted];
        this.refreshRowActivities(this.panelRecordId);
    }

    sortActivities(activities) {
        return activities.sort((a, b) => {
            if (a.isCompleted !== b.isCompleted) return a.isCompleted ? 1 : -1;
            return 0;
        });
    }

    mapActivity(a) {
        return {
            ...a,
            displayDate: a.dueDate || (a.startDateTime ? this.formatDateTime(a.startDateTime) : ''),
            typeIcon: a.activityType === 'Call' ? 'utility:call' :
                      a.activityType === 'Email' ? 'utility:email' :
                      a.activityType === 'Meeting' ? 'utility:event' : 'utility:task',
            statusClass: a.isCompleted ? 'activity-completed' : 'activity-open',
            statusBadgeClass: a.isCompleted ? 'activity-status-badge badge-completed' : 'activity-status-badge badge-open',
            hasLocation: !!a.location,
            canToggle: a.isTask && !a.isCompleted,
            displayTime: a.startDateTime && a.endDateTime
                ? this.formatTime(a.startDateTime) + ' - ' + this.formatTime(a.endDateTime)
                : ''
        };
    }

    async handleToggleTaskStatus(event) {
        const taskId = event.currentTarget.dataset.taskId;
        try {
            await updateTaskStatus({ taskId: taskId, newStatus: 'Completed' });
            await this.reloadActivities();
            this.showToast('Success', 'Task completed.', 'success');
        } catch (error) {
            this.showToast('Error', 'Failed to complete task: ' + this.reduceError(error), 'error');
        }
    }

    async handleLoadMoreActivities() {
        this.loadingMoreActivities = true;
        try {
            const activities = await getActivitiesForRecordPaged({
                recordId: this.panelRecordId,
                completedLimit: this.completedActivityPageSize + 1,
                completedOffset: this.completedActivityOffset
            });
            const mapped = activities.map(a => this.mapActivity(a));
            const completed = mapped.filter(a => a.isCompleted);
            this.hasMoreCompletedActivities = completed.length > this.completedActivityPageSize;
            const displayCompleted = this.hasMoreCompletedActivities ? completed.slice(0, this.completedActivityPageSize) : completed;
            this.completedActivityOffset += displayCompleted.length;
            this.panelActivities = [...this.panelActivities, ...displayCompleted];
        } catch (error) {
            this.showToast('Error', 'Failed to load activities: ' + this.reduceError(error), 'error');
        } finally {
            this.loadingMoreActivities = false;
        }
    }

    refreshRowActivities(recordId) {
        const record = this.records.find(r => r.Id === recordId);
        if (!record) return;
        // Rebuild open tasks/events from panel data
        const openTasks = this.panelActivities.filter(a => a.isTask && !a.isCompleted);
        const upcomingEvents = this.panelActivities.filter(a => a.isEvent);
        record._openTasks = openTasks.map(t => ({ Id: t.id, Subject: t.subject, Status: t.status, TaskSubtype: t.activityType }));
        record._upcomingEvents = upcomingEvents.map(e => ({ Id: e.id, Subject: e.subject }));
        this.applyDisplayRows();
    }

    formatTime(datetimeStr) {
        if (!datetimeStr) return '';
        const d = new Date(datetimeStr);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // --- Agreement handlers ---

    mapAgreement(a) {
        const statusClass = 'agreement-badge badge-' + (a.status || 'unknown').toLowerCase().replace(/\s+/g, '-');
        return {
            ...a,
            statusClass: statusClass,
            displayRequestedDate: a.requestedDate || '',
            displaySignedDate: a.signedDate || '',
            displayExpirationDate: a.expirationDate || '',
            hasIronCladUrl: !!a.ironCladUrl,
            hasNotes: !!a.notes,
            hasSignerName: !!a.signerName,
            isEditing: this.editingAgreementId === a.id
        };
    }

    handleNewAgreementField(event) {
        const field = event.currentTarget.dataset.field;
        const val = event.detail ? event.detail.value : event.target.value;
        if (field === 'type') this.newAgreementType = val;
        else if (field === 'status') this.newAgreementStatus = val;
        else if (field === 'requestedDate') this.newAgreementRequestedDate = val;
    }

    handleNewAgreementNotes(event) {
        this.newAgreementNotes = event.target.value;
    }

    async handleAddAgreement() {
        // Validate required fields before calling server
        const missing = [];
        if (!this.newAgreementType) missing.push('Agreement Type');
        if (!this.newAgreementStatus) missing.push('Status');
        if (missing.length > 0) {
            this.showToast('Required Fields', 'Please fill in: ' + missing.join(', '), 'warning');
            return;
        }
        if (!this.canAddAgreement) return;
        this.isAddingAgreement = true;
        try {
            await createAgreement({
                recordId: this.agreementsPanelRecordId,
                agreementType: this.newAgreementType,
                status: this.newAgreementStatus,
                requestedDate: this.newAgreementRequestedDate || null,
                notes: this.newAgreementNotes.trim() || null
            });
            this.newAgreementType = '';
            this.newAgreementStatus = 'Not Started';
            this.newAgreementRequestedDate = '';
            this.newAgreementNotes = '';
            const notesArea = this.template.querySelector('.agreement-notes-input');
            if (notesArea) notesArea.value = '';
            this.showToast('Success', 'Agreement created.', 'success');
            await this.reloadAgreements();
        } catch (error) {
            this.showToast('Error', 'Failed to create agreement: ' + this.reduceError(error), 'error');
        } finally {
            this.isAddingAgreement = false;
        }
    }

    handleEditAgreement(event) {
        const agrId = event.currentTarget.dataset.agreementId;
        const agr = this.panelAgreements.find(a => a.id === agrId);
        if (!agr) return;
        this.editingAgreementId = agrId;
        this.editAgreementData = {
            agreementType: agr.agreementType || '',
            status: agr.status || '',
            requestedDate: agr.requestedDate || '',
            signedDate: agr.signedDate || '',
            expirationDate: agr.expirationDate || '',
            notes: agr.notes || ''
        };
        this.panelAgreements = this.panelAgreements.map(a => this.mapAgreement(a));
    }

    handleEditAgreementField(event) {
        const field = event.currentTarget.dataset.field;
        const val = event.detail ? event.detail.value : event.target.value;
        this.editAgreementData = { ...this.editAgreementData, [field]: val };
    }

    handleEditAgreementNotes(event) {
        this.editAgreementData = { ...this.editAgreementData, notes: event.target.value };
    }

    handleCancelEditAgreement() {
        this.editingAgreementId = '';
        this.editAgreementData = {};
        this.panelAgreements = this.panelAgreements.map(a => this.mapAgreement(a));
    }

    async handleSaveAgreement() {
        this.isSavingAgreement = true;
        try {
            await updateAgreement({
                agreementId: this.editingAgreementId,
                agreementType: this.editAgreementData.agreementType,
                status: this.editAgreementData.status,
                requestedDate: this.editAgreementData.requestedDate || null,
                signedDate: this.editAgreementData.signedDate || null,
                expirationDate: this.editAgreementData.expirationDate || null,
                notes: this.editAgreementData.notes || null
            });
            this.editingAgreementId = '';
            this.editAgreementData = {};
            this.showToast('Success', 'Agreement updated.', 'success');
            await this.reloadAgreements();
        } catch (error) {
            this.showToast('Error', 'Failed to update agreement: ' + this.reduceError(error), 'error');
        } finally {
            this.isSavingAgreement = false;
        }
    }

    async reloadAgreements() {
        const agreements = await getAgreementsForRecord({ recordId: this.agreementsPanelRecordId });
        this.panelAgreements = agreements.map(a => this.mapAgreement(a));
        // Update agreement count in grid
        const record = this.records.find(r => r.Id === this.agreementsPanelRecordId);
        if (record) {
            record._agreements = agreements;
            record['Agreement_Count__c'] = agreements.length;
            this.applyDisplayRows();
        }
    }

    handleContactFieldChange(event) {
        const field = event.currentTarget.dataset.field;
        const val = event.detail.value;
        if (field === 'firstName') this.newContactFirstName = val;
        else if (field === 'lastName') this.newContactLastName = val;
        else if (field === 'email') this.newContactEmail = val;
        else if (field === 'phone') this.newContactPhone = val;
    }

    get isOtherRole() {
        return this.newContactRole === 'Other';
    }

    newContactCustomRole = '';

    handleContactSelectChange(event) {
        this.newContactRole = event.target.value;
        if (event.target.value !== 'Other') {
            this.newContactCustomRole = '';
        }
    }

    handleCustomRoleChange(event) {
        this.newContactCustomRole = event.detail.value;
    }

    async handleAddContact() {
        const missing = [];
        if (!this.newContactLastName || !this.newContactLastName.trim()) missing.push('Last Name');
        if (missing.length > 0) {
            this.showToast('Required Fields', 'Please fill in: ' + missing.join(', '), 'warning');
            return;
        }
        if (!this.canAddContact) return;
        this.isAddingContact = true;
        try {
            await createAndLinkContact({
                recordId: this.panelRecordId,
                firstName: this.newContactFirstName.trim(),
                lastName: this.newContactLastName.trim(),
                email: this.newContactEmail.trim(),
                phone: this.newContactPhone.trim(),
                role: this.newContactRole.trim(),
                roleDescription: this.newContactCustomRole.trim()
            });
            this.newContactFirstName = '';
            this.newContactLastName = '';
            this.newContactEmail = '';
            this.newContactPhone = '';
            this.newContactRole = '';
            this.newContactCustomRole = '';
            const roleSelect = this.template.querySelector('.contact-role-select');
            if (roleSelect) roleSelect.value = '';
            this.showToast('Success', 'Contact created and linked.', 'success');

            // Reload contacts
            const contacts = await getContactsForRecord({ recordId: this.panelRecordId });
            this.panelContacts = contacts.map(c => ({
                ...c,
                displayPhone: c.phone || '',
                displayEmail: c.email || '',
                displayRole: c.role === 'Other' && c.roleDescription
                    ? 'Other - ' + c.roleDescription
                    : (c.role || '')
            }));
        } catch (error) {
            this.showToast('Error', 'Failed to add contact: ' + this.reduceError(error), 'error');
        } finally {
            this.isAddingContact = false;
        }
    }

    formatDateTime(dt) {
        if (!dt) return '';
        const d = new Date(dt);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
            ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }

    // --- Utilities ---

    showToast(title, message, variant) {
        this.dispatchEvent(new ShowToastEvent({ title, message, variant }));
    }

    reduceError(error) {
        if (typeof error === 'string') return error;

        // Apex action errors with field-level details
        if (error.body) {
            const messages = [];

            // Field-level validation errors (e.g., required fields)
            if (error.body.output && error.body.output.fieldErrors) {
                const fieldErrors = error.body.output.fieldErrors;
                for (const field of Object.keys(fieldErrors)) {
                    for (const err of fieldErrors[field]) {
                        messages.push(err.message || `${field}: validation error`);
                    }
                }
            }

            // Record-level errors
            if (error.body.output && error.body.output.errors) {
                for (const err of error.body.output.errors) {
                    messages.push(err.message);
                }
            }

            // DML / trigger errors often come as an array in body
            if (Array.isArray(error.body)) {
                for (const err of error.body) {
                    if (err.message) messages.push(err.message);
                }
            }

            if (messages.length > 0) return messages.join('; ');

            // Fallback to body.message
            if (error.body.message) return error.body.message;
        }

        if (error.message) return error.message;
        return JSON.stringify(error);
    }
}