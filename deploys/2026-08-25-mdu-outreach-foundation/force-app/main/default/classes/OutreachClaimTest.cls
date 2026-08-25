@isTest
private class OutreachClaimTest {

    private static Id newBatch() {
        Outreach_Batch__c b = new Outreach_Batch__c(Status__c = 'Draft');
        insert b;
        return b.Id;
    }

    @isTest
    static void claimsFreshAddresses() {
        Id batchId = newBatch();

        OutreachClaim.Result r = OutreachClaim.claim(new Map<String, Id>{
            'one@example.com' => null, 'two@example.com' => null}, batchId);

        System.assertEquals(2, r.claimed.size());
        System.assertEquals(0, r.rejected.size());
        System.assertEquals(2, [SELECT COUNT() FROM Outreach_Recipient__c]);
    }

    @isTest
    static void refusesAnAddressAlreadyHeld() {
        Id firstBatch = newBatch();
        OutreachClaim.claim(new Map<String, Id>{'taken@example.com' => null}, firstBatch);

        Id secondBatch = newBatch();
        OutreachClaim.Result r = OutreachClaim.claim(new Map<String, Id>{
            'taken@example.com' => null, 'free@example.com' => null}, secondBatch);

        System.assertEquals(1, r.claimed.size(), 'only the free address may be claimed');
        System.assertEquals(true, r.claimed.containsKey('free@example.com'));
        System.assertEquals(1, r.rejected.size());
        System.assertEquals(true, r.rejected.contains('taken@example.com'));
    }

    @isTest
    static void aRejectionDoesNotRollBackTheWholeClaim() {
        Id firstBatch = newBatch();
        OutreachClaim.claim(new Map<String, Id>{'held@example.com' => null}, firstBatch);

        Id secondBatch = newBatch();
        OutreachClaim.claim(new Map<String, Id>{
            'held@example.com' => null, 'newone@example.com' => null}, secondBatch);

        System.assertEquals(1, [SELECT COUNT() FROM Outreach_Recipient__c
                                WHERE Email_Key__c = 'newone@example.com'],
            'partial success must persist; allOrNone must be false');
    }

    @isTest
    static void stampsTheBatchAndTheContact() {
        Contact c = OutreachTestData.contact('Michelle', 'Hardy', 'mhardy@elevateliving.com');
        Id batchId = newBatch();

        OutreachClaim.claim(new Map<String, Id>{'mhardy@elevateliving.com' => c.Id}, batchId);

        Outreach_Recipient__c r = [SELECT Contact__c, Last_Batch__c, Status__c, First_Mailed_At__c
                                   FROM Outreach_Recipient__c LIMIT 1];
        System.assertEquals(c.Id, r.Contact__c);
        System.assertEquals(batchId, r.Last_Batch__c);
        System.assertEquals('Claimed', r.Status__c);
        System.assertEquals(null, r.First_Mailed_At__c,
            'claiming is not sending; the mailed stamp waits for a successful send');
    }

    @isTest
    static void ignoresBlankKeys() {
        Id batchId = newBatch();
        OutreachClaim.Result r = OutreachClaim.claim(new Map<String, Id>{
            '' => null, null => null, 'good@example.com' => null}, batchId);

        System.assertEquals(1, r.claimed.size());
        System.assertEquals(true, r.claimed.containsKey('good@example.com'));
    }
}
