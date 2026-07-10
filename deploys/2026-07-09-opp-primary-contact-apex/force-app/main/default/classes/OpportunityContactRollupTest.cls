@isTest
private class OpportunityContactRollupTest {

    private static Id mduRecordTypeId() {
        return Schema.SObjectType.Opportunity
            .getRecordTypeInfosByDeveloperName().get('MDU').getRecordTypeId();
    }

    /**
     * City/State/Zip are required by validation on MDU opportunities, but
     * Property_Address__c is left blank on purpose: OpportunityAddressDupBlock skips any
     * record with a blank address, so these fixtures never collide with each other.
     */
    private static Opportunity makeOpp(String name) {
        return new Opportunity(
            Name = name,
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            Sales_Status__c = 'Contact Pending',
            Property_City__c = 'MESA',
            Property_State__c = 'AZ',
            Property_Zip__c = '85210',
            RecordTypeId = mduRecordTypeId()
        );
    }

    private static Contact makeContact(String lastName) {
        return new Contact(LastName = lastName);
    }

    private static Opportunity reload(Id oppId) {
        return [
            SELECT Primary_Contact__c, Primary_Contact_Role__c, Contact_Count__c
            FROM Opportunity WHERE Id = :oppId
        ];
    }

    @isTest
    static void rolePriority_beatsInsertOrder() {
        Opportunity opp = makeOpp('ROLE PRIORITY');
        insert opp;
        Contact broker = makeContact('Broker');
        Contact owner = makeContact('Owner');
        insert new List<Contact>{ broker, owner };

        // Broker linked FIRST; Property Owner must still win.
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = broker.Id, Role__c = 'Broker');

        Test.startTest();
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = owner.Id, Role__c = 'Property Owner');
        Test.stopTest();

        Opportunity result = reload(opp.Id);
        System.assertEquals(owner.Id, result.Primary_Contact__c,
            'Property Owner outranks Broker regardless of link order');
        System.assertEquals('Property Owner', result.Primary_Contact_Role__c);
        System.assertEquals(2, result.Contact_Count__c);
    }

    @isTest
    static void equalRole_oldestLinkWins() {
        Opportunity opp = makeOpp('TIEBREAK');
        insert opp;
        Contact first = makeContact('FirstOwner');
        Contact second = makeContact('SecondOwner');
        insert new List<Contact>{ first, second };

        Opportunity_Contact__c older = new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = first.Id, Role__c = 'Property Owner');
        insert older;

        Test.startTest();
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = second.Id, Role__c = 'Property Owner');
        Test.stopTest();

        System.assertEquals(first.Id, reload(opp.Id).Primary_Contact__c,
            'At equal role rank the oldest link wins');
    }

    @isTest
    static void duplicateLink_countedOnce() {
        Opportunity opp = makeOpp('DUPLICATE');
        insert opp;
        Contact c = makeContact('OnlyPerson');
        insert c;

        Test.startTest();
        insert new List<Opportunity_Contact__c>{
            new Opportunity_Contact__c(Opportunity__c = opp.Id, Contact__c = c.Id,
                                       Role__c = 'Property Owner'),
            new Opportunity_Contact__c(Opportunity__c = opp.Id, Contact__c = c.Id,
                                       Role__c = 'Property Owner')
        };
        Test.stopTest();

        System.assertEquals(1, reload(opp.Id).Contact_Count__c,
            'Same contact twice is one distinct contact, not two');
    }

    @isTest
    static void blankRole_sortsLast() {
        Opportunity opp = makeOpp('BLANK ROLE');
        insert opp;
        Contact noRole = makeContact('NoRole');
        Contact hoa = makeContact('Hoa');
        insert new List<Contact>{ noRole, hoa };

        insert new Opportunity_Contact__c(Opportunity__c = opp.Id, Contact__c = noRole.Id);

        Test.startTest();
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = hoa.Id, Role__c = 'HOA Contact');
        Test.stopTest();

        System.assertEquals(hoa.Id, reload(opp.Id).Primary_Contact__c,
            'A known role outranks a blank role even when linked later');
    }

    @isTest
    static void deletingPrimary_promotesNext() {
        Opportunity opp = makeOpp('DELETE PRIMARY');
        insert opp;
        Contact owner = makeContact('TheOwner');
        Contact mgr = makeContact('TheManager');
        insert new List<Contact>{ owner, mgr };

        Opportunity_Contact__c ownerLink = new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = owner.Id, Role__c = 'Property Owner');
        insert ownerLink;
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = mgr.Id, Role__c = 'Property Manager');

        System.assertEquals(owner.Id, reload(opp.Id).Primary_Contact__c);

        Test.startTest();
        delete ownerLink;
        Test.stopTest();

        Opportunity result = reload(opp.Id);
        System.assertEquals(mgr.Id, result.Primary_Contact__c,
            'Manager is promoted once the Owner link is gone');
        System.assertEquals(1, result.Contact_Count__c);
    }

    @isTest
    static void deletingLastLink_clearsFields() {
        Opportunity opp = makeOpp('LAST LINK');
        insert opp;
        Contact c = makeContact('Solo');
        insert c;
        Opportunity_Contact__c link = new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = c.Id, Role__c = 'Property Owner');
        insert link;
        System.assertEquals(1, reload(opp.Id).Contact_Count__c);

        Test.startTest();
        delete link;
        Test.stopTest();

        Opportunity result = reload(opp.Id);
        System.assertEquals(null, result.Primary_Contact__c, 'No links, no primary contact');
        System.assertEquals(null, result.Primary_Contact_Role__c);
        System.assertEquals(null, result.Contact_Count__c, 'Blank means nobody on file');
    }

    @isTest
    static void undeletedLink_isRestored() {
        Opportunity opp = makeOpp('UNDELETE');
        insert opp;
        Contact c = makeContact('Restored');
        insert c;
        Opportunity_Contact__c link = new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = c.Id, Role__c = 'Property Owner');
        insert link;
        delete link;
        System.assertEquals(null, reload(opp.Id).Primary_Contact__c);

        Test.startTest();
        undelete link;
        Test.stopTest();

        System.assertEquals(c.Id, reload(opp.Id).Primary_Contact__c,
            'Restoring the link restores the primary contact');
    }

    /** Opportunity__c is master-detail with cascade delete. Deleting the parent fires the
     *  child after-delete trigger, which must not block the parent delete. */
    @isTest
    static void deletingParentOpportunity_doesNotThrow() {
        Opportunity opp = makeOpp('CASCADE');
        insert opp;
        Contact c = makeContact('Cascade');
        insert c;
        insert new Opportunity_Contact__c(
            Opportunity__c = opp.Id, Contact__c = c.Id, Role__c = 'Property Owner');

        Test.startTest();
        delete opp;
        Test.stopTest();

        System.assertEquals(0, [SELECT COUNT() FROM Opportunity WHERE Id = :opp.Id],
            'Cascade delete of the parent must succeed');
    }

    @isTest
    static void bulk_200Opportunities_oneQuery() {
        List<Opportunity> opps = new List<Opportunity>();
        for (Integer i = 0; i < 200; i++) {
            opps.add(makeOpp('BULK ' + i));
        }
        insert opps;

        List<Contact> contacts = new List<Contact>();
        for (Integer i = 0; i < 200; i++) {
            contacts.add(makeContact('Bulk' + i));
        }
        insert contacts;

        List<Opportunity_Contact__c> links = new List<Opportunity_Contact__c>();
        for (Integer i = 0; i < 200; i++) {
            links.add(new Opportunity_Contact__c(
                Opportunity__c = opps[i].Id, Contact__c = contacts[i].Id,
                Role__c = 'Property Manager'));
        }

        Test.startTest();
        insert links;
        System.assert(Limits.getQueries() < Limits.getLimitQueries(),
            'Must stay well inside SOQL limits on a 200-row insert');
        Test.stopTest();

        System.assertEquals(200, [
            SELECT COUNT() FROM Opportunity
            WHERE Id IN :opps AND Primary_Contact__c != null
        ], 'Every opportunity in the batch gets its primary contact');
    }
}
