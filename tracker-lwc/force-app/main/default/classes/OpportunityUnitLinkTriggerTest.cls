@isTest
private class OpportunityUnitLinkTriggerTest {

    private static Property_Location__c makePL() {
        Property_Location__c pl = new Property_Location__c(Name = 'TEST 100 MAIN ST');
        insert pl;
        return pl;
    }

    private static Property_Unit__c makeUnit(Id plId, String label) {
        Property_Unit__c u = new Property_Unit__c(
            Property_Location__c = plId,
            Unit__c = label
        );
        insert u;
        return u;
    }

    private static Opportunity makeOpp(Id unitId) {
        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
        return new Opportunity(
            Name = 'TEST OPP ' + (unitId == null ? 'NO_UNIT' : String.valueOf(unitId).right(6)),
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            Property_Unit__c = unitId,
            RecordTypeId = mduRtId
        );
    }

    @isTest
    static void insert_withUnit_setsReverseLink() {
        Property_Location__c pl = makePL();
        Property_Unit__c u = makeUnit(pl.Id, 'UNIT 101');

        Test.startTest();
        Opportunity opp = makeOpp(u.Id);
        insert opp;
        Test.stopTest();

        Property_Unit__c reloaded = [SELECT Opportunity__c FROM Property_Unit__c WHERE Id = :u.Id];
        System.assertEquals(opp.Id, reloaded.Opportunity__c, 'Unit should be auto-linked to Opp');
    }

    @isTest
    static void insert_withoutUnit_doesNotError() {
        Test.startTest();
        Opportunity opp = makeOpp(null);
        insert opp;
        Test.stopTest();
        // No assertion needed — just verifying no exception
    }

    @isTest
    static void update_changesUnit_updatesNewUnitLink() {
        Property_Location__c pl = makePL();
        Property_Unit__c u1 = makeUnit(pl.Id, 'UNIT 101');
        Property_Unit__c u2 = makeUnit(pl.Id, 'UNIT 102');
        Opportunity opp = makeOpp(u1.Id);
        insert opp;

        Property_Unit__c u1Reload = [SELECT Opportunity__c FROM Property_Unit__c WHERE Id = :u1.Id];
        System.assertEquals(opp.Id, u1Reload.Opportunity__c);

        Test.startTest();
        opp.Property_Unit__c = u2.Id;
        update opp;
        Test.stopTest();

        Property_Unit__c u2Reload = [SELECT Opportunity__c FROM Property_Unit__c WHERE Id = :u2.Id];
        System.assertEquals(opp.Id, u2Reload.Opportunity__c, 'New Unit should now link to Opp');
    }

    @isTest
    static void bulk_insert_handlesManyOpps() {
        Property_Location__c pl = makePL();
        List<Property_Unit__c> units = new List<Property_Unit__c>();
        for (Integer i = 0; i < 50; i++) {
            units.add(new Property_Unit__c(Property_Location__c = pl.Id, Unit__c = 'UNIT ' + i));
        }
        insert units;

        List<Opportunity> opps = new List<Opportunity>();
        for (Property_Unit__c u : units) {
            opps.add(makeOpp(u.Id));
        }

        Test.startTest();
        insert opps;
        Test.stopTest();

        List<Property_Unit__c> reloaded = [
            SELECT Opportunity__c FROM Property_Unit__c WHERE Id IN :units
        ];
        Integer linked = 0;
        for (Property_Unit__c r : reloaded) {
            if (r.Opportunity__c != null) {
                linked++;
            }
        }
        System.assertEquals(50, linked, 'All 50 Units should have been auto-linked');
    }
}
