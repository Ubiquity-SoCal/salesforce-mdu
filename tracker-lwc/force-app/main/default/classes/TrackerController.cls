public with sharing class TrackerController {

    @AuraEnabled(cacheable=true)
    public static List<Tracker_View__c> getActiveViews() {
        return [
            SELECT Id, Name, Config__c, Object__c, Is_Active__c, Sort_Order__c
            FROM Tracker_View__c
            WHERE Is_Active__c = true
            ORDER BY Sort_Order__c ASC NULLS LAST, Name ASC
        ];
    }

    @AuraEnabled
    public static TrackerResult getTrackerData(String viewId) {
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

        // Build field list and track relationship fields
        // Always include Notes_Count__c for notes icon, OwnerId for owner editing
        Set<String> directFields = new Set<String>{'Id', 'Notes_Count__c', 'OwnerId'};
        Set<String> relationshipFields = new Set<String>();

        for (Object col : columns) {
            Map<String, Object> colMap = (Map<String, Object>) col;
            String field = (String) colMap.get('field');
            if (field.contains('.')) {
                // Relationship field — convert dot notation for SOQL
                // e.g., Account.Name stays as Account.Name in SOQL
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

        if (!whereClauses.isEmpty()) {
            soql += ' WHERE ' + String.join(whereClauses, ' AND ');
        }

        // Sort
        if (sortConfig != null) {
            String sortField = (String) sortConfig.get('field');
            String sortDir = (String) sortConfig.get('direction');
            soql += ' ORDER BY ' + sortField + ' ' + sortDir + ' NULLS LAST';
        }

        // Limit
        soql += ' LIMIT ' + recordLimit;

        result.records = Database.query(soql);
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
}
