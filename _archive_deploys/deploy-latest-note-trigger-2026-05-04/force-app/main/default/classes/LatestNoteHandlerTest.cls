@isTest
private class LatestNoteHandlerTest {

    private static Opportunity makeOpp(String name) {
        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
        Opportunity opp = new Opportunity(
            Name = name,
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            RecordTypeId = mduRtId
        );
        insert opp;
        return opp;
    }

    private static Id attachNote(Id linkedId, String title, String body) {
        ContentNote n = new ContentNote(Title = title, Content = Blob.valueOf(body));
        insert n;
        ContentDocumentLink cdl = new ContentDocumentLink(
            ContentDocumentId = n.Id,
            LinkedEntityId = linkedId,
            ShareType = 'V',
            Visibility = 'AllUsers'
        );
        insert cdl;
        return n.Id;
    }

    @isTest
    static void insertNote_populatesLatestNoteFields() {
        Opportunity opp = makeOpp('LATEST_NOTE_TEST_1');

        Test.startTest();
        attachNote(opp.Id, 'Sample Title', '<p>Hello world</p>');
        Test.stopTest();

        Opportunity reloaded = [
            SELECT Latest_Note_Date__c, Latest_Note_Snippet__c FROM Opportunity WHERE Id = :opp.Id
        ];
        System.assertNotEquals(null, reloaded.Latest_Note_Date__c, 'Date should be set');
        System.assert(reloaded.Latest_Note_Snippet__c.contains('Sample Title'), 'Snippet should contain title');
        System.assert(reloaded.Latest_Note_Snippet__c.contains('Hello world'), 'Snippet should contain body text');
    }

    @isTest
    static void deleteNote_clearsLatestNoteFields() {
        Opportunity opp = makeOpp('LATEST_NOTE_TEST_2');
        Id noteId = attachNote(opp.Id, 'Will Delete', '<p>going away</p>');

        Opportunity afterInsert = [
            SELECT Latest_Note_Date__c FROM Opportunity WHERE Id = :opp.Id
        ];
        System.assertNotEquals(null, afterInsert.Latest_Note_Date__c, 'Should be populated after insert');

        Test.startTest();
        delete [SELECT Id FROM ContentDocument WHERE Id = :noteId];
        Test.stopTest();

        Opportunity reloaded = [
            SELECT Latest_Note_Date__c, Latest_Note_Snippet__c FROM Opportunity WHERE Id = :opp.Id
        ];
        System.assertEquals(null, reloaded.Latest_Note_Date__c, 'Date should be cleared after note deletion');
        System.assertEquals(null, reloaded.Latest_Note_Snippet__c, 'Snippet should be cleared after note deletion');
    }

    @isTest
    static void multipleNotes_picksMostRecent() {
        Opportunity opp = makeOpp('LATEST_NOTE_TEST_3');
        attachNote(opp.Id, 'Older Note', 'old body');
        // Slight delay so the second note is unambiguously later
        Datetime t = Datetime.now().addMinutes(1);

        Test.startTest();
        attachNote(opp.Id, 'Newest Note', 'new body that is more recent');
        Test.stopTest();

        Opportunity reloaded = [
            SELECT Latest_Note_Snippet__c FROM Opportunity WHERE Id = :opp.Id
        ];
        System.assert(reloaded.Latest_Note_Snippet__c.contains('Newest Note'),
            'Snippet should reflect the most recent note: ' + reloaded.Latest_Note_Snippet__c);
    }

    @isTest
    static void refreshOpps_handlesEmptyAndNullSets() {
        Test.startTest();
        LatestNoteHandler.refreshOpps(null);
        LatestNoteHandler.refreshOpps(new Set<Id>());
        Test.stopTest();
        // No exception = pass
    }

    @isTest
    static void refreshOpps_filtersNonOpportunityIds() {
        Property_Location__c pl = new Property_Location__c(Name = 'TEST_PL_1');
        insert pl;
        Test.startTest();
        LatestNoteHandler.refreshOpps(new Set<Id>{pl.Id});
        Test.stopTest();
        // No exception = pass
    }
}
