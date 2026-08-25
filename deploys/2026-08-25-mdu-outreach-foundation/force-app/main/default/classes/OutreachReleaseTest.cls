@isTest
private class OutreachReleaseTest {

    private static Id claimOneBatch(String emailKey) {
        Outreach_Batch__c b = new Outreach_Batch__c(Status__c = 'Confirmed');
        insert b;
        OutreachClaim.Result claim = OutreachClaim.claim(
            new Map<String, Id>{emailKey => null}, b.Id);
        insert new Outreach_Message__c(
            Batch__c = b.Id, Recipient__c = claim.claimed.get(emailKey),
            To_Address__c = emailKey, Subject__c = 's', Body_Html__c = 'b',
            Status__c = 'Queued');
        return b.Id;
    }

    @isTest
    static void cancellingABatchReleasesItsUnmailedClaims() {
        Id batchId = claimOneBatch('owner@example.com');
        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Recipient__c]);

        Test.startTest();
        OutreachRelease.Result r = OutreachRelease.cancelBatch(batchId);
        Test.stopTest();

        System.assertEquals(1, r.recipientsReleased);
        System.assertEquals(0, r.recipientsKept);
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Recipient__c],
            'a claim that never mailed must not survive the batch that made it');
        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Batch__c WHERE Id = :batchId]);
    }

    @isTest
    static void releasingMakesTheAddressClaimableAgain() {
        // The whole point. Releasing that does not restore contactability is bookkeeping.
        Id batchId = claimOneBatch('owner@example.com');
        OutreachRelease.cancelBatch(batchId);

        Outreach_Batch__c fresh = new Outreach_Batch__c(Status__c = 'Confirmed');
        insert fresh;
        OutreachClaim.Result second = OutreachClaim.claim(
            new Map<String, Id>{'owner@example.com' => null}, fresh.Id);

        System.assertEquals(1, second.claimed.size(),
            'the person can be contacted again, which is the entire purpose of releasing');
        System.assertEquals(0, second.rejected.size());
    }

    @isTest
    static void aMailedRecipientIsNeverReleased() {
        Id batchId = claimOneBatch('mailed@example.com');
        Outreach_Recipient__c r = [SELECT Id FROM Outreach_Recipient__c LIMIT 1];
        r.Status__c = 'Mailed';
        r.First_Mailed_At__c = System.now();
        update r;

        Test.startTest();
        OutreachRelease.Result result = OutreachRelease.cancelBatch(batchId);
        Test.stopTest();

        System.assertEquals(0, result.recipientsReleased);
        System.assertEquals(1, result.recipientsKept);
        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Recipient__c],
            'releasing a mailed recipient would let a real person be contacted twice, which is '
            + 'the one thing this whole project exists to prevent');
    }

    @isTest
    static void aStampedMailDateAloneIsEnoughToKeepAClaim() {
        // Belt and braces on the invariant. Status and the timestamp must BOTH be clean, so a
        // half-updated row from a partially failed send is kept rather than released.
        Id batchId = claimOneBatch('half@example.com');
        Outreach_Recipient__c r = [SELECT Id FROM Outreach_Recipient__c LIMIT 1];
        r.First_Mailed_At__c = System.now();
        update r;

        Test.startTest();
        OutreachRelease.Result result = OutreachRelease.cancelBatch(batchId);
        Test.stopTest();

        System.assertEquals(0, result.recipientsReleased,
            'Status still says Claimed, but something was delivered. Keep it.');
        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Recipient__c]);
    }

    @isTest
    static void aBatchHoldingASendingMessageCannotBeCancelled() {
        // Sending is the ambiguous state: the transmitter may or may not have delivered it.
        // Under-releasing is recoverable, double sending is not.
        Id batchId = claimOneBatch('inflight@example.com');
        Outreach_Message__c m = [SELECT Id FROM Outreach_Message__c LIMIT 1];
        m.Status__c = 'Sending';
        update m;

        Boolean threw = false;
        Test.startTest();
        try {
            OutreachRelease.cancelBatch(batchId);
        } catch (OutreachRelease.CannotReleaseException e) {
            threw = true;
            System.assert(e.getMessage().contains('Sending'), e.getMessage());
        }
        Test.stopTest();

        System.assertEquals(true, threw);
        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Recipient__c],
            'and nothing was released');
    }

    @isTest
    static void staleClaimsSurfacesAClaimThatNeverMailed() {
        claimOneBatch('stale@example.com');

        // olderThanDays = 0 so a row created moments ago qualifies; the boundary itself is not
        // what this asserts. What it asserts is that a burned claim is FINDABLE at all.
        List<Outreach_Recipient__c> stale = OutreachRelease.staleClaims(0);

        System.assertEquals(1, stale.size(),
            'a claim nobody released and nobody mailed must be visible, not silent');
    }
}
