@isTest
private class OutreachSelectionControllerTest {

    private static List<OutreachSelectionController.Candidate> omaha() {
        return OutreachSelectionController.candidates('Omaha', 'NE', null, null, false);
    }

    private static OutreachSelectionController.Candidate find(
            List<OutreachSelectionController.Candidate> rows, Id oppId) {
        for (OutreachSelectionController.Candidate c : rows) {
            if (c.opportunityId == oppId) return c;
        }
        return null;
    }

    @isTest
    static void aMailablePropertyIsReadyAndSelectable() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        OutreachSelectionController.Candidate row = find(omaha(), o.Id);

        System.assertEquals('Ready', row.chip);
        System.assertEquals(true, row.selectable);
        System.assertEquals('mhardy@elevateliving.com', row.emailKey);
        System.assertEquals(485, row.units);
    }

    @isTest
    static void noContactIsReportedNotHidden() {
        Opportunity o = OutreachTestData.opportunity('Orphan Property', 50);

        OutreachSelectionController.Candidate row = find(omaha(), o.Id);

        System.assertNotEquals(null, row, 'blocked rows stay visible with a reason');
        System.assertEquals('No contact', row.chip);
        System.assertEquals(false, row.selectable);
    }

    @isTest
    static void contactWithoutAnEmailIsNoEmail() {
        Contact c = OutreachTestData.contact('No', 'Email', null);
        Opportunity o = OutreachTestData.opportunity('Unreachable Property', 60, c);

        System.assertEquals('No email', find(omaha(), o.Id).chip);
    }

    @isTest
    static void contactWithoutAFirstNameIsBlocked() {
        Contact c = OutreachTestData.contact(null, 'Nameless', 'nameless@example.com');
        Opportunity o = OutreachTestData.opportunity('Nameless Owner Property', 70, c);

        OutreachSelectionController.Candidate row = find(omaha(), o.Id);
        System.assertEquals('No first name', row.chip);
        System.assertEquals(false, row.selectable,
            'the renderer would refuse this row anyway; block it before the rep invests in it');
    }

    @isTest
    static void anAlreadyMailedAddressIsBlockedForever() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);
        insert new Outreach_Recipient__c(
            Email_Key__c = 'mhardy@elevateliving.com', Status__c = 'Mailed');

        OutreachSelectionController.Candidate row = find(omaha(), o.Id);
        System.assertEquals('Already mailed', row.chip);
        System.assertEquals(false, row.selectable);
    }

    @isTest
    static void alreadyMailedBeatsEveryOtherReason() {
        Contact c = OutreachTestData.contact(null, 'Nameless', 'nameless@example.com');
        Opportunity o = OutreachTestData.opportunity('Nameless Owner Property', 70, c);
        insert new Outreach_Recipient__c(
            Email_Key__c = 'nameless@example.com', Status__c = 'Mailed');

        System.assertEquals('Already mailed', find(omaha(), o.Id).chip,
            'precedence puts the permanent block above the fixable one');
    }

    @isTest
    static void closedLostIsIneligibleByStage() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        Opportunity o = OutreachTestData.opportunity('Lost Property', 80, c);
        o.StageName = 'Closed Lost';
        // The org enforces Loss Reason on Closed Lost via validation rule; without it this
        // update throws FIELD_CUSTOM_VALIDATION_EXCEPTION before the test ever reaches the
        // controller. Not part of what this test verifies, just setup to get there.
        o.Loss_Reason__c = 'Other';
        update o;

        OutreachSelectionController.Candidate row = find(omaha(), o.Id);
        System.assertEquals('Ineligible stage', row.chip);
        System.assertEquals(false, row.selectable);
    }

    @isTest
    static void twoPropertiesSharingAnAddressAreBothFlaggedDuplicateButStaySelectable() {
        Contact c = OutreachTestData.contact('Phil', 'Buttner', 'philbuttner@cox.net');
        Opportunity a = OutreachTestData.opportunity('The Richards Apartments', 30, c);
        Opportunity b = OutreachTestData.opportunity('St Frances Apartments', 15, c);

        List<OutreachSelectionController.Candidate> rows = omaha();

        System.assertEquals('Duplicate recipient', find(rows, a.Id).chip);
        System.assertEquals('Duplicate recipient', find(rows, b.Id).chip);
        System.assertEquals(true, find(rows, a.Id).selectable,
            'collapsing duplicates into one message is the correct outcome, not a refusal');
    }

    @isTest
    static void twoContactRecordsOneAddressStillCountsAsDuplicate() {
        // Modelled on the real Omaha data rather than invented, and deliberately NOT bypassing
        // the org's Contact duplicate rule with DMLOptions. Two of the three genuinely shared
        // addresses in production pair a COMPANY record with a PERSON record on one mailbox,
        // which is what ajm@ and info@ addresses look like. Identical names would trip the rule;
        // the real pattern does not, so no bypass is needed and the fixture resembles the data
        // it claims to represent.
        //
        // Note the domain: MarcoNOmaha, not MarcoOmaha. An earlier version dropped the n, so the
        // two addresses folded to DIFFERENT domains and the test never exercised cross-contact
        // key matching at all. The same typo was fixed once in the grouper's copy of this
        // fixture and survived here, which is why it is called out.
        Contact company = OutreachTestData.contact(null, 'MarCon Enterprises', 'ajm@marconomaha.com');
        Contact person = OutreachTestData.contact('Albert', 'Moellenbeck', 'AJM@MarcoNOmaha.com');
        Opportunity a = OutreachTestData.opportunity('78th Place Apartments', 40, company);
        OutreachTestData.opportunity('Orchard Park Apartments', 25, person);

        List<OutreachSelectionController.Candidate> rows = omaha();
        System.assertEquals('Duplicate recipient', find(rows, a.Id).chip,
            'matching on Contact Id would miss this; the key is the normalised address');
    }

    @isTest
    static void anOverflowingListSaysSoOnEveryRow() {
        // The branch that matters. Verified against the org 2026-08-25 that an unfiltered query
        // returns EXACTLY 2000 rows against 3,646 MDU opportunities, so a rep clearing the city
        // filter works from a list quietly missing 1,646 properties, ordered by units descending
        // so it looks entirely plausible.
        //
        // PAGE_CAP is lowered rather than inserting 2,001 records. An earlier version of this
        // test asserted the flag was FALSE on a small result, which cannot distinguish a wired
        // check from a hardcoded false, so it proved nothing.
        OutreachSelectionController.PAGE_CAP = 2;
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        OutreachTestData.opportunity('Alpha Court', 300, c);
        OutreachTestData.opportunity('Bravo Court', 200, c);
        OutreachTestData.opportunity('Charlie Court', 100, c);

        List<OutreachSelectionController.Candidate> rows = omaha();

        System.assertEquals(2, rows.size(), 'the extra row fetched to detect overflow is dropped');
        for (OutreachSelectionController.Candidate row : rows) {
            System.assertEquals(true, row.listTruncated,
                'EVERY row says so, so the screen can warn without a second call');
        }
    }

    @isTest
    static void aListUnderTheCapIsNotFlaggedTruncated() {
        OutreachSelectionController.PAGE_CAP = 10;
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachSelectionController.Candidate> rows = omaha();

        System.assertEquals(false, rows[0].listTruncated,
            'and a result under the cap is not falsely flagged, which the overflow test alone '
            + 'would not catch');
    }

    @isTest
    static void minUnitsFiltersServerSide() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        OutreachTestData.opportunity('Tiny Property', 4, c);
        Opportunity big = OutreachTestData.opportunity('Big Property', 400, c);

        List<OutreachSelectionController.Candidate> rows =
            OutreachSelectionController.candidates('Omaha', 'NE', null, 100, false);

        System.assertEquals(1, rows.size());
        System.assertEquals(big.Id, rows[0].opportunityId);
    }
}
