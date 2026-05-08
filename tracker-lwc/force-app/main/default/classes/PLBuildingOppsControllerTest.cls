@isTest
private class PLBuildingOppsControllerTest {

    @isTest
    static void getBuildingOpps_returnsOnlyOppsWithoutUnit() {
        Property_Location__c pl = new Property_Location__c(Name = 'TEST PL 100');
        insert pl;

        Property_Unit__c unit = new Property_Unit__c(
            Property_Location__c = pl.Id,
            Unit__c = 'UNIT 1'
        );
        insert unit;

        Id mduRtId = Schema.SObjectType.Opportunity.getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();

        Opportunity buildingOpp = new Opportunity(
            Name = 'BUILDING ROE TEST',
            StageName = 'Engaged',
            CloseDate = Date.today().addDays(60),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            Property_Location__c = pl.Id,
            RecordTypeId = mduRtId
        );
        Opportunity unitOpp = new Opportunity(
            Name = 'UNIT 1 OPP',
            StageName = 'Engaged',
            CloseDate = Date.today().addDays(60),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'TESTVILLE',
            Property_State__c = 'AZ',
            Property_Zip__c = '85202',
            Property_Location__c = pl.Id,
            Property_Unit__c = unit.Id,
            RecordTypeId = mduRtId
        );
        insert new List<Opportunity>{ buildingOpp, unitOpp };

        Test.startTest();
        List<PLBuildingOppsController.OppRow> rows =
            PLBuildingOppsController.getBuildingOpps(pl.Id);
        Test.stopTest();

        System.assertEquals(1, rows.size(), 'should return only the building-level Opp');
        System.assertEquals('BUILDING ROE TEST', rows[0].name);
        System.assertEquals('Engaged', rows[0].stage);
    }

    @isTest
    static void getBuildingOpps_handlesEmpty() {
        Property_Location__c pl = new Property_Location__c(Name = 'EMPTY PL');
        insert pl;
        Test.startTest();
        List<PLBuildingOppsController.OppRow> rows =
            PLBuildingOppsController.getBuildingOpps(pl.Id);
        Test.stopTest();
        System.assertEquals(0, rows.size());
    }

    @isTest
    static void getBuildingOpps_handlesNull() {
        Test.startTest();
        List<PLBuildingOppsController.OppRow> rows =
            PLBuildingOppsController.getBuildingOpps(null);
        Test.stopTest();
        System.assertEquals(0, rows.size());
    }
}
