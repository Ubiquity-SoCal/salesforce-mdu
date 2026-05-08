@isTest
private class PropertyLocationSummaryControllerTest {

    @isTest
    static void getSummary_returnsCountsForLinkedPL() {
        // Property_Unit_Count__c and Active_Unit_Count__c are read-only rollups; we don't set them.
        Property_Location__c pl = new Property_Location__c(
            Name = 'TEST 100 MAIN ST'
        );
        insert pl;

        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
        Opportunity opp1 = new Opportunity(
            Name = 'TEST OPP 1',
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            Property_Location__c = pl.Id,
            RecordTypeId = mduRtId
        );
        Opportunity opp2 = new Opportunity(
            Name = 'TEST OPP 2',
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            Property_Location__c = pl.Id,
            RecordTypeId = mduRtId
        );
        insert new List<Opportunity>{ opp1, opp2 };

        Test.startTest();
        PropertyLocationSummaryController.Summary s =
            PropertyLocationSummaryController.getSummary(opp1.Id);
        Test.stopTest();

        System.assertEquals(pl.Id, s.plId, 'plId should match linked PL');
        System.assertEquals('TEST 100 MAIN ST', s.plName);
        System.assertEquals(2, s.oppCount, 'should count both Opps on the PL');
    }

    @isTest
    static void getSummary_returnsEmptyWhenNoPL() {
        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
        Opportunity opp = new Opportunity(
            Name = 'NO PL OPP',
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            RecordTypeId = mduRtId
        );
        insert opp;

        Test.startTest();
        PropertyLocationSummaryController.Summary s =
            PropertyLocationSummaryController.getSummary(opp.Id);
        Test.stopTest();

        System.assertEquals(null, s.plId);
        System.assertEquals(null, s.oppCount);
    }

    @isTest
    static void getSummary_handlesNullId() {
        Test.startTest();
        PropertyLocationSummaryController.Summary s =
            PropertyLocationSummaryController.getSummary(null);
        Test.stopTest();
        System.assertEquals(null, s.plId);
    }
}
