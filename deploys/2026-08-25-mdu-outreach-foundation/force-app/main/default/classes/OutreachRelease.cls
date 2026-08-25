/**
 * Gives back a claim that was never used.
 *
 * Every other class here defends against contacting someone twice. This one defends the
 * opposite failure: a person claimed, never mailed, and therefore never contactable again,
 * with nothing on any screen saying so. Against 103 reachable owners, one abandoned batch of
 * 40 burns nearly half the list invisibly.
 */
public with sharing class OutreachRelease {

    public class CannotReleaseException extends Exception {}

    public class Result {
        public Integer messagesDeleted = 0;
        public Integer recipientsReleased = 0;
        public Integer recipientsKept = 0;
    }

    public static Result cancelBatch(Id batchId) {
        Result out = new Result();

        List<Outreach_Message__c> messages =
            [SELECT Id, Status__c FROM Outreach_Message__c WHERE Batch__c = :batchId];

        for (Outreach_Message__c m : messages) {
            // Sent is obvious. Sending is the ambiguous state this project deliberately never
            // auto-retries, because a transmitter may have delivered before dying. Refuse the
            // whole batch rather than guess: under releasing is recoverable, double sending
            // is not.
            if (m.Status__c == 'Sent' || m.Status__c == 'Sending') {
                throw new CannotReleaseException(
                    'This batch contains a message in state ' + m.Status__c + ', so it cannot '
                    + 'be cancelled. Releasing a claim for someone who may already have been '
                    + 'emailed would allow a second email. Resolve that message first.');
            }
        }
        out.messagesDeleted = messages.size();

        // THE INVARIANT, expressed as a query rather than trusted to a comment. Both conditions
        // are required: Status alone could be stale on a half updated row, and the timestamp
        // alone could be unset on a row whose status moved first.
        List<Outreach_Recipient__c> releasable = [
            SELECT Id FROM Outreach_Recipient__c
            WHERE Last_Batch__c = :batchId
              AND Status__c = 'Claimed'
              AND First_Mailed_At__c = null];

        Integer claimedByThisBatch =
            [SELECT COUNT() FROM Outreach_Recipient__c WHERE Last_Batch__c = :batchId];
        out.recipientsReleased = releasable.size();
        out.recipientsKept = claimedByThisBatch - releasable.size();

        // Order matters. Outreach_Message__c.Recipient__c is Restrict on purpose, so the claims
        // cannot go while messages reference them. Deleting the batch cascades messages and
        // their property lines through master-detail, which clears the Restrict.
        delete [SELECT Id FROM Outreach_Batch__c WHERE Id = :batchId];
        delete releasable;

        return out;
    }

    /**
     * Claims that were made and never used. A burned claim is invisible by nature, so the only
     * defence against one is a place to go and look.
     */
    public static List<Outreach_Recipient__c> staleClaims(Integer olderThanDays) {
        DateTime cutoff = System.now().addDays(-1 * Math.abs(olderThanDays));
        return [SELECT Id, Email_Key__c, Contact__c, Last_Batch__c, CreatedDate
                FROM Outreach_Recipient__c
                WHERE Status__c = 'Claimed'
                  AND First_Mailed_At__c = null
                  AND CreatedDate <= :cutoff
                ORDER BY CreatedDate ASC];
    }
}
