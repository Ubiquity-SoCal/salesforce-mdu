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

    // preview() renders through OutreachConfirm.senderFromRunningUser(), the same validated
    // builder confirm uses. Measured against the org 2026-08-25 (see OutreachConfirmTest):
    // every real User in this org, including whoever runs these tests, has a null Phone, so a
    // call to preview() NOT wrapped in System.runAs would throw SenderProfileException even on
    // a row that should render cleanly. That is deliberately what
    // previewRefusesLoudlyWhenTheSenderCannotSign below exercises. The other three tests need
    // to reach the actual rendering, so they run as a manufactured sender who DOES have a
    // Phone, the same fixture OutreachConfirmTest already uses for the identical reason,
    // rather than inventing a second way around the same validation.
    private static String previewSenderUsername() {
        return 'outreach.preview.sender@' + UserInfo.getOrganizationId() + '.mdusdd';
    }

    private static User previewSender() {
        String u = previewSenderUsername();
        return [SELECT Id FROM User WHERE Username = :u LIMIT 1];
    }

    @testSetup
    static void makePreviewFixtures() {
        Profile admin = [SELECT Id FROM Profile WHERE Name = 'System Administrator' LIMIT 1];
        insert new User(
            FirstName = 'Outreach', LastName = 'Preview Sender',
            Alias = 'oprev',
            Email = 'outreach.preview.sender@example.com',
            Username = previewSenderUsername(),
            Phone = '816-555-0100',
            ProfileId = admin.Id,
            TimeZoneSidKey = 'America/Chicago',
            LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8',
            LanguageLocaleKey = 'en_US');

        // EmailTemplate needs a folder; the running user's personal folder is always present.
        EmailTemplate t = new EmailTemplate(
            DeveloperName = 'MDU_Outreach_Fiber',
            Name = 'MDU Outreach Fiber',
            FolderId = UserInfo.getUserId(),
            TemplateType = 'custom',
            Subject = 'Fiber at [Property Name], no cost to ownership',
            HtmlValue = '<p>Hello [First Name],</p><p>About [Property Block].</p>' +
                        '<p>20 minutes [day 1] or [day 2]?</p>' +
                        '<p>[Sender Name]<br>[Company]<br>[phone]  |  [email]</p>',
            IsActive = true);
        insert t;
    }

    @isTest
    static void previewRendersRealMessagesAndWritesNothing() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        List<OutreachSelectionController.PreviewItem> items;
        Test.startTest();
        System.runAs(previewSender()) {
            // Measured as a DELTA across the preview() call, not an absolute zero: entering
            // System.runAs with a User for the first time in a transaction costs Salesforce its
            // own implicit DML statement for sharing recalculation, independent of anything
            // preview() does. An absolute-zero assertion here would fail on that overhead and
            // hide the real question, which is whether preview() itself adds any DML on top of
            // it. Checking just the two tables below would prove they stayed empty, but would
            // pass even if preview wrote a row somewhere neither query looks, which is not the
            // same as proving no DML ran at all.
            Integer dmlBefore = Limits.getDmlStatements();
            items = OutreachSelectionController.preview(new List<Id>{o.Id});
            System.assertEquals(dmlBefore, Limits.getDmlStatements(),
                'preview must perform zero DML statements, not merely leave these two tables '
                + 'empty');
        }
        Test.stopTest();

        System.assertEquals(1, items.size());
        System.assertEquals('Fiber at Camelot Village, no cost to ownership', items[0].subject);
        System.assert(items[0].bodyHtml.contains('Hello Michelle,'));
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Recipient__c],
            'preview must not claim anybody');
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Batch__c],
            'preview must not create a batch');
    }

    @isTest
    static void previewRefusesLoudlyWhenTheSenderCannotSign() {
        // Deliberately NOT wrapped in System.runAs, so it runs as the real test user, who has no
        // Phone, as does every real User in this org. Before this, preview rendered nothing and
        // silently skipped every item, leaving a rep with an empty screen and a Confirm button
        // that could never enable. An empty preview must be an explained failure, never a blank.
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        // Catches Exception rather than SenderProfileException by name because preview now wraps
        // it: an unwrapped exception reaches Lightning as "An internal server error has
        // occurred", so the wrap is required and this test must not assert the old contract.
        // The wrapping itself is asserted by previewWrapsTheSenderErrorSoItsMessageSurvives.
        // What THIS test still owns, and no other test does, is that preview refuses at all
        // rather than returning an empty list that looks like there is nothing to show.
        Boolean threw = false;
        Test.startTest();
        try {
            OutreachSelectionController.preview(new List<Id>{o.Id});
        } catch (Exception e) {
            threw = true;
            System.assert(e.getMessage().contains('Phone'),
                'and it names the field to fix: ' + e.getMessage());
        }
        Test.stopTest();

        System.assertEquals(true, threw,
            'preview must fail the same way confirm does, for the same reason, rather than '
            + 'returning an empty list that looks like there is nothing to show');
    }

    @isTest
    static void previewShowsAtMostThreeMostUnusualFirst() {
        Contact solo = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        Contact portfolio = OutreachTestData.contact('Paladino', 'Director', 'pdg@example.com');
        List<Id> ids = new List<Id>();
        ids.add(OutreachTestData.opportunity('Solo Property', 200, solo).Id);
        for (Integer i = 0; i < 5; i++) {
            ids.add(OutreachTestData.opportunity('Portfolio Property ' + i, 10, portfolio).Id);
        }
        Contact second = OutreachTestData.contact('Ann', 'Marco', 'ajm@example.com');
        ids.add(OutreachTestData.opportunity('Marco One', 40, second).Id);
        ids.add(OutreachTestData.opportunity('Marco Two', 20, second).Id);

        List<OutreachSelectionController.PreviewItem> items;
        Test.startTest();
        System.runAs(previewSender()) {
            items = OutreachSelectionController.preview(ids);
        }
        Test.stopTest();

        System.assertEquals(3, items.size());
        System.assertEquals(5, items[0].propertyCount,
            'the five property group is the message most worth checking, so it leads');
        System.assertEquals(2, items[1].propertyCount);
        System.assertEquals(1, items[2].propertyCount);
    }

    @isTest
    static void previewUsesTheSameMeetingDaysConfirmWould() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        List<String> expected = OutreachMeetingDays.nextTwo(Date.today());
        List<OutreachSelectionController.PreviewItem> items;
        System.runAs(previewSender()) {
            items = OutreachSelectionController.preview(new List<Id>{o.Id});
        }

        System.assert(items[0].bodyHtml.contains(expected[0] + ' or ' + expected[1]),
            'a preview offering different days from the send would be a lie');
    }

    @isTest
    static void confirmSelectionReturnsWhatWasAndWasNotDone() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        OutreachSelectionController.ConfirmResult r;
        Test.startTest();
        System.runAs(previewSender()) {
            r = OutreachSelectionController.confirmSelection(
                new List<Id>{o.Id}, new Map<String, Id>());
        }
        Test.stopTest();

        System.assertNotEquals(null, r.batchId);
        System.assertEquals(1, r.messageCount);
        System.assertEquals(0, r.rejectedAddresses.size());
        System.assertEquals(0, r.refusals.size());
        // deferredKeys and overrideWarnings are two of the four outcome channels this method
        // must not collapse. No override was requested here, so overrideWarnings is genuinely
        // empty rather than vacuously so; see confirmSelectionSurfacesAnOverrideWarningSeparately
        // FromARefusal below for the case that proves the wiring instead of just its shape.
        // deferredKeys cannot be forced non-empty in a unit test without a real row lock
        // (OutreachConfirmTest.aTransientClaimFailureReachesTheCallerRatherThanVanishing hit the
        // same limit), so the honest claim here is narrower: the channel exists, survived the
        // Set-to-List conversion without throwing, and is empty on a clean run.
        System.assertNotEquals(null, r.deferredKeys,
            'the channel must exist even when empty, so a caller can render it unconditionally');
        System.assertEquals(0, r.deferredKeys.size());
        System.assertEquals(0, r.overrideWarnings.size());
    }

    @isTest
    static void confirmSelectionReportsAnAlreadyClaimedAddress() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity first = OutreachTestData.opportunity('Camelot Village', 485, c);
        Opportunity second = OutreachTestData.opportunity('Camelot Village Two', 100, c);

        OutreachSelectionController.ConfirmResult again;
        Test.startTest();
        System.runAs(previewSender()) {
            OutreachSelectionController.confirmSelection(
                new List<Id>{first.Id}, new Map<String, Id>());
            again = OutreachSelectionController.confirmSelection(
                new List<Id>{second.Id}, new Map<String, Id>());
        }
        Test.stopTest();

        System.assertEquals(0, again.messageCount);
        System.assertEquals(1, again.rejectedAddresses.size());
        System.assertEquals('mhardy@elevateliving.com', again.rejectedAddresses[0]);
    }

    @isTest
    static void confirmSelectionSurfacesAnOverrideWarningSeparatelyFromARefusal() {
        // None of the tests above touch overrideWarnings, so a controller that dropped
        // `r.overrideWarnings = outcome.overrideWarnings` on the floor, or that merged it into
        // refusals, would still pass every one of them. Modeled directly on
        // OutreachConfirmTest.aChosenContactFromAnotherMailboxIsRefusedNotApplied, but calling
        // through this controller: a chosen contact that does not share the group's mailbox is
        // refused as an override, yet the message still sends under the default contact, so
        // overrideWarnings and refusals must move independently through this layer too, not
        // just through OutreachConfirm.
        Contact owner = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Contact stranger = OutreachTestData.contact('Someone', 'Else', 'someone@different.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, owner);

        OutreachSelectionController.ConfirmResult r;
        Test.startTest();
        System.runAs(previewSender()) {
            r = OutreachSelectionController.confirmSelection(
                new List<Id>{o.Id},
                new Map<String, Id>{'mhardy@elevateliving.com' => stranger.Id});
        }
        Test.stopTest();

        System.assertEquals(1, r.messageCount, 'the message still sends under the default contact');
        System.assertEquals(1, r.overrideWarnings.size(),
            'the rep must be told their pick did not take');
        System.assertEquals(0, r.refusals.size(),
            'a warning is not a refusal; collapsing them would tell the rep nobody was contacted');
    }

    @isTest
    static void aThrottleBreachReachesTheRepAsAReadableMessage() {
        // The default cap is 40 recipients per rep per day. Claim 41 distinct people.
        List<Id> ids = new List<Id>();
        for (Integer i = 0; i < 41; i++) {
            Contact c = OutreachTestData.contact('Owner' + i, 'Surname' + i, 'owner' + i + '@example.com');
            ids.add(OutreachTestData.opportunity('Throttle Property ' + i, 10, c).Id);
        }

        // Catch Exception, not AuraHandledException. Verified 2026-08-25 that Apex refuses to
        // throw AuraHandledException outside a VisualForce or Aura context ("Can only throw
        // this exception type from VisualForce or Aura context"), so a test that names that
        // type risks failing on the throw itself rather than on the behaviour under test.
        // Catching the base type asserts what actually matters: the batch stopped, and the
        // rep can see the cap.
        Boolean threw = false;
        String message = '';
        Test.startTest();
        System.runAs(previewSender()) {
            try {
                OutreachSelectionController.confirmSelection(ids, new Map<String, Id>());
            } catch (Exception e) {
                threw = true;
                message = e.getMessage();
            }
        }
        Test.stopTest();

        System.assertEquals(true, threw, 'the cap must stop the batch, not silently truncate it');
        System.assert(message.contains('40'), 'the rep must see what the cap actually is: ' + message);
    }

    /**
     * These two assert the TYPE, not the message, and that is the whole point.
     *
     * SenderProfileException's own message already contains the word "Phone", so a test that
     * only asserted on the message would pass identically whether the controller wrapped the
     * exception or let it escape. It would be hollow. What actually has to be true is that the
     * exception reaching Lightning is an AuraHandledException, because that is the only type
     * whose message survives instead of being replaced with "An internal server error has
     * occurred".
     *
     * Catch Exception rather than naming AuraHandledException in the catch, per the note above:
     * naming it risks failing on the throw rather than on the behaviour under test.
     *
     * Deliberately NOT wrapped in System.runAs. The user running these tests has no Phone, which
     * is precisely the state all three real Users in this org are in, verified 2026-08-27.
     */
    @isTest
    static void previewWrapsTheSenderErrorSoItsMessageSurvives() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        String typeName = '';
        String message = '';
        Test.startTest();
        try {
            OutreachSelectionController.preview(new List<Id>{o.Id});
        } catch (Exception e) {
            typeName = e.getTypeName();
            message = e.getMessage();
        }
        Test.stopTest();

        System.assert(typeName.contains('AuraHandledException'),
            'preview must wrap, or Lightning replaces the message with an internal server '
            + 'error. Actual type: ' + typeName);
        System.assert(message.contains('Phone'),
            'and the wrapped message must still name the field to fix: ' + message);
    }

    @isTest
    static void confirmWrapsTheSenderErrorSoItsMessageSurvives() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        Opportunity o = OutreachTestData.opportunity('The Village at Grant Square', 201, c);

        String typeName = '';
        String message = '';
        Test.startTest();
        try {
            OutreachSelectionController.confirmSelection(
                new List<Id>{o.Id}, new Map<String, Id>());
        } catch (Exception e) {
            typeName = e.getTypeName();
            message = e.getMessage();
        }
        Test.stopTest();

        System.assert(typeName.contains('AuraHandledException'),
            'confirmSelection must wrap SenderProfileException too, not only ThrottleException. '
            + 'Actual type: ' + typeName);
        System.assert(message.contains('Phone'),
            'and the wrapped message must still name the field to fix: ' + message);
    }

    @isTest
    static void theThrottleItselfIsTestedWhereItLives() {
        // The controller only wraps. The rule lives in OutreachConfirm and throws a plain Apex
        // exception, which is testable without any Aura context ambiguity, so the cap is
        // proven here even if the wrapping layer's exception type ever changes.
        List<Id> ids = new List<Id>();
        for (Integer i = 0; i < 41; i++) {
            Contact c = OutreachTestData.contact('Owner' + i, 'Surname' + i, 'cap' + i + '@example.com');
            ids.add(OutreachTestData.opportunity('Cap Property ' + i, 10, c).Id);
        }

        Boolean threw = false;
        Test.startTest();
        System.runAs(previewSender()) {
            try {
                OutreachConfirm.confirm(new Set<Id>(ids), 'MDU_Outreach_Fiber');
            } catch (OutreachConfirm.ThrottleException e) {
                threw = true;
                System.assert(e.getMessage().contains('40'), e.getMessage());
            }
        }
        Test.stopTest();

        System.assertEquals(true, threw, 'the per-rep cap is the control that replaces an approver');
    }
}
