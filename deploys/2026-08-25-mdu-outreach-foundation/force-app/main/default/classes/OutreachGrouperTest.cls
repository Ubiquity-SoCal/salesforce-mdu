@isTest
private class OutreachGrouperTest {

    @isTest
    static void oneOwnerOnePropertyIsVariantA() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{o.Id});

        System.assertEquals(1, groups.size());
        System.assertEquals('A', groups[0].variant);
        System.assertEquals('mhardy@elevateliving.com', groups[0].emailKey);
        System.assertEquals('Michelle', groups[0].firstName);
        System.assertEquals(485, groups[0].totalUnits);
        System.assertEquals('Camelot Village', groups[0].named.Name);
    }

    @isTest
    static void threePropertiesCollapseToOneRecipientAsVariantB() {
        Contact c = OutreachTestData.contact('Phil', 'Buttner', 'philbuttner@cox.net');
        // Units deliberately anti-correlated with alphabetical order. The largest is
        // alphabetically FIRST, so an implementation that ignores Units__c and simply keeps
        // the last row the SOQL returns would name the wrong property and fail here.
        Opportunity big = OutreachTestData.opportunity('817 N 47th St', 30, c);
        Opportunity mid = OutreachTestData.opportunity('St Frances Apartments', 15, c);
        Opportunity small = OutreachTestData.opportunity('The Richards Apartments', 8, c);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{small.Id, big.Id, mid.Id});

        System.assertEquals(1, groups.size(), 'one person must receive one message');
        System.assertEquals('B', groups[0].variant);
        System.assertEquals(3, groups[0].properties.size());
        System.assertEquals(53, groups[0].totalUnits);
        System.assertEquals('817 N 47th St', groups[0].named.Name,
            'the largest by units is named even though it sorts first alphabetically');
    }

    @isTest
    static void fourOrMorePropertiesIsVariantC() {
        Contact c = OutreachTestData.contact('Kumar', 'Gurung', 'info@drkumargurung.com');
        Set<Id> ids = new Set<Id>();
        for (Integer i = 0; i < 5; i++) {
            ids.add(OutreachTestData.opportunity('Portfolio Property ' + i, 14 - i, c).Id);
        }

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(ids);

        System.assertEquals(1, groups.size());
        System.assertEquals('C', groups[0].variant);
        System.assertEquals(5, groups[0].properties.size());
        System.assertEquals('Portfolio Property 0', groups[0].named.Name,
            'largest by units, and alphabetically first, so a last-row implementation fails');
    }

    @isTest
    static void twoContactRecordsSharingAnAddressAreOneRecipient() {
        // Modelled on the real Omaha data rather than invented. Two of the three shared
        // addresses in production are a COMPANY record and a PERSON record on one mailbox,
        // e.g. ajm@marconomaha.com carries both "MarCon Enterprises" and "Albert Moellenbeck".
        // Identical names on both records would trip this org's Contact duplicate rule, which
        // blocks rather than alerts, so the fixture would fail before grouping ever ran.
        Contact company = OutreachTestData.contact(null, 'MarCon Enterprises', 'ajm@marconomaha.com');
        Contact person = OutreachTestData.contact('Albert', 'Moellenbeck', 'AJM@MarcoNOmaha.com');
        Opportunity a = OutreachTestData.opportunity('78th Place Apartments', 40, company);
        Opportunity b = OutreachTestData.opportunity('Orchard Park Apartments', 25, person);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{a.Id, b.Id});

        System.assertEquals(1, groups.size(),
            'deduping on Contact Id would wrongly produce two messages here');
        System.assertEquals(2, groups[0].properties.size());
    }

    @isTest
    static void aGroupPrefersTheContactItCanGreetByName() {
        // Real consequence, not hypothetical. In two of the three shared addresses in the
        // Omaha data one record is a company with no first name. Taking whichever Contact
        // happened to be seen first would leave [First Name] unfillable, the renderer would
        // refuse the message, and a multi property owner would silently never be contacted.
        Contact company = OutreachTestData.contact(null, 'Gurung Brothers Real Estate',
                                                   'info@drkumargurung.com');
        Contact person = OutreachTestData.contact('Kumar', 'Gurung', 'INFO@DrKumarGurung.com');
        Opportunity first = OutreachTestData.opportunity('6314 Boyd Street', 30, company);
        Opportunity second = OutreachTestData.opportunity('Taylor Apartments', 12, person);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{first.Id, second.Id});

        System.assertEquals(1, groups.size());
        System.assertEquals('Kumar', groups[0].firstName,
            'the company record sorts first and has no first name; the group must still carry '
            + 'a greetable name or the whole portfolio is refused at render time');
        System.assertEquals(person.Id, groups[0].contactId,
            'contactId must move with firstName. Task 8 links the activity by it, so a '
            + 'regression that moved one and not the other would misattribute every send '
            + 'and no other assertion in this file would notice');
        System.assertEquals('info@drkumargurung.com', groups[0].toAddress,
            'the To address follows the chosen contact. Lowercase because Salesforce lowercases '
            + 'Contact.Email on save, measured 2026-08-25: an insert of INFO@DrKumarGurung.com '
            + 'reads back as info@drkumargurung.com, so no Apex can preserve the original case');
    }

    @isTest
    static void theDefaultGreetingDoesNotDependOnWhichPropertiesWereSelected() {
        Contact one = OutreachTestData.contact('Ann', 'Marco', 'ajm@marconomaha.com');
        Contact two = OutreachTestData.contact('Albert', 'Moellenbeck', 'AJM@MarcoNOmaha.com');
        Opportunity alpha = OutreachTestData.opportunity('Alpha Court', 10, two);
        Opportunity zebra = OutreachTestData.opportunity('Zebra Court', 10, one);

        // Computed, not hardcoded: Contact Id assignment order is not guaranteed in a test.
        Boolean oneWins = one.Id < two.Id;
        String expected = oneWins ? 'Ann' : 'Albert';

        List<OutreachGrouper.RecipientGroup> whole =
            OutreachGrouper.group(new Set<Id>{alpha.Id, zebra.Id});

        System.assertEquals(expected, whole[0].firstName);

        // A subset containing only the loser's property greets the loser, because it is the only
        // candidate present. That is true but it does NOT discriminate: with one candidate there
        // is no tie to break, so every implementation agrees. Kept only as a statement of the
        // contract. The assertion that does the work is
        // aStrictSubsetStillBreaksTiesByContactId, which needs three contacts on one mailbox so
        // that a strict subset still contains a genuine tie.
        List<OutreachGrouper.RecipientGroup> loserOnly =
            OutreachGrouper.group(new Set<Id>{oneWins ? alpha.Id : zebra.Id});
        System.assertEquals(oneWins ? 'Albert' : 'Ann', loserOnly[0].firstName,
            'with only one candidate present, that candidate is greeted');
    }

    @isTest
    static void propertiesWithNoReachableContactAreOmitted() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        Opportunity reachable = OutreachTestData.opportunity('The Village at Grant Square', 201, c);
        Opportunity noContact = OutreachTestData.opportunity('Orphan Property', 50);
        Contact noEmail = OutreachTestData.contact('No', 'Email', null);
        Opportunity noEmailOpp = OutreachTestData.opportunity('Unreachable Property', 60, noEmail);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{reachable.Id, noContact.Id, noEmailOpp.Id});

        System.assertEquals(1, groups.size());
        System.assertEquals('sheiman@burlingtoncapital.com', groups[0].emailKey);
    }

    @isTest
    static void aUnitsTieIsBrokenByNameAscending() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        OutreachTestData.opportunity('Zephyr Court', 50, c);
        OutreachTestData.opportunity('Alder Court', 50, c);
        Opportunity mid = OutreachTestData.opportunity('Middle Court', 50, c);

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(new Set<Id>{
            [SELECT Id FROM Opportunity WHERE Name = 'Zephyr Court' LIMIT 1].Id,
            [SELECT Id FROM Opportunity WHERE Name = 'Alder Court' LIMIT 1].Id,
            mid.Id});

        System.assertEquals('Alder Court', groups[0].named.Name,
            'the documented tie-break is Name ascending, and nothing else tested it');
    }

    @isTest
    static void aBouncedContactIsExcludedByTheGrouperNotJustTheScreen() {
        // Sets EmailBouncedReason rather than IsEmailBounced. The latter is system managed and
        // not writable in this org, which is exactly why the production check reads both.
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        c.EmailBouncedDate = System.now();
        c.EmailBouncedReason = 'Mailbox unavailable';
        update c;
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(new Set<Id>{o.Id});

        System.assertEquals(0, groups.size(),
            'suppression must hold for any caller, not only for the screen that draws chips');
    }

    @isTest
    static void emptyInputProducesEmptyOutput() {
        System.assertEquals(0, OutreachGrouper.group(new Set<Id>()).size());
    }

    @isTest
    static void aStrictSubsetStillBreaksTiesByContactId() {
        // Closes the gap that two earlier attempts missed. A subset containing ONE candidate
        // cannot discriminate, because there is no tie to break. This fixture puts THREE
        // contacts on one mailbox so a strict subset still contains a real tie, and the
        // property names are anti-correlated with contact creation order so an implementation
        // ordering by Opportunity name picks differently from one ordering by Contact Id.
        // Distinct surnames on purpose: identical names trip this org's Contact duplicate rule,
        // which blocks rather than alerts.
        Contact a = OutreachTestData.contact('Ann', 'Marco', 'ajm@marconomaha.com');
        Contact b = OutreachTestData.contact('Bert', 'Nolan', 'AJM@MarcoNOmaha.com');
        Contact c = OutreachTestData.contact('Cyd', 'Okonkwo', 'ajm@MARCONOMAHA.com');
        OutreachTestData.opportunity('Zulu Court', 10, a);
        Opportunity pb = OutreachTestData.opportunity('Alpha Court', 10, b);
        Opportunity pc = OutreachTestData.opportunity('Mike Court', 10, c);

        // Computed, never hardcoded: Contact Id assignment order is not guaranteed in a test.
        Boolean bWins = b.Id < c.Id;
        String expectedName = bWins ? 'Bert' : 'Cyd';
        Id expectedId = bWins ? b.Id : c.Id;

        List<OutreachGrouper.RecipientGroup> subset =
            OutreachGrouper.group(new Set<Id>{pb.Id, pc.Id});

        System.assertEquals(1, subset.size(), 'all three share one mailbox');
        System.assertEquals(expectedName, subset[0].firstName,
            'a strict subset containing a genuine tie must still break it by Contact Id, not by '
            + 'which property name happened to sort first within this call');
        System.assertEquals(expectedId, subset[0].contactId,
            'and contactId moves with the greeting');
    }

    @isTest
    static void aCandidateCarriesEnoughToLabelACompanyRecord() {
        // The picker has to render a choice. A company record has no FirstName at all, so a
        // candidate list carrying only Id, FirstName and Email would show a blank row, or throw
        // SObjectException the moment the UI reads LastName off an unqueried field.
        Contact company = OutreachTestData.contact(null, 'Gurung Brothers Real Estate',
                                                   'info@drkumargurung.com');
        Contact person = OutreachTestData.contact('Kumar', 'Gurung', 'INFO@DrKumarGurung.com');
        Opportunity first = OutreachTestData.opportunity('6314 Boyd Street', 30, company);
        Opportunity second = OutreachTestData.opportunity('Taylor Apartments', 12, person);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{first.Id, second.Id});

        for (Contact c : groups[0].candidates) {
            System.assertNotEquals(null, c.LastName,
                'every candidate must be labellable without a second query, including a company '
                + 'record that has no first name');
        }
    }

    @isTest
    static void aGroupExposesEveryContactSharingItsMailbox() {
        Contact company = OutreachTestData.contact(null, 'Gurung Brothers Real Estate',
                                                   'info@drkumargurung.com');
        Contact person = OutreachTestData.contact('Kumar', 'Gurung', 'INFO@DrKumarGurung.com');
        Opportunity first = OutreachTestData.opportunity('6314 Boyd Street', 30, company);
        Opportunity second = OutreachTestData.opportunity('Taylor Apartments', 12, person);

        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>{first.Id, second.Id});

        System.assertEquals(2, groups[0].candidates.size(),
            'the rep cannot choose between records the group never surfaced');
        System.assertEquals(person.Id, groups[0].candidates[0].Id,
            'the defaulted pick leads, so accepting the default requires no interaction');
    }

    @isTest
    static void aSingleContactGroupOffersNoChoice() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(new Set<Id>{o.Id});

        System.assertEquals(1, groups[0].candidates.size(),
            'a picker must not appear for the 100 of 103 recipients who have exactly one record');
    }

    @isTest
    static void oneContactOnManyPropertiesIsStillOneCandidate() {
        Contact c = OutreachTestData.contact('Paladino', 'Director', 'pdg@example.com');
        Set<Id> ids = new Set<Id>();
        for (Integer i = 0; i < 4; i++) {
            ids.add(OutreachTestData.opportunity('Paladino Property ' + i, 18, c).Id);
        }

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(ids);

        System.assertEquals(1, groups[0].candidates.size(),
            'candidates are distinct Contact RECORDS, not one per property; the seventeen '
            + 'property owner must not present seventeen identical choices');
    }
}
