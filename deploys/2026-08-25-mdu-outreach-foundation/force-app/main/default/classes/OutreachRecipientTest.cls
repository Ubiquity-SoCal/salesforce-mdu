@isTest
private class OutreachRecipientTest {

    @isTest
    static void duplicateKeyIsRejectedByThePlatform() {
        insert new Outreach_Recipient__c(Email_Key__c = 'owner@example.com', Status__c = 'Claimed');

        Database.SaveResult sr = Database.insert(
            new Outreach_Recipient__c(Email_Key__c = 'owner@example.com', Status__c = 'Claimed'),
            false);

        System.assertEquals(false, sr.isSuccess(), 'a second claim on the same address must be rejected');
        System.assertEquals(StatusCode.DUPLICATE_VALUE, sr.getErrors()[0].getStatusCode(),
            'rejection must come from the unique constraint, not from application logic');
    }

    @isTest
    static void uniquenessIsCaseInsensitive() {
        insert new Outreach_Recipient__c(Email_Key__c = 'owner@example.com', Status__c = 'Claimed');

        Database.SaveResult sr = Database.insert(
            new Outreach_Recipient__c(Email_Key__c = 'OWNER@EXAMPLE.COM', Status__c = 'Claimed'),
            false);

        System.assertEquals(false, sr.isSuccess(),
            'caseSensitive=false must make a differently cased address the same recipient');
    }

    @isTest
    static void twoRowsInOneInsertCollideToo() {
        List<Outreach_Recipient__c> both = new List<Outreach_Recipient__c>{
            new Outreach_Recipient__c(Email_Key__c = 'dup@example.com', Status__c = 'Claimed'),
            new Outreach_Recipient__c(Email_Key__c = 'dup@example.com', Status__c = 'Claimed')
        };

        List<Database.SaveResult> results = Database.insert(both, false);

        Integer succeeded = 0;
        for (Database.SaveResult r : results) {
            if (r.isSuccess()) succeeded++;
        }
        System.assertEquals(1, succeeded, 'exactly one of two identical rows may survive one insert');
    }

    @isTest
    static void distinctAddressesBothSucceed() {
        List<Database.SaveResult> results = Database.insert(new List<Outreach_Recipient__c>{
            new Outreach_Recipient__c(Email_Key__c = 'a@example.com', Status__c = 'Claimed'),
            new Outreach_Recipient__c(Email_Key__c = 'b@example.com', Status__c = 'Claimed')
        }, false);

        System.assertEquals(true, results[0].isSuccess());
        System.assertEquals(true, results[1].isSuccess());
    }
}
