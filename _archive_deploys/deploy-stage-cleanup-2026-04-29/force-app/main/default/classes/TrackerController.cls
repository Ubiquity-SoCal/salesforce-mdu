public with sharing class TrackerController {

    @AuraEnabled(cacheable=true)
    public static List<Campaign> getActiveCampaignsForFilter() {
        return [SELECT Id, Name FROM Campaign WHERE IsActive = true ORDER BY Name ASC];
    }

    @AuraEnabled(cacheable=true)
    public static List<Tracker_View__c> getActiveViews() {
        return [
            SELECT Id, Name, Config__c, Object__c, Is_Active__c, Sort_Order__c, App_Context__c
            FROM Tracker_View__c
            WHERE Is_Active__c = true
            ORDER BY Sort_Order__c ASC NULLS LAST, Name ASC
        ];
    }

    @AuraEnabled(cacheable=true)
    public static List<Tracker_View__c> getActiveViewsForApp(String appContext) {
        if (String.isBlank(appContext)) {
            return getActiveViews();
        }
        return [
            SELECT Id, Name, Config__c, Object__c, Is_Active__c, Sort_Order__c, App_Context__c
            FROM Tracker_View__c
            WHERE Is_Active__c = true AND App_Context__c = :appContext
            ORDER BY Sort_Order__c ASC NULLS LAST, Name ASC
        ];
    }

    @AuraEnabled
    public static TrackerResult getTrackerData(String viewId) {
        return getTrackerDataPaged(viewId, 0, null, null);
    }

    @AuraEnabled
    public static TrackerResult getTrackerDataPaged(String viewId, Integer recordOffset, String ownerName, String dateRange) {
        return getTrackerDataPagedWithRE(viewId, recordOffset, ownerName, dateRange, null);
    }

    @AuraEnabled
    public static TrackerResult getTrackerDataPagedWithRE(String viewId, Integer recordOffset, String ownerName, String dateRange, String reAssignedName) {
        return getTrackerDataFull(viewId, recordOffset, ownerName, dateRange, reAssignedName, null, null, null, null);
    }

    @AuraEnabled
    public static TrackerResult getTrackerDataFull(String viewId, Integer recordOffset, String ownerName, String dateRange, String reAssignedName, String userSortField, String userSortDir, String filterField, String filterValue) {
        return getTrackerDataFullWithCampaign(viewId, recordOffset, ownerName, dateRange, reAssignedName, userSortField, userSortDir, filterField, filterValue, null);
    }

    @AuraEnabled
    public static TrackerResult getTrackerDataFullWithCampaign(String viewId, Integer recordOffset, String ownerName, String dateRange, String reAssignedName, String userSortField, String userSortDir, String filterField, String filterValue, String campaignId) {
        Tracker_View__c view = [
            SELECT Id, Name, Config__c, Object__c
            FROM Tracker_View__c
            WHERE Id = :viewId
            LIMIT 1
        ];

        TrackerResult result = new TrackerResult();
        result.viewConfig = view;

        // Parse config JSON to build dynamic SOQL
        Map<String, Object> config = (Map<String, Object>) JSON.deserializeUntyped(view.Config__c);
        List<Object> columns = (List<Object>) config.get('columns');
        Map<String, Object> sortConfig = (Map<String, Object>) config.get('sort');
        List<Object> filters = config.containsKey('filters') ? (List<Object>) config.get('filters') : new List<Object>();
        Integer recordLimit = config.containsKey('record_limit') ? (Integer) config.get('record_limit') : 50;

        // Override sort if caller provided sort params
        if (String.isNotBlank(userSortField)) {
            sortConfig = new Map<String, Object>();
            sortConfig.put('field', userSortField);
            sortConfig.put('direction', String.isNotBlank(userSortDir) ? userSortDir : 'ASC');
        }

        // Build field list and track relationship fields
        // Always include Notes_Count__c for notes icon, OwnerId for owner editing
        Set<String> directFields = new Set<String>{'Id', 'Notes_Count__c', 'OwnerId'};
        Set<String> relationshipFields = new Set<String>();
        // Virtual fields are computed in the LWC from subqueries — skip in SOQL
        Set<String> virtualFields = new Set<String>{'ST_Build_Status', 'ST_Site_Status'};

        for (Object col : columns) {
            Map<String, Object> colMap = (Map<String, Object>) col;
            String field = (String) colMap.get('field');
            if (virtualFields.contains(field)) {
                continue;
            } else if (field.contains('.')) {
                relationshipFields.add(field);
            } else {
                directFields.add(field);
            }
        }

        // Build SOQL
        String objectName = view.Object__c;
        List<String> allFields = new List<String>(directFields);
        allFields.addAll(relationshipFields);
        String fieldList = String.join(allFields, ', ');

        String soql = 'SELECT ' + fieldList;

        // Add Agreement and Activity sub-queries if querying Opportunity
        if (objectName == 'Opportunity') {
            soql += ', (SELECT Id, Name, Agreement_Type__c, Status__c FROM Agreements__r)';
            soql += ', (SELECT Id, Subject, Status, TaskSubtype, ActivityDate FROM Tasks WHERE Status != \'Completed\' ORDER BY ActivityDate ASC NULLS LAST LIMIT 5)';
            soql += ', (SELECT Id, Subject, StartDateTime FROM Events WHERE StartDateTime >= TODAY ORDER BY StartDateTime ASC LIMIT 5)';
            soql += ', (SELECT Id, Build_Status__c, Site_Status__c FROM SiteTracker_Projects__r ORDER BY Last_Synced__c DESC NULLS LAST LIMIT 1)';
        }

        soql += ' FROM ' + objectName;

        // Build WHERE clause
        List<String> whereClauses = new List<String>();
        for (Object f : filters) {
            Map<String, Object> filterMap = (Map<String, Object>) f;
            String field = (String) filterMap.get('field');
            String op = (String) filterMap.get('operator');
            Object val = filterMap.get('value');

            whereClauses.add(buildFilterClause(field, op, val));
        }

        // Owner filter (server-side)
        if (String.isNotBlank(ownerName)) {
            whereClauses.add('Owner.Name = \'' + String.escapeSingleQuotes(ownerName) + '\'');
        }

        // RE Assigned filter (server-side)
        if (String.isNotBlank(reAssignedName)) {
            whereClauses.add('RE_Assigned__r.Name = \'' + String.escapeSingleQuotes(reAssignedName) + '\'');
        }

        // Text filter (server-side LIKE search)
        if (String.isNotBlank(filterField) && String.isNotBlank(filterValue)) {
            // Only allow filtering on fields that are in the column list (security)
            Set<String> allowedFields = new Set<String>();
            for (Object col : columns) {
                Map<String, Object> colMap = (Map<String, Object>) col;
                allowedFields.add((String) colMap.get('field'));
            }
            if (allowedFields.contains(filterField) && !filterField.contains('.')) {
                whereClauses.add(filterField + ' LIKE \'%' + String.escapeSingleQuotes(filterValue) + '%\'');
            }
        }

        // Date range filter on Projected_Close_Date__c
        if (String.isNotBlank(dateRange)) {
            if (dateRange == 'NEXT_7_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:7');
            } else if (dateRange == 'NEXT_30_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:30');
            } else if (dateRange == 'NEXT_60_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:60');
            } else if (dateRange == 'NEXT_90_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:90');
            } else if (dateRange == 'PAST_DUE') {
                whereClauses.add('Projected_Close_Date__c < TODAY AND Projected_Close_Date__c != null AND StageName NOT IN (\'Closed Lost\', \'PAL/ROE Complete\', \'EMA/Bulk In Progress\', \'EMA/Bulk Complete\', \'On Hold\')');
            }
        }

        // Campaign filter (server-side). Only applies when querying Opportunity.
        if (String.isNotBlank(campaignId) && objectName == 'Opportunity') {
            whereClauses.add('CampaignId = \'' + String.escapeSingleQuotes(campaignId) + '\'');
        }

        if (!whereClauses.isEmpty()) {
            soql += ' WHERE ' + String.join(whereClauses, ' AND ');
        }

        // Sort
        if (sortConfig != null) {
            String sortField = (String) sortConfig.get('field');
            String sortDir = (String) sortConfig.get('direction');
            soql += ' ORDER BY ' + sortField + ' ' + sortDir + ' NULLS LAST';
        }

        // Count total matching records (without LIMIT) for summary
        String countSoql = 'SELECT COUNT() FROM ' + objectName;
        if (!whereClauses.isEmpty()) {
            countSoql += ' WHERE ' + String.join(whereClauses, ' AND ');
        }
        result.totalCount = Database.countQuery(countSoql);

        // Limit + Offset
        soql += ' LIMIT ' + recordLimit;
        if (recordOffset != null && recordOffset > 0) {
            soql += ' OFFSET ' + recordOffset;
        }

        result.records = Database.query(soql);
        result.hasMore = (recordOffset + result.records.size()) < result.totalCount;
        return result;
    }

    @AuraEnabled
    public static List<SaveResultWrapper> saveRecords(List<SObject> records) {
        List<Database.SaveResult> results = Database.update(records, false);
        List<SaveResultWrapper> wrappers = new List<SaveResultWrapper>();
        for (Database.SaveResult sr : results) {
            SaveResultWrapper w = new SaveResultWrapper();
            w.success = sr.isSuccess();
            w.id = sr.getId();
            w.errors = new List<String>();
            if (!sr.isSuccess()) {
                for (Database.Error err : sr.getErrors()) {
                    w.errors.add(err.getMessage());
                }
            }
            wrappers.add(w);
        }
        return wrappers;
    }

    @AuraEnabled
    public static List<NoteWrapper> getNotesForRecord(String recordId) {
        return getNotesForRecordPaged(recordId, 2000, 0);
    }

    @AuraEnabled
    public static List<NoteWrapper> getNotesForRecordPaged(String recordId, Integer limitCount, Integer offsetCount) {
        List<NoteWrapper> notes = new List<NoteWrapper>();

        // Query ContentDocumentLinks for this record
        List<ContentDocumentLink> links = [
            SELECT ContentDocumentId
            FROM ContentDocumentLink
            WHERE LinkedEntityId = :recordId
        ];

        if (links.isEmpty()) {
            return notes;
        }

        Set<Id> docIds = new Set<Id>();
        for (ContentDocumentLink link : links) {
            docIds.add(link.ContentDocumentId);
        }

        // Query via ContentVersion which bridges ContentDocument and ContentNote
        // FileType = 'SNOTE' identifies enhanced notes
        List<ContentVersion> versions = [
            SELECT ContentDocumentId, Title, TextPreview,
                   CreatedDate, CreatedBy.Name, LastModifiedDate
            FROM ContentVersion
            WHERE ContentDocumentId IN :docIds
            AND FileType = 'SNOTE'
            AND IsLatest = true
            ORDER BY CreatedDate DESC
            LIMIT :limitCount
            OFFSET :offsetCount
        ];

        for (ContentVersion cv : versions) {
            NoteWrapper nw = new NoteWrapper();
            nw.id = cv.ContentDocumentId;
            nw.title = cv.Title;
            nw.preview = cv.TextPreview;
            nw.body = cv.TextPreview != null ? cv.TextPreview : '';
            nw.createdDate = cv.CreatedDate;
            nw.createdBy = cv.CreatedBy.Name;
            nw.lastModified = cv.LastModifiedDate;
            notes.add(nw);
        }

        return notes;
    }

    @AuraEnabled
    public static List<ContactWrapper> getContactsForRecord(String recordId) {
        List<ContactWrapper> contacts = new List<ContactWrapper>();

        List<Opportunity_Contact__c> oppContacts = [
            SELECT Id, Contact__c, Contact__r.Name, Contact__r.Email, Contact__r.Phone, Role__c, Role_Description__c
            FROM Opportunity_Contact__c
            WHERE Opportunity__c = :recordId
            ORDER BY Contact__r.Name ASC
        ];

        for (Opportunity_Contact__c oc : oppContacts) {
            ContactWrapper cw = new ContactWrapper();
            cw.id = oc.Id;
            cw.contactId = oc.Contact__c;
            cw.name = oc.Contact__r.Name;
            cw.email = oc.Contact__r.Email;
            cw.phone = oc.Contact__r.Phone;
            cw.role = oc.Role__c;
            cw.roleDescription = oc.Role_Description__c;
            contacts.add(cw);
        }

        return contacts;
    }

    @AuraEnabled
    public static String createNote(String recordId, String title, String body) {
        ContentNote note = new ContentNote();
        note.Title = title;
        note.Content = Blob.valueOf(body);
        insert note;

        ContentDocumentLink link = new ContentDocumentLink();
        link.ContentDocumentId = note.Id;
        link.LinkedEntityId = recordId;
        link.ShareType = 'V';
        link.Visibility = 'AllUsers';
        insert link;

        // Update Notes_Count__c with actual count
        Integer count = [SELECT COUNT() FROM ContentDocumentLink WHERE LinkedEntityId = :recordId];
        Opportunity opp = [SELECT Id FROM Opportunity WHERE Id = :recordId LIMIT 1];
        opp.Notes_Count__c = count;
        update opp;

        return note.Id;
    }

    @AuraEnabled
    public static String createAndLinkContact(String recordId, String firstName, String lastName, String email, String phone, String role, String roleDescription) {
        // Get the Account from the Opportunity to associate the Contact
        Opportunity opp = [SELECT AccountId FROM Opportunity WHERE Id = :recordId LIMIT 1];

        Contact c = new Contact();
        c.FirstName = firstName;
        c.LastName = lastName;
        c.Email = email;
        c.Phone = phone;
        if (opp.AccountId != null) {
            c.AccountId = opp.AccountId;
        }
        insert c;

        Opportunity_Contact__c oc = new Opportunity_Contact__c();
        oc.Opportunity__c = recordId;
        oc.Contact__c = c.Id;
        if (String.isNotBlank(role)) {
            oc.Role__c = role;
        }
        if (String.isNotBlank(roleDescription)) {
            oc.Role_Description__c = roleDescription;
        }
        insert oc;

        return c.Id;
    }

    @AuraEnabled
    public static List<ActivityWrapper> getActivitiesForRecord(String recordId) {
        return getActivitiesForRecordPaged(recordId, 5, 0);
    }

    @AuraEnabled
    public static List<ActivityWrapper> getActivitiesForRecordPaged(String recordId, Integer completedLimit, Integer completedOffset) {
        List<ActivityWrapper> activities = new List<ActivityWrapper>();

        // ALL open tasks (always show these)
        for (Task t : [
            SELECT Id, Subject, Status, Priority, ActivityDate, Description,
                   TaskSubtype, CallType, Owner.Name
            FROM Task
            WHERE WhatId = :recordId AND Status != 'Completed'
            ORDER BY ActivityDate ASC NULLS LAST, CreatedDate DESC
        ]) {
            activities.add(mapTask(t));
        }

        // Upcoming events (always show these)
        for (Event e : [
            SELECT Id, Subject, StartDateTime, EndDateTime, Location,
                   Description, Type, Owner.Name
            FROM Event
            WHERE WhatId = :recordId AND StartDateTime >= TODAY
            ORDER BY StartDateTime ASC
        ]) {
            activities.add(mapEvent(e));
        }

        // Completed tasks (paged)
        for (Task t : [
            SELECT Id, Subject, Status, Priority, ActivityDate, Description,
                   TaskSubtype, CallType, Owner.Name
            FROM Task
            WHERE WhatId = :recordId AND Status = 'Completed'
            ORDER BY LastModifiedDate DESC
            LIMIT :completedLimit
            OFFSET :completedOffset
        ]) {
            activities.add(mapTask(t));
        }

        // Past events (paged)
        for (Event e : [
            SELECT Id, Subject, StartDateTime, EndDateTime, Location,
                   Description, Type, Owner.Name
            FROM Event
            WHERE WhatId = :recordId AND StartDateTime < TODAY
            ORDER BY StartDateTime DESC
            LIMIT :completedLimit
            OFFSET :completedOffset
        ]) {
            activities.add(mapEvent(e));
        }

        return activities;
    }

    private static ActivityWrapper mapTask(Task t) {
        ActivityWrapper aw = new ActivityWrapper();
        aw.id = t.Id;
        aw.subject = t.Subject;
        aw.activityType = t.TaskSubtype != null ? t.TaskSubtype : 'Task';
        aw.status = t.Status;
        aw.priority = t.Priority;
        aw.dueDate = t.ActivityDate;
        aw.description = t.Description;
        aw.ownerName = t.Owner.Name;
        aw.isTask = true;
        aw.isEvent = false;
        aw.isCompleted = t.Status == 'Completed';
        return aw;
    }

    private static ActivityWrapper mapEvent(Event e) {
        ActivityWrapper aw = new ActivityWrapper();
        aw.id = e.Id;
        aw.subject = e.Subject;
        aw.activityType = e.Type != null ? e.Type : 'Meeting';
        aw.startDateTime = e.StartDateTime;
        aw.endDateTime = e.EndDateTime;
        aw.location = e.Location;
        aw.description = e.Description;
        aw.ownerName = e.Owner.Name;
        aw.isTask = false;
        aw.isEvent = true;
        aw.isCompleted = e.StartDateTime < Datetime.now();
        return aw;
    }

    @AuraEnabled
    public static String createActivity(String recordId, String activityType, String subject, String dueDate, String priority, String description, String startDate, String startTime, String endTime, String location) {
        if (activityType == 'Call' || activityType == 'Email' || activityType == 'Task') {
            Task t = new Task();
            t.WhatId = recordId;
            t.Subject = subject;
            t.TaskSubtype = activityType;
            t.Status = (activityType == 'Call' || activityType == 'Email') ? 'Completed' : 'Open';
            t.Priority = String.isNotBlank(priority) ? priority : 'Normal';
            if (String.isNotBlank(dueDate)) {
                t.ActivityDate = Date.valueOf(dueDate);
            } else if (activityType == 'Call' || activityType == 'Email') {
                t.ActivityDate = Date.today();
            }
            if (String.isNotBlank(description)) {
                t.Description = description;
            }
            insert t;
            return t.Id;
        } else {
            // Meeting/Event
            Event e = new Event();
            e.WhatId = recordId;
            e.Subject = subject;
            if (String.isNotBlank(description)) {
                e.Description = description;
            }
            if (String.isNotBlank(location)) {
                e.Location = location;
            }
            if (String.isNotBlank(startDate)) {
                String sTime = String.isNotBlank(startTime) ? startTime : '09:00';
                String eTime = String.isNotBlank(endTime) ? endTime : '10:00';
                Datetime startDt = Datetime.valueOf(startDate + ' ' + sTime + ':00');
                Datetime endDt = Datetime.valueOf(startDate + ' ' + eTime + ':00');
                if (endDt <= startDt) {
                    endDt = startDt.addHours(1);
                }
                e.StartDateTime = startDt;
                e.EndDateTime = endDt;
            } else {
                e.StartDateTime = Datetime.now();
                e.EndDateTime = Datetime.now().addHours(1);
            }
            insert e;
            return e.Id;
        }
    }

    @AuraEnabled
    public static void updateTaskStatus(String taskId, String newStatus) {
        Task t = [SELECT Id, Status FROM Task WHERE Id = :taskId LIMIT 1];
        t.Status = newStatus;
        update t;
    }

    @AuraEnabled
    public static List<AgreementWrapper> getAgreementsForRecord(String recordId) {
        List<AgreementWrapper> agreements = new List<AgreementWrapper>();
        for (Agreement__c a : [
            SELECT Id, Name, Agreement_Type__c, Status__c, Requested_Date__c,
                   Signed_Date__c, Expiration_Date__c, Signer__c, Signer__r.Name,
                   IronClad_ID__c, IronClad_URL__c, Notes__c
            FROM Agreement__c
            WHERE Opportunity__c = :recordId
            ORDER BY CreatedDate DESC
        ]) {
            AgreementWrapper aw = new AgreementWrapper();
            aw.id = a.Id;
            aw.name = a.Name;
            aw.agreementType = a.Agreement_Type__c;
            aw.status = a.Status__c;
            aw.requestedDate = a.Requested_Date__c;
            aw.signedDate = a.Signed_Date__c;
            aw.expirationDate = a.Expiration_Date__c;
            aw.signerId = a.Signer__c;
            aw.signerName = a.Signer__r != null ? a.Signer__r.Name : '';
            aw.ironCladId = a.IronClad_ID__c;
            aw.ironCladUrl = a.IronClad_URL__c;
            aw.notes = a.Notes__c;
            agreements.add(aw);
        }
        return agreements;
    }

    @AuraEnabled
    public static String createAgreement(String recordId, String agreementType, String status, String requestedDate, String notes) {
        Agreement__c a = new Agreement__c();
        a.Opportunity__c = recordId;
        a.Agreement_Type__c = agreementType;
        a.Status__c = status;
        if (String.isNotBlank(requestedDate)) {
            a.Requested_Date__c = Date.valueOf(requestedDate);
        }
        if (String.isNotBlank(notes)) {
            a.Notes__c = notes;
        }
        insert a;
        return a.Id;
    }

    @AuraEnabled
    public static void updateAgreement(String agreementId, String agreementType, String status, String requestedDate, String signedDate, String expirationDate, String notes) {
        Agreement__c a = [SELECT Id FROM Agreement__c WHERE Id = :agreementId LIMIT 1];
        a.Agreement_Type__c = agreementType;
        a.Status__c = status;
        a.Requested_Date__c = String.isNotBlank(requestedDate) ? Date.valueOf(requestedDate) : null;
        a.Signed_Date__c = String.isNotBlank(signedDate) ? Date.valueOf(signedDate) : null;
        a.Expiration_Date__c = String.isNotBlank(expirationDate) ? Date.valueOf(expirationDate) : null;
        a.Notes__c = notes;
        update a;
    }

    @AuraEnabled(cacheable=true)
    public static Map<String, List<PicklistOption>> getAgreementPicklists() {
        Map<String, List<PicklistOption>> result = new Map<String, List<PicklistOption>>();
        for (String fieldName : new List<String>{'Agreement_Type__c', 'Status__c'}) {
            Schema.DescribeFieldResult dfr = Agreement__c.getSObjectType().getDescribe()
                .fields.getMap().get(fieldName).getDescribe();
            List<PicklistOption> opts = new List<PicklistOption>();
            for (Schema.PicklistEntry pe : dfr.getPicklistValues()) {
                if (pe.isActive()) {
                    PicklistOption po = new PicklistOption();
                    po.label = pe.getLabel();
                    po.value = pe.getValue();
                    opts.add(po);
                }
            }
            result.put(fieldName, opts);
        }
        return result;
    }

    @AuraEnabled(cacheable=true)
    public static List<PicklistOption> getContactRoleOptions() {
        List<PicklistOption> opts = new List<PicklistOption>();
        Schema.DescribeFieldResult dfr = Opportunity_Contact__c.Role__c.getDescribe();
        for (Schema.PicklistEntry pe : dfr.getPicklistValues()) {
            if (pe.isActive()) {
                PicklistOption po = new PicklistOption();
                po.label = pe.getLabel();
                po.value = pe.getValue();
                opts.add(po);
            }
        }
        return opts;
    }

    @AuraEnabled(cacheable=true)
    public static Map<String, List<PicklistOption>> getPicklistValues(String objectName) {
        // Cache buster: 2026-04-28 EMA/Bulk stages added
        Map<String, List<PicklistOption>> result = new Map<String, List<PicklistOption>>();
        Schema.SObjectType objType = Schema.getGlobalDescribe().get(objectName);
        if (objType == null) return result;

        Map<String, Schema.SObjectField> fieldMap = objType.getDescribe().fields.getMap();
        for (String fieldName : fieldMap.keySet()) {
            Schema.DescribeFieldResult dfr = fieldMap.get(fieldName).getDescribe();
            if (dfr.getType() == Schema.DisplayType.PICKLIST) {
                List<PicklistOption> opts = new List<PicklistOption>();
                for (Schema.PicklistEntry pe : dfr.getPicklistValues()) {
                    if (pe.isActive()) {
                        PicklistOption po = new PicklistOption();
                        po.label = pe.getLabel();
                        po.value = pe.getValue();
                        opts.add(po);
                    }
                }
                // Use the actual API name from the describe (proper casing)
                result.put(dfr.getName(), opts);
            }
        }
        return result;
    }

    @AuraEnabled(cacheable=true)
    public static List<OwnerOption> getActiveUsers() {
        List<OwnerOption> options = new List<OwnerOption>();
        for (User u : [
            SELECT Id, Name
            FROM User
            WHERE IsActive = true AND UserType = 'Standard'
            ORDER BY Name ASC
        ]) {
            OwnerOption opt = new OwnerOption();
            opt.label = u.Name;
            opt.value = u.Id;
            options.add(opt);
        }
        return options;
    }

    private static String buildFilterClause(String field, String op, Object val) {
        if (op == 'equals') {
            if (val == 'CURRENT_USER') {
                return field + ' = \'' + UserInfo.getUserId() + '\'';
            }
            return field + ' = \'' + String.valueOf(val) + '\'';
        } else if (op == 'not_equals') {
            return field + ' != \'' + String.valueOf(val) + '\'';
        } else if (op == 'not_in') {
            List<Object> vals = (List<Object>) val;
            List<String> quoted = new List<String>();
            for (Object v : vals) {
                quoted.add('\'' + String.valueOf(v) + '\'');
            }
            return field + ' NOT IN (' + String.join(quoted, ', ') + ')';
        } else if (op == 'in_list') {
            List<Object> vals = (List<Object>) val;
            List<String> quoted = new List<String>();
            for (Object v : vals) {
                quoted.add('\'' + String.valueOf(v) + '\'');
            }
            return field + ' IN (' + String.join(quoted, ', ') + ')';
        } else if (op == 'less_than') {
            String sval = String.valueOf(val);
            if (sval == 'TODAY') {
                return field + ' < TODAY';
            }
            return field + ' < ' + sval;
        } else if (op == 'greater_than') {
            String sval = String.valueOf(val);
            if (sval == 'TODAY') {
                return field + ' > TODAY';
            }
            return field + ' > ' + sval;
        }
        return '';
    }

    public class TrackerResult {
        @AuraEnabled public Tracker_View__c viewConfig;
        @AuraEnabled public List<SObject> records;
        @AuraEnabled public Integer totalCount;
        @AuraEnabled public Boolean hasMore;
    }

    public class SaveResultWrapper {
        @AuraEnabled public Boolean success;
        @AuraEnabled public String id;
        @AuraEnabled public List<String> errors;
    }

    public class NoteWrapper {
        @AuraEnabled public String id;
        @AuraEnabled public String title;
        @AuraEnabled public String preview;
        @AuraEnabled public String body;
        @AuraEnabled public Datetime createdDate;
        @AuraEnabled public String createdBy;
        @AuraEnabled public Datetime lastModified;
    }

    public class PicklistOption {
        @AuraEnabled public String label;
        @AuraEnabled public String value;
    }

    public class OwnerOption {
        @AuraEnabled public String label;
        @AuraEnabled public String value;
    }

    public class ContactWrapper {
        @AuraEnabled public String id;
        @AuraEnabled public String contactId;
        @AuraEnabled public String name;
        @AuraEnabled public String email;
        @AuraEnabled public String phone;
        @AuraEnabled public String role;
        @AuraEnabled public String roleDescription;
    }

    public class ActivityWrapper {
        @AuraEnabled public String id;
        @AuraEnabled public String subject;
        @AuraEnabled public String activityType;
        @AuraEnabled public String status;
        @AuraEnabled public String priority;
        @AuraEnabled public Date dueDate;
        @AuraEnabled public Datetime startDateTime;
        @AuraEnabled public Datetime endDateTime;
        @AuraEnabled public String location;
        @AuraEnabled public String description;
        @AuraEnabled public String ownerName;
        @AuraEnabled public Boolean isTask;
        @AuraEnabled public Boolean isEvent;
        @AuraEnabled public Boolean isCompleted;
    }

    @AuraEnabled
    public static SummaryResult getTrackerSummary(String viewId) {
        return getTrackerSummaryFiltered(viewId, null, null, null);
    }

    @AuraEnabled
    public static SummaryResult getTrackerSummaryFiltered(String viewId, String ownerName, String dateRange, String reAssignedName) {
        return getTrackerSummaryFilteredWithCampaign(viewId, ownerName, dateRange, reAssignedName, null);
    }

    @AuraEnabled
    public static SummaryResult getTrackerSummaryFilteredWithCampaign(String viewId, String ownerName, String dateRange, String reAssignedName, String campaignId) {
        Tracker_View__c view = [
            SELECT Config__c, Object__c FROM Tracker_View__c WHERE Id = :viewId LIMIT 1
        ];
        Map<String, Object> config = (Map<String, Object>) JSON.deserializeUntyped(view.Config__c);
        List<Object> filters = config.containsKey('filters') ? (List<Object>) config.get('filters') : new List<Object>();

        // Build WHERE
        List<String> whereClauses = new List<String>();
        for (Object f : filters) {
            Map<String, Object> filterMap = (Map<String, Object>) f;
            whereClauses.add(buildFilterClause(
                (String) filterMap.get('field'),
                (String) filterMap.get('operator'),
                filterMap.get('value')
            ));
        }
        if (String.isNotBlank(ownerName)) {
            whereClauses.add('Owner.Name = \'' + String.escapeSingleQuotes(ownerName) + '\'');
        }
        if (String.isNotBlank(reAssignedName)) {
            whereClauses.add('RE_Assigned__r.Name = \'' + String.escapeSingleQuotes(reAssignedName) + '\'');
        }
        if (String.isNotBlank(dateRange)) {
            if (dateRange == 'NEXT_7_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:7');
            } else if (dateRange == 'NEXT_30_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:30');
            } else if (dateRange == 'NEXT_60_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:60');
            } else if (dateRange == 'NEXT_90_DAYS') {
                whereClauses.add('Projected_Close_Date__c >= TODAY AND Projected_Close_Date__c <= NEXT_N_DAYS:90');
            } else if (dateRange == 'PAST_DUE') {
                whereClauses.add('Projected_Close_Date__c < TODAY AND Projected_Close_Date__c != null AND StageName NOT IN (\'Closed Lost\', \'PAL/ROE Complete\', \'EMA/Bulk In Progress\', \'EMA/Bulk Complete\', \'On Hold\')');
            }
        }
        if (String.isNotBlank(campaignId)) {
            whereClauses.add('CampaignId = \'' + String.escapeSingleQuotes(campaignId) + '\'');
        }
        String whereStr = whereClauses.isEmpty() ? '' : ' WHERE ' + String.join(whereClauses, ' AND ');

        SummaryResult summary = new SummaryResult();

        // Count + sum units
        String aggSoql = 'SELECT COUNT(Id) cnt, SUM(Units__c) totalUnits FROM Opportunity' + whereStr;
        AggregateResult agg = Database.query(aggSoql);
        summary.totalOpportunities = (Integer) agg.get('cnt');
        summary.totalUnits = agg.get('totalUnits') != null ? ((Decimal) agg.get('totalUnits')).intValue() : 0;

        // Agreement counts by type (only Completed)
        String agrSoql = 'SELECT Agreement_Type__c, COUNT(Id) cnt FROM Agreement__c WHERE Status__c = \'Completed\' AND Opportunity__c IN (SELECT Id FROM Opportunity' + whereStr + ') GROUP BY Agreement_Type__c ORDER BY COUNT(Id) DESC';
        List<AggregateResult> agrResults = Database.query(agrSoql);
        summary.agreementsByType = new List<AgreementCount>();
        Integer totalAgr = 0;
        for (AggregateResult ar : agrResults) {
            AgreementCount ac = new AgreementCount();
            ac.agreementType = (String) ar.get('Agreement_Type__c');
            ac.count = (Integer) ar.get('cnt');
            totalAgr += ac.count;
            summary.agreementsByType.add(ac);
        }
        summary.totalAgreements = totalAgr;

        return summary;
    }

    public class SummaryResult {
        @AuraEnabled public Integer totalOpportunities;
        @AuraEnabled public Integer totalUnits;
        @AuraEnabled public Integer totalAgreements;
        @AuraEnabled public List<AgreementCount> agreementsByType;
    }

    public class AgreementCount {
        @AuraEnabled public String agreementType;
        @AuraEnabled public Integer count;
    }

    public class AgreementWrapper {
        @AuraEnabled public String id;
        @AuraEnabled public String name;
        @AuraEnabled public String agreementType;
        @AuraEnabled public String status;
        @AuraEnabled public Date requestedDate;
        @AuraEnabled public Date signedDate;
        @AuraEnabled public Date expirationDate;
        @AuraEnabled public String signerId;
        @AuraEnabled public String signerName;
        @AuraEnabled public String ironCladId;
        @AuraEnabled public String ironCladUrl;
        @AuraEnabled public String notes;
    }

    // ── Executive Dashboard ──────────────────────────────────────

    @AuraEnabled
    public static ExecutiveDashboardData getExecutiveDashboardData() {
        ExecutiveDashboardData data = new ExecutiveDashboardData();

        // Pre-PAL stages (sales forecasting toward PAL signing)
        List<String> prePalStages = new List<String>{
            'Prospecting', 'Engaged', 'Proposal Sent', 'Contract Negotiations'
        };
        // EMA/Bulk forecast stage (Melissa's lane after PAL)
        List<String> emaBulkStages = new List<String>{
            'EMA/Bulk In Progress'
        };
        // Stages that visualize the funnel (all active sales states)
        List<String> funnelStagesList = new List<String>{
            'Prospecting', 'Engaged', 'Proposal Sent', 'Contract Negotiations',
            'PAL/ROE Complete', 'EMA/Bulk In Progress', 'EMA/Bulk Complete'
        };
        // Completed stages (MDU-correct: no Closed Won, no legacy stages)
        List<String> completedStages = new List<String>{
            'PAL/ROE Complete', 'EMA/Bulk In Progress', 'EMA/Bulk Complete'
        };

        // Lane owners (filter forecast queries by these names)
        String palOwnerName     = 'Brett Spivey';
        String emaBulkOwnerName = 'Melissa Baker';
        String saqOwnerName     = 'Bill Holick';

        // 1. Funnel counts by stage (all 7 active stages, only Opps with Projected Close)
        Map<String, AggregateResult> funnelMap = new Map<String, AggregateResult>();
        for (AggregateResult ar : [
            SELECT StageName, COUNT(Id) cnt, SUM(Units__c) units
            FROM Opportunity
            WHERE RecordType.DeveloperName = 'MDU'
              AND IsClosed = FALSE
              AND Projected_Close_Date__c != null
              AND StageName IN :funnelStagesList
            GROUP BY StageName
        ]) {
            funnelMap.put((String) ar.get('StageName'), ar);
        }

        data.funnelStages = new List<FunnelStage>();
        Integer totalPipeline = 0;
        for (String stage : funnelStagesList) {
            FunnelStage fs = new FunnelStage();
            fs.stage = stage;
            if (funnelMap.containsKey(stage)) {
                fs.count = (Integer) funnelMap.get(stage).get('cnt');
                Object u = funnelMap.get(stage).get('units');
                fs.units = u != null ? ((Decimal) u).intValue() : 0;
            } else {
                fs.count = 0;
                fs.units = 0;
            }
            totalPipeline += fs.count;
            data.funnelStages.add(fs);
        }
        data.totalPipeline = totalPipeline;

        // 2. Total completed
        data.totalCompleted = [
            SELECT COUNT() FROM Opportunity
            WHERE RecordType.DeveloperName = 'MDU' AND StageName IN :completedStages
        ];

        // 3. Agreements signed this year by month
        Integer currentYear = Date.today().year();
        Date yearStart = Date.newInstance(currentYear, 1, 1);
        Date yearEnd   = Date.newInstance(currentYear, 12, 31);

        Map<Integer, Integer> monthMap = new Map<Integer, Integer>();
        Integer totalSigned = 0;
        for (AggregateResult ar : [
            SELECT CALENDAR_MONTH(Signed_Date__c) mo, COUNT(Id) cnt
            FROM Agreement__c
            WHERE Signed_Date__c >= :yearStart
              AND Signed_Date__c <= :yearEnd
              AND Opportunity__r.RecordType.DeveloperName = 'MDU'
            GROUP BY CALENDAR_MONTH(Signed_Date__c)
            ORDER BY CALENDAR_MONTH(Signed_Date__c)
        ]) {
            Integer mo = (Integer) ar.get('mo');
            Integer cnt = (Integer) ar.get('cnt');
            monthMap.put(mo, cnt);
            totalSigned += cnt;
        }
        data.totalSignedYTD = totalSigned;

        List<String> monthNames = new List<String>{
            'Jan','Feb','Mar','Apr','May','Jun',
            'Jul','Aug','Sep','Oct','Nov','Dec'
        };
        data.completedByMonth = new List<MonthlyCount>();
        for (Integer i = 1; i <= 12; i++) {
            MonthlyCount mc = new MonthlyCount();
            mc.month = i;
            mc.monthName = monthNames[i - 1];
            mc.count = monthMap.containsKey(i) ? monthMap.get(i) : 0;
            data.completedByMonth.add(mc);
        }

        // 4. Three-lane forecast — PAL (Brett), EMA/Bulk (Melissa), SAQ (Bill)
        Date today    = Date.today();
        Date in90Days = today.addDays(90);

        data.palForecast     = buildLaneForecast(palOwnerName,     prePalStages, today, in90Days);
        data.emaBulkForecast = buildLaneForecast(emaBulkOwnerName, emaBulkStages, today, in90Days);
        data.saqForecast     = buildLaneForecast(saqOwnerName,     prePalStages, today, in90Days);

        // Backward-compat: combined past-due/next-90/over-90 across all lanes
        data.pastDueDetails    = new List<PipelineDetail>();
        data.next90DaysDetails = new List<PipelineDetail>();
        data.over90DaysDetails = new List<PipelineDetail>();
        for (LaneForecast lf : new List<LaneForecast>{ data.palForecast, data.emaBulkForecast, data.saqForecast }) {
            data.pastDueDetails.addAll(lf.pastDueDetails);
            data.next90DaysDetails.addAll(lf.next90Details);
            data.over90DaysDetails.addAll(lf.over90Details);
        }
        data.pastDueCount    = data.pastDueDetails.size();
        data.next90DaysCount = data.next90DaysDetails.size();
        data.over90DaysCount = data.over90DaysDetails.size();

        // 5. In-progress SiteTracker Projects — exclude first (PAL/ROE Signed) and
        //    last (Completed) build-status steps. Soonest Activation_Forecast__c first.
        Set<String> excludeStatuses = new Set<String>{
            '1. Project - PAL/ROE Signed',
            '4. Project - Completed'
        };
        data.inProgressSiteTrackers = new List<SiteTrackerSummary>();
        for (SiteTracker_Project__c st : [
            SELECT Id, Name, Build_Status__c, Site_Status__c, Activation_Forecast__c,
                   Opportunity__c, Opportunity__r.Name, Opportunity__r.Property_State__c,
                   Opportunity__r.Units__c, Opportunity__r.Owner.Name
            FROM SiteTracker_Project__c
            WHERE Build_Status__c != null
              AND Build_Status__c NOT IN :excludeStatuses
            ORDER BY Activation_Forecast__c ASC NULLS LAST, Name ASC
        ]) {
            SiteTrackerSummary s = new SiteTrackerSummary();
            s.id                 = st.Id;
            s.name               = st.Name;
            s.buildStatus        = st.Build_Status__c;
            s.siteStatus         = st.Site_Status__c;
            s.activationForecast = st.Activation_Forecast__c;
            s.oppId              = st.Opportunity__c;
            s.oppName            = st.Opportunity__r != null ? st.Opportunity__r.Name : null;
            s.state              = st.Opportunity__r != null ? st.Opportunity__r.Property_State__c : null;
            s.units              = (st.Opportunity__r != null && st.Opportunity__r.Units__c != null)
                                   ? st.Opportunity__r.Units__c.intValue() : 0;
            s.ownerName          = (st.Opportunity__r != null && st.Opportunity__r.Owner != null)
                                   ? st.Opportunity__r.Owner.Name : null;
            data.inProgressSiteTrackers.add(s);
        }
        data.inProgressSiteTrackerCount = data.inProgressSiteTrackers.size();

        return data;
    }

    public class SiteTrackerSummary {
        @AuraEnabled public Id id;
        @AuraEnabled public String name;
        @AuraEnabled public String buildStatus;
        @AuraEnabled public String siteStatus;
        @AuraEnabled public Date activationForecast;
        @AuraEnabled public Id oppId;
        @AuraEnabled public String oppName;
        @AuraEnabled public String state;
        @AuraEnabled public Integer units;
        @AuraEnabled public String ownerName;
    }

    private static LaneForecast buildLaneForecast(
        String ownerName, List<String> stages, Date today, Date in90Days
    ) {
        LaneForecast lf = new LaneForecast();
        lf.ownerName = ownerName;
        lf.pastDueDetails = new List<PipelineDetail>();
        lf.next90Details  = new List<PipelineDetail>();
        lf.over90Details  = new List<PipelineDetail>();
        Integer pdUnits = 0, n90Units = 0, o90Units = 0;

        for (Opportunity opp : [
            SELECT Id, Name, StageName, Projected_Close_Date__c, Units__c,
                   Account.Name, Owner.Name,
                   (SELECT Id, Agreement_Type__c, Status__c FROM Agreements__r)
            FROM Opportunity
            WHERE RecordType.DeveloperName = 'MDU'
              AND Projected_Close_Date__c != null
              AND StageName IN :stages
              AND Owner.Name = :ownerName
              AND IsClosed = FALSE
            ORDER BY Projected_Close_Date__c ASC
        ]) {
            PipelineDetail pd = new PipelineDetail();
            pd.id            = opp.Id;
            pd.name          = opp.Name;
            pd.stage         = opp.StageName;
            pd.closeDate     = opp.Projected_Close_Date__c;
            pd.units         = opp.Units__c != null ? opp.Units__c.intValue() : 0;
            pd.accountName   = opp.Account != null ? opp.Account.Name : '';
            pd.ownerName     = opp.Owner   != null ? opp.Owner.Name   : '';
            pd.agreementCount = opp.Agreements__r != null ? opp.Agreements__r.size() : 0;

            if (opp.Projected_Close_Date__c < today) {
                lf.pastDueDetails.add(pd);
                pdUnits += pd.units;
            } else if (opp.Projected_Close_Date__c <= in90Days) {
                lf.next90Details.add(pd);
                n90Units += pd.units;
            } else {
                lf.over90Details.add(pd);
                o90Units += pd.units;
            }
        }

        lf.pastDueCount = lf.pastDueDetails.size();
        lf.next90Count  = lf.next90Details.size();
        lf.over90Count  = lf.over90Details.size();
        lf.pastDueUnits = pdUnits;
        lf.next90Units  = n90Units;
        lf.over90Units  = o90Units;
        return lf;
    }

    public class ExecutiveDashboardData {
        @AuraEnabled public List<FunnelStage> funnelStages;
        @AuraEnabled public Integer totalPipeline;
        @AuraEnabled public Integer totalCompleted;
        @AuraEnabled public Integer totalSignedYTD;
        @AuraEnabled public List<MonthlyCount> completedByMonth;
        @AuraEnabled public List<SiteTrackerSummary> inProgressSiteTrackers;
        @AuraEnabled public Integer inProgressSiteTrackerCount;
        // Lane forecasts (new)
        @AuraEnabled public LaneForecast palForecast;
        @AuraEnabled public LaneForecast emaBulkForecast;
        @AuraEnabled public LaneForecast saqForecast;
        // Backward-compat aggregate fields
        @AuraEnabled public Integer pastDueCount;
        @AuraEnabled public Integer next90DaysCount;
        @AuraEnabled public Integer over90DaysCount;
        @AuraEnabled public List<PipelineDetail> pastDueDetails;
        @AuraEnabled public List<PipelineDetail> next90DaysDetails;
        @AuraEnabled public List<PipelineDetail> over90DaysDetails;
    }

    public class LaneForecast {
        @AuraEnabled public String ownerName;
        @AuraEnabled public Integer pastDueCount;
        @AuraEnabled public Integer next90Count;
        @AuraEnabled public Integer over90Count;
        @AuraEnabled public Integer pastDueUnits;
        @AuraEnabled public Integer next90Units;
        @AuraEnabled public Integer over90Units;
        @AuraEnabled public List<PipelineDetail> pastDueDetails;
        @AuraEnabled public List<PipelineDetail> next90Details;
        @AuraEnabled public List<PipelineDetail> over90Details;
    }

    public class FunnelStage {
        @AuraEnabled public String stage;
        @AuraEnabled public Integer count;
        @AuraEnabled public Integer units;
    }

    public class MonthlyCount {
        @AuraEnabled public Integer month;
        @AuraEnabled public String monthName;
        @AuraEnabled public Integer count;
    }

    public class PipelineDetail {
        @AuraEnabled public String id;
        @AuraEnabled public String name;
        @AuraEnabled public String stage;
        @AuraEnabled public Date closeDate;
        @AuraEnabled public Integer units;
        @AuraEnabled public String accountName;
        @AuraEnabled public String ownerName;
        @AuraEnabled public Integer agreementCount;
    }
}