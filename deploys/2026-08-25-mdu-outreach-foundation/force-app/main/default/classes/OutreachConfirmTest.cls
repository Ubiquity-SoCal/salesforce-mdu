@isTest
private class OutreachConfirmTest {

    private static final String TPL = 'MDU_Outreach_Fiber';

    // Salesforce usernames are unique across EVERY org, not just this one, so a hardcoded
    // string is a real if small collision risk. Deriving it from the org id makes it unique
    // by construction without needing a timestamp, which would differ between the testSetup
    // transaction and the test method that looks it up.
    private static String senderUsername() {
        return 'outreach.sender@' + UserInfo.getOrganizationId() + '.mdusdd';
    }

    private static User sender() {
        String u = senderUsername();
        return [SELECT Id FROM User WHERE Username = :u LIMIT 1];
    }

    @testSetup
    static void makeTemplate() {
        // A sender whose user record CAN produce a signature. Verified against the org
        // 2026-08-25 that Title, CompanyName and Phone are null on every real User who would
        // send this, including both reps, so confirm refuses the run for them. That is a true
        // finding about the org and aSenderWithNoPhoneStopsTheRunBeforeAnythingIsClaimed
        // asserts it deliberately. Every other test runs as this user instead, so it exercises
        // the happy path rather than papering over the check.
        Profile admin = [SELECT Id FROM Profile WHERE Name = 'System Administrator' LIMIT 1];
        insert new User(
            FirstName = 'Outreach', LastName = 'Sender',
            Alias = 'osend',
            Email = 'outreach.sender@example.com',
            Username = senderUsername(),
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
    static void confirmWritesABatchWithFrozenBodies() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        Test.startTest();
        OutreachConfirm.Outcome result;
        System.runAs(sender()) {
            result = OutreachConfirm.confirm(new Set<Id>{o.Id}, TPL);
        }
        Test.stopTest();

        System.assertEquals(1, result.messageCount);

        Outreach_Message__c m = [SELECT Subject__c, Body_Html__c, To_Address__c, Status__c
                                 FROM Outreach_Message__c WHERE Batch__c = :result.batchId];
        System.assertEquals('Fiber at Camelot Village, no cost to ownership', m.Subject__c);
        System.assert(m.Body_Html__c.contains('Hello Michelle,'));
        System.assertEquals('mhardy@elevateliving.com', m.To_Address__c);
        System.assertEquals('Queued', m.Status__c);
    }

    @isTest
    static void confirmFreezesTheMeetingDaysOnTheBatch() {
        Contact c = OutreachTestData.contact('Sue', 'Heiman', 'sheiman@burlingtoncapital.com');
        Opportunity o = OutreachTestData.opportunity('The Village at Grant Square', 201, c);

        Test.startTest();
        OutreachConfirm.Outcome result;
        System.runAs(sender()) {
            result = OutreachConfirm.confirm(new Set<Id>{o.Id}, TPL);
        }
        Test.stopTest();

        Outreach_Batch__c b = [SELECT Meeting_Day_1__c, Meeting_Day_2__c, Status__c, Confirmed_At__c
                               FROM Outreach_Batch__c WHERE Id = :result.batchId];
        List<String> expected = OutreachMeetingDays.nextTwo(Date.today());
        System.assertEquals(expected[0], b.Meeting_Day_1__c);
        System.assertEquals(expected[1], b.Meeting_Day_2__c);
        System.assertEquals('Confirmed', b.Status__c);
        System.assertNotEquals(null, b.Confirmed_At__c);
    }

    @isTest
    static void seventeenPropertiesProduceOneMessageAndSeventeenLines() {
        Contact c = OutreachTestData.contact('Paladino', 'Director', 'pdgdirector@example.com');
        Set<Id> ids = new Set<Id>();
        for (Integer i = 0; i < 17; i++) {
            ids.add(OutreachTestData.opportunity('Paladino Property ' + i, 18, c).Id);
        }

        Test.startTest();
        OutreachConfirm.Outcome result;
        System.runAs(sender()) {
            result = OutreachConfirm.confirm(ids, TPL);
        }
        Test.stopTest();

        System.assertEquals(1, result.messageCount, 'seventeen properties are one person');
        System.assertEquals(17, [SELECT COUNT() FROM Outreach_Message_Property__c],
            'every property still gets a line so the activity logs against all of them');
        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Message_Property__c
                                WHERE Is_Named__c = true]);
    }

    @isTest
    static void aSecondConfirmCannotReclaimTheSamePerson() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity first = OutreachTestData.opportunity('Camelot Village', 485, c);
        Opportunity second = OutreachTestData.opportunity('Camelot Village Two', 100, c);

        Test.startTest();
        OutreachConfirm.Outcome again;
        System.runAs(sender()) {
            OutreachConfirm.confirm(new Set<Id>{first.Id}, TPL);
            again = OutreachConfirm.confirm(new Set<Id>{second.Id}, TPL);
        }
        Test.stopTest();

        System.assertEquals(0, again.messageCount, 'the person is already claimed');
        System.assertEquals(1, again.rejectedKeys.size());
        System.assertEquals(true, again.rejectedKeys.contains('mhardy@elevateliving.com'));
    }

    @isTest
    static void aSenderWithNoPhoneStopsTheRunBeforeAnythingIsClaimed() {
        // Deliberately NOT wrapped in System.runAs. The user running the tests has no Phone,
        // which is true of every real User in this org including both reps, verified
        // 2026-08-25. Without the check in senderFromRunningUser the run would proceed, every
        // rendered body would keep an unfilled [phone] token, the renderer would refuse all of
        // them one at a time, and the rep would see a batch that produced nothing.
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Opportunity o = OutreachTestData.opportunity('Camelot Village', 485, c);

        Boolean threw = false;
        Test.startTest();
        try {
            OutreachConfirm.confirm(new Set<Id>{o.Id}, TPL);
        } catch (OutreachConfirm.SenderProfileException e) {
            threw = true;
            System.assert(e.getMessage().contains('Phone'),
                'the message must name the field to fix: ' + e.getMessage());
        }
        Test.stopTest();

        System.assertEquals(true, threw, 'a sender who cannot sign must stop the run');
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Recipient__c],
            'and must cost nothing. Claiming first would burn these recipients permanently '
            + 'under the never-re-mail rule, for a batch that was never going to render');
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Batch__c]);
    }

    @isTest
    static void propertiesWithNoContactAreReportedNotSilentlyDropped() {
        Opportunity orphan = OutreachTestData.opportunity('Orphan Property', 50);

        Test.startTest();
        OutreachConfirm.Outcome result;
        System.runAs(sender()) {
            result = OutreachConfirm.confirm(new Set<Id>{orphan.Id}, TPL);
        }
        Test.stopTest();

        System.assertEquals(0, result.messageCount);
        System.assertEquals(1, result.refusals.size());
        System.assert(result.refusals[0].contains('Orphan Property'));
    }
}
