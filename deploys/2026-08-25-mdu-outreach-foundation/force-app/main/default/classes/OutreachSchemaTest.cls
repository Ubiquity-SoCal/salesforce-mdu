@isTest
private class OutreachSchemaTest {

    @isTest
    static void aBatchHoldsMessagesWhichHoldProperties() {
        Outreach_Batch__c b = new Outreach_Batch__c(
            Status__c = 'Draft', Meeting_Day_1__c = 'Thursday', Meeting_Day_2__c = 'Friday');
        insert b;

        Outreach_Recipient__c r = new Outreach_Recipient__c(
            Email_Key__c = 'schema@example.com', Status__c = 'Claimed', Last_Batch__c = b.Id);
        insert r;

        Outreach_Message__c m = new Outreach_Message__c(
            Batch__c = b.Id, Recipient__c = r.Id, To_Address__c = 'schema@example.com',
            Subject__c = 'Fiber at Somewhere, no cost to ownership',
            Body_Html__c = '<p>Hello</p>', Status__c = 'Queued');
        insert m;

        Opportunity o = OutreachTestData.opportunity('Schema Test Property', 100);

        insert new Outreach_Message_Property__c(
            Message__c = m.Id, Opportunity__c = o.Id, Is_Named__c = true);

        // Custom child relationships take the __r suffix in SOQL. `FROM Messages` is rejected.
        Outreach_Batch__c reloaded = [
            SELECT Id, (SELECT Id, (SELECT Id FROM Properties__r) FROM Messages__r)
            FROM Outreach_Batch__c WHERE Id = :b.Id];

        System.assertEquals(1, reloaded.Messages__r.size());
        System.assertEquals(1, reloaded.Messages__r[0].Properties__r.size());
    }

    @isTest
    static void deletingABatchRemovesItsMessagesAndLines() {
        Outreach_Batch__c b = new Outreach_Batch__c(Status__c = 'Draft');
        insert b;
        Outreach_Recipient__c r = new Outreach_Recipient__c(
            Email_Key__c = 'cascade@example.com', Status__c = 'Claimed');
        insert r;
        Outreach_Message__c m = new Outreach_Message__c(
            Batch__c = b.Id, Recipient__c = r.Id, Status__c = 'Queued');
        insert m;

        delete b;

        System.assertEquals(0, [SELECT COUNT() FROM Outreach_Message__c WHERE Id = :m.Id],
            'master-detail must cascade the delete');
    }

    @isTest
    static void aRecipientCannotBeDeletedWhileAMessageReferencesIt() {
        Outreach_Batch__c b = new Outreach_Batch__c(Status__c = 'Draft');
        insert b;
        Outreach_Recipient__c r = new Outreach_Recipient__c(
            Email_Key__c = 'restrict@example.com', Status__c = 'Claimed');
        insert r;
        insert new Outreach_Message__c(Batch__c = b.Id, Recipient__c = r.Id, Status__c = 'Queued');

        Database.DeleteResult dr = Database.delete(r.Id, false);

        System.assertEquals(false, dr.isSuccess(),
            'deleting a recipient would silently unblock re-mailing that person');
    }
}
