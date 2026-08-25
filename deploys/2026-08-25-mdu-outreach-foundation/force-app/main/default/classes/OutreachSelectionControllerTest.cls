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
        // Domain matches 'AJM@MarcoOmaha.com' below once both are lowercased. An earlier
        // version of this fixture spelled the first domain 'marconomaha.com', an extra 'n'
        // that made the two addresses genuinely different after normalisation, not merely
        // different in case, defeating the entire point of this test.
        Contact first = OutreachTestData.contact('Ann', 'Marco', 'ajm@marcoomaha.com');

        // Once the domains genuinely match, the org's own duplicate rule blocks a second
        // Contact insert on a case-insensitive email match, DUPLICATES_DETECTED. That block is
        // exactly the real-world condition this test exists to prove the controller handles:
        // two Contact records already sitting on one address (an import, manual entry before
        // the rule existed) that Contact Id matching would miss. Bypassing the rule here, once,
        // recreates that condition; OutreachTestData.contact() is left alone so every other
        // test still goes through normal duplicate enforcement.
        Contact second = new Contact(FirstName = 'Ann', LastName = 'Marco',
            Email = 'AJM@MarcoOmaha.com');
        Database.DMLOptions dmo = new Database.DMLOptions();
        dmo.DuplicateRuleHeader.allowSave = true;
        Database.insert(second, dmo);

        Opportunity a = OutreachTestData.opportunity('78th Place Apartments', 40, first);
        Opportunity b = OutreachTestData.opportunity('Orchard Park Apartments', 25, second);

        List<OutreachSelectionController.Candidate> rows = omaha();
        System.assertEquals('Duplicate recipient', find(rows, a.Id).chip,
            'matching on Contact Id would miss this; the key is the normalised address');
    }

    @isTest
    static void aTruncatedListSaysSoOnEveryRow() {
        // Verified against the org 2026-08-25 that an unfiltered query hits the 2000 cap
        // exactly, against 3,646 MDU opportunities. A rep who clears the city filter must not
        // be shown a silently shortened list. This asserts the flag is present and false on a
        // small result, so a change that drops the flag entirely fails here rather than only
        // in production at scale.
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachSelectionController.Candidate> rows = omaha();

        System.assertNotEquals(null, rows[0].listTruncated,
            'every row carries the flag, so the screen never has to guess');
        System.assertEquals(false, rows[0].listTruncated,
            'and a result well under the cap is not truncated');
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
