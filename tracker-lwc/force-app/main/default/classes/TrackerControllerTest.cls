@isTest
private class TrackerControllerTest {

    @TestSetup
    static void setup() {
        // Create a test view
        Tracker_View__c view = new Tracker_View__c();
        view.Name = 'Test Pipeline';
        view.Object__c = 'Opportunity';
        view.Is_Active__c = true;
        view.Sort_Order__c = 1;
        view.Config__c = '{"columns":[{"field":"Name","label":"Name","width":200,"editable":false},{"field":"StageName","label":"Stage","width":150,"editable":true},{"field":"Amount","label":"Amount","width":120,"editable":true},{"field":"CloseDate","label":"Close Date","width":120,"editable":true}],"sort":{"field":"CloseDate","direction":"ASC"},"filters":[],"record_limit":10}';
        insert view;

        // Create test Account + Opportunity
        Account acc = new Account(Name = 'Test Account');
        insert acc;

        Opportunity opp = new Opportunity(
            Name = 'Test Opp',
            AccountId = acc.Id,
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Amount = 10000
        );
        insert opp;
    }

    @isTest
    static void testGetActiveViews() {
        List<Tracker_View__c> views = TrackerController.getActiveViews();
        System.assertEquals(1, views.size(), 'Should return 1 active view');
        System.assertEquals('Test Pipeline', views[0].Name);
    }

    @isTest
    static void testGetTrackerData() {
        Tracker_View__c view = [SELECT Id FROM Tracker_View__c LIMIT 1];
        TrackerController.TrackerResult result = TrackerController.getTrackerData(view.Id);
        System.assertNotEquals(null, result.viewConfig);
        System.assert(result.records.size() > 0, 'Should return at least 1 record');
    }

    @isTest
    static void testSaveRecords() {
        Opportunity opp = [SELECT Id, Name FROM Opportunity LIMIT 1];
        opp.Name = 'Updated Test Opp';
        List<TrackerController.SaveResultWrapper> results = TrackerController.saveRecords(
            new List<SObject>{ opp }
        );
        System.assertEquals(1, results.size());
        System.assertEquals(true, results[0].success);
    }

    @isTest
    static void testGetTrackerDataWithFilters() {
        Tracker_View__c view = [SELECT Id FROM Tracker_View__c LIMIT 1];
        // Update config with filters
        view.Config__c = '{"columns":[{"field":"Name","label":"Name","width":200}],"sort":{"field":"Name","direction":"ASC"},"filters":[{"field":"StageName","operator":"not_in","value":["Closed Won","Closed Lost"]},{"field":"StageName","operator":"equals","value":"Prospecting"}],"record_limit":10}';
        update view;

        TrackerController.TrackerResult result = TrackerController.getTrackerData(view.Id);
        System.assertNotEquals(null, result);
    }

    @isTest
    static void testAllFilterOperators() {
        Tracker_View__c view = [SELECT Id FROM Tracker_View__c LIMIT 1];
        // Test not_equals, in_list, less_than (TODAY), greater_than (TODAY)
        view.Config__c = '{"columns":[{"field":"Name","label":"Name","width":200}],"sort":{"field":"Name","direction":"ASC"},"filters":[{"field":"StageName","operator":"not_equals","value":"Closed Won"},{"field":"StageName","operator":"in_list","value":["Prospecting","Qualification"]},{"field":"CloseDate","operator":"greater_than","value":"TODAY"},{"field":"Amount","operator":"less_than","value":"999999"}],"record_limit":10}';
        update view;

        TrackerController.TrackerResult result = TrackerController.getTrackerData(view.Id);
        System.assertNotEquals(null, result);
    }

    @isTest
    static void testCurrentUserFilter() {
        Tracker_View__c view = [SELECT Id FROM Tracker_View__c LIMIT 1];
        view.Config__c = '{"columns":[{"field":"Name","label":"Name","width":200}],"filters":[{"field":"OwnerId","operator":"equals","value":"CURRENT_USER"}],"record_limit":10}';
        update view;

        TrackerController.TrackerResult result = TrackerController.getTrackerData(view.Id);
        System.assertNotEquals(null, result);
    }

    @isTest
    static void testGetNotesForRecord() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];
        List<TrackerController.NoteWrapper> notes = TrackerController.getNotesForRecord(opp.Id);
        // No notes in test data, just verify it runs
        System.assertNotEquals(null, notes);
    }

    @isTest
    static void testCreateAndGetNotes() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];

        String noteId = TrackerController.createNote(opp.Id, 'Test Note', 'Test body content');
        System.assertNotEquals(null, noteId);

        List<TrackerController.NoteWrapper> notes = TrackerController.getNotesForRecord(opp.Id);
        System.assertEquals(1, notes.size());
        System.assertEquals('Test Note', notes[0].title);

        // Test paged notes
        List<TrackerController.NoteWrapper> pagedNotes = TrackerController.getNotesForRecordPaged(opp.Id, 5, 0);
        System.assertEquals(1, pagedNotes.size());
    }

    @isTest
    static void testGetPicklistValues() {
        Map<String, List<TrackerController.PicklistOption>> result = TrackerController.getPicklistValues('Opportunity');
        System.assert(result.containsKey('StageName'), 'Should contain StageName picklist');
        System.assert(result.get('StageName').size() > 0, 'StageName should have values');
    }

    @isTest
    static void testGetActiveUsers() {
        List<TrackerController.OwnerOption> users = TrackerController.getActiveUsers();
        System.assert(users.size() > 0, 'Should return at least 1 active user');
    }

    @isTest
    static void testGetActivitiesForRecord() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];
        // Create a task
        Task t = new Task(Subject = 'Test Call', WhatId = opp.Id, Status = 'Open', Priority = 'Normal');
        insert t;
        // Create an event
        Event e = new Event(Subject = 'Test Meeting', WhatId = opp.Id, StartDateTime = Datetime.now(), EndDateTime = Datetime.now().addHours(1));
        insert e;

        List<TrackerController.ActivityWrapper> activities = TrackerController.getActivitiesForRecord(opp.Id);
        System.assert(activities.size() >= 2, 'Should return at least 2 activities');

        // Test paged method
        List<TrackerController.ActivityWrapper> paged = TrackerController.getActivitiesForRecordPaged(opp.Id, 5, 0);
        System.assert(paged.size() >= 2, 'Paged should also return activities');

        // Test toggling task status
        TrackerController.updateTaskStatus(t.Id, 'Completed');
        Task updated = [SELECT Status FROM Task WHERE Id = :t.Id];
        System.assertEquals('Completed', updated.Status);

        TrackerController.updateTaskStatus(t.Id, 'Open');
        updated = [SELECT Status FROM Task WHERE Id = :t.Id];
        System.assertEquals('Open', updated.Status);
    }

    @isTest
    static void testCreateActivity() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];

        // Log a Call - no due date, no priority, auto-completes
        String callId = TrackerController.createActivity(opp.Id, 'Call', 'Follow-up call', null, null, 'Discussed next steps', null, null, null, null);
        System.assertNotEquals(null, callId);
        Task callTask = [SELECT Status, ActivityDate FROM Task WHERE Id = :callId];
        System.assertEquals('Completed', callTask.Status);
        System.assertEquals(Date.today(), callTask.ActivityDate);

        // New Task - has due date and priority
        String taskId = TrackerController.createActivity(opp.Id, 'Task', 'Send proposal', String.valueOf(Date.today().addDays(7)), 'High', null, null, null, null, null);
        System.assertNotEquals(null, taskId);
        Task newTask = [SELECT Status, Priority FROM Task WHERE Id = :taskId];
        System.assertEquals('Open', newTask.Status);
        System.assertEquals('High', newTask.Priority);

        // New Event - has start/end time and location
        String eventId = TrackerController.createActivity(opp.Id, 'Meeting', 'Site visit', null, null, 'Walk the property', String.valueOf(Date.today()), '14:00', '15:30', 'Main Office');
        System.assertNotEquals(null, eventId);
        Event evt = [SELECT Location FROM Event WHERE Id = :eventId];
        System.assertEquals('Main Office', evt.Location);
    }

    @isTest
    static void testGetAgreementPicklists() {
        Map<String, List<TrackerController.PicklistOption>> result = TrackerController.getAgreementPicklists();
        System.assert(result.containsKey('Agreement_Type__c'), 'Should contain Agreement_Type__c');
        System.assert(result.containsKey('Status__c'), 'Should contain Status__c');
    }

    @isTest
    static void testCreateAndGetAgreements() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];

        String agrId = TrackerController.createAgreement(opp.Id, 'PAL', 'Not Started', String.valueOf(Date.today()), 'Test notes');
        System.assertNotEquals(null, agrId);

        List<TrackerController.AgreementWrapper> agreements = TrackerController.getAgreementsForRecord(opp.Id);
        System.assertEquals(1, agreements.size());
        System.assertEquals('PAL', agreements[0].agreementType);
        System.assertEquals('Not Started', agreements[0].status);
    }

    @isTest
    static void testUpdateAgreement() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];
        String agrId = TrackerController.createAgreement(opp.Id, 'ROE', 'Not Started', null, null);

        TrackerController.updateAgreement(agrId, 'ROE', 'Signed', null, String.valueOf(Date.today()), null, 'Updated notes');

        List<TrackerController.AgreementWrapper> agreements = TrackerController.getAgreementsForRecord(opp.Id);
        System.assertEquals('Signed', agreements[0].status);
        System.assertEquals('Updated notes', agreements[0].notes);
    }

    @isTest
    static void testGetContactsForRecord() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];
        List<TrackerController.ContactWrapper> contacts = TrackerController.getContactsForRecord(opp.Id);
        System.assertNotEquals(null, contacts);
    }

    @isTest
    static void testGetContactRoleOptions() {
        List<TrackerController.PicklistOption> opts = TrackerController.getContactRoleOptions();
        System.assert(opts.size() > 0, 'Should return role picklist values');
    }

    @isTest
    static void testCreateAndLinkContact() {
        Opportunity opp = [SELECT Id FROM Opportunity LIMIT 1];

        String contactId = TrackerController.createAndLinkContact(
            opp.Id, 'Test', 'NewContact', 'test@example.com', '555-1234', 'Other', 'Assistant'
        );
        System.assertNotEquals(null, contactId);

        List<TrackerController.ContactWrapper> contacts = TrackerController.getContactsForRecord(opp.Id);
        System.assertEquals(1, contacts.size());
        System.assertEquals('Test NewContact', contacts[0].name);
    }
}
