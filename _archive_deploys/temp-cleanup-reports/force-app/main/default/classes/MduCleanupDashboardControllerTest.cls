@IsTest
private class MduCleanupDashboardControllerTest {

    @TestSetup
    static void setup() {
        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();

        List<Opportunity> opps = new List<Opportunity>();

        // Active Opp: Engaged, missing Property Location, no Projected Close
        Opportunity o1 = new Opportunity(
            Name = 'Test Engaged No PL',
            StageName = 'Engaged',
            CloseDate = Date.today().addDays(60),
            RecordTypeId = mduRtId,
            Property_City__c = 'Test City',
            Property_State__c = 'CA',
            Property_Zip__c = '90001'
        );
        opps.add(o1);

        // Active Opp: ROE Secured, no RE assigned, no projected close
        Opportunity o2 = new Opportunity(
            Name = 'Test ROE Secured',
            StageName = 'ROE Secured',
            CloseDate = Date.today().addDays(90),
            RecordTypeId = mduRtId,
            Property_City__c = 'Test City',
            Property_State__c = 'CA',
            Property_Zip__c = '90002'
        );
        opps.add(o2);

        // Under Contract Opp without signed PAL
        Opportunity o3 = new Opportunity(
            Name = 'Test Under Contract No PAL',
            StageName = 'Under Contract',
            CloseDate = Date.today().addDays(30),
            RecordTypeId = mduRtId,
            Property_City__c = 'Test City',
            Property_State__c = 'CA',
            Property_Zip__c = '90003'
        );
        opps.add(o3);

        insert opps;

        // Agreements with various statuses, none with IronClad ID
        List<Agreement__c> agrs = new List<Agreement__c>{
            new Agreement__c(
                Opportunity__c = o1.Id,
                Agreement_Type__c = 'PAL',
                Status__c = 'Completed',
                Signed_Date__c = Date.today().addDays(-30)
            ),
            new Agreement__c(
                Opportunity__c = o2.Id,
                Agreement_Type__c = 'EMA',
                Status__c = 'Sign'
            ),
            new Agreement__c(
                Opportunity__c = o3.Id,
                Agreement_Type__c = 'EMA',
                Status__c = 'Review'
            )
        };
        insert agrs;
    }

    @IsTest
    static void smokeTest() {
        Test.startTest();
        List<MduCleanupDashboardController.CleanupCategory> cats =
            MduCleanupDashboardController.getCleanupSummary();
        Test.stopTest();

        System.assertNotEquals(null, cats);
        System.assert(cats.size() >= 7, 'Expected at least 7 cleanup categories');

        Map<String, MduCleanupDashboardController.CleanupCategory> byKey =
            new Map<String, MduCleanupDashboardController.CleanupCategory>();
        for (MduCleanupDashboardController.CleanupCategory c : cats) {
            System.assertNotEquals(null, c.key);
            System.assertNotEquals(null, c.label);
            System.assertNotEquals(null, c.count);
            System.assertNotEquals(null, c.severity);
            byKey.put(c.key, c);
        }

        System.assert(byKey.containsKey('ic_high'), 'expected ic_high');
        System.assert(byKey.containsKey('ic_med'),  'expected ic_med');
        System.assert(byKey.containsKey('no_property_location'), 'expected no_property_location');
        System.assert(byKey.containsKey('no_re'), 'expected no_re');
        System.assert(byKey.containsKey('no_close'), 'expected no_close');
        System.assert(byKey.containsKey('under_contract_no_pal'), 'expected under_contract_no_pal');
        System.assert(byKey.containsKey('stale'), 'expected stale');

        // The seeded Completed PAL with no IronClad ID should land in ic_high
        System.assert(byKey.get('ic_high').count >= 1, 'expected at least one ic_high row');
        // The seeded Sign EMA should land in ic_med
        System.assert(byKey.get('ic_med').count >= 1, 'expected at least one ic_med row');
        // Under Contract opp without signed PAL should land in under_contract_no_pal
        System.assert(byKey.get('under_contract_no_pal').count >= 1, 'expected at least one under_contract_no_pal row');

        // Verify a row has expected fields populated
        MduCleanupDashboardController.CleanupCategory ic = byKey.get('ic_high');
        if (ic.count > 0) {
            MduCleanupDashboardController.CleanupRow r = ic.rows[0];
            System.assertNotEquals(null, r.recordId);
            System.assertEquals('Agreement', r.recordType);
        }
    }
}
