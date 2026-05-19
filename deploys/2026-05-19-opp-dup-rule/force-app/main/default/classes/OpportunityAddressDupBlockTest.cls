@isTest
private class OpportunityAddressDupBlockTest {

    private static Id mduRecordTypeId() {
        return Schema.SObjectType.Opportunity
            .getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
    }

    private static Opportunity makeOpp(String name, String addr, String city, String state, String zip) {
        return new Opportunity(
            Name = name,
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_Address__c = addr,
            Property_City__c = city,
            Property_State__c = state,
            Property_Zip__c = zip,
            RecordTypeId = mduRecordTypeId()
        );
    }

    @isTest
    static void insert_uniqueAddress_succeeds() {
        Test.startTest();
        insert makeOpp('UNIQ', '100 MAIN ST', 'MESA', 'AZ', '85210');
        Test.stopTest();
        System.assertEquals(1, [SELECT COUNT() FROM Opportunity WHERE Name = 'UNIQ']);
    }

    @isTest
    static void insert_exactDupAddress_blocked() {
        insert makeOpp('EXISTING', '200 MAIN ST', 'MESA', 'AZ', '85210');

        Test.startTest();
        Boolean blocked = false;
        try {
            insert makeOpp('DUP', '200 MAIN ST', 'MESA', 'AZ', '85210');
        } catch (DmlException e) {
            blocked = true;
            System.assert(e.getMessage().contains('already exists at this property address'),
                'Error message should describe the dup. Got: ' + e.getMessage());
        }
        Test.stopTest();
        System.assert(blocked, 'Dup insert should have been blocked');
    }

    @isTest
    static void insert_caseAndWhitespaceDifferent_blocked() {
        insert makeOpp('EXISTING', '300 MAIN ST', 'Mesa', 'AZ', '85210');

        Test.startTest();
        Boolean blocked = false;
        try {
            insert makeOpp('DUP', '  300 main st  ', 'mesa', 'AZ', '85210');
        } catch (DmlException e) {
            blocked = true;
        }
        Test.stopTest();
        System.assert(blocked, 'Case/whitespace variant should still be detected as dup');
    }

    @isTest
    static void insert_dirtyExistingAddress_matchesCleanNew() {
        // Mirrors real org data: existing has city/state/zip embedded in address.
        insert makeOpp('EXISTING_DIRTY',
            '1942 South Emerson, Mesa, AZ 85210', 'Mesa', 'AZ', '85210');

        Test.startTest();
        Boolean blocked = false;
        try {
            // New record has the clean form.
            insert makeOpp('DUP_CLEAN',
                '1942 South Emerson', 'Mesa', 'AZ', '85210');
        } catch (DmlException e) {
            blocked = true;
            System.assert(e.getMessage().contains('1942 South Emerson')
                       || e.getMessage().contains('already exists'),
                'Error should reference dup. Got: ' + e.getMessage());
        }
        Test.stopTest();
        System.assert(blocked,
            'Dirty-addr existing should match clean-addr new on core+zip key');
    }

    @isTest
    static void insert_sameStreetDifferentZip_notBlocked() {
        // Same street name in two different zips should NOT block.
        insert makeOpp('A_ZIP1', '500 OAK ST', 'MESA', 'AZ', '85210');

        Test.startTest();
        // Note: different zip
        insert makeOpp('B_ZIP2', '500 OAK ST', 'MESA', 'AZ', '85211');
        Test.stopTest();
        System.assertEquals(1, [SELECT COUNT() FROM Opportunity WHERE Name = 'B_ZIP2']);
    }

    @isTest
    static void update_noAddressChange_doesNotBlock() {
        Opportunity existing = makeOpp('EXISTING', '600 MAIN ST', 'MESA', 'AZ', '85210');
        insert existing;

        Test.startTest();
        existing.Name = 'EXISTING RENAMED';
        update existing;
        Test.stopTest();
        System.assertEquals(1, [SELECT COUNT() FROM Opportunity WHERE Name = 'EXISTING RENAMED']);
    }

    @isTest
    static void update_addressChangedToCollision_blocked() {
        insert makeOpp('A_BUILDING', '700 MAIN ST', 'MESA', 'AZ', '85210');
        Opportunity b = makeOpp('B_BUILDING', '701 MAIN ST', 'MESA', 'AZ', '85210');
        insert b;

        Test.startTest();
        b.Property_Address__c = '700 MAIN ST';   // collide with A_BUILDING
        Boolean blocked = false;
        try {
            update b;
        } catch (DmlException e) {
            blocked = true;
        }
        Test.stopTest();
        System.assert(blocked, 'Address change creating a collision should be blocked');
    }

    @isTest
    static void bulk_mix_blocksDupsLetsUniquesThrough() {
        insert makeOpp('EXISTING', '800 MAIN ST', 'MESA', 'AZ', '85210');

        List<Opportunity> batch = new List<Opportunity>();
        for (Integer i = 0; i < 5; i++) {
            batch.add(makeOpp('UNIQ_' + i, (900 + i) + ' MAIN ST', 'MESA', 'AZ', '85210'));
        }
        batch.add(makeOpp('DUP_OF_800', '800 MAIN ST', 'MESA', 'AZ', '85210'));

        Test.startTest();
        Database.SaveResult[] results = Database.insert(batch, false);
        Test.stopTest();

        Integer ok = 0, fail = 0;
        for (Database.SaveResult sr : results) {
            if (sr.isSuccess()) ok++; else fail++;
        }
        System.assertEquals(5, ok, 'The 5 unique inserts should succeed');
        System.assertEquals(1, fail, 'The dup insert should fail');
    }

    @isTest
    static void helper_norm_normalises() {
        // Hits coreAddress + norm via normKey (their @TestVisible private setters).
        System.assertEquals('1942 SOUTH EMERSON|85210',
            OpportunityAddressDupHelper.normKey('  1942 south emerson, MESA, az 85210  ', '85210'));
        System.assertEquals('|',
            OpportunityAddressDupHelper.normKey(null, null));
    }
}
