/**
 * Keeps Opportunity.Primary_Contact__c / Primary_Contact_Role__c / Contact_Count__c current.
 * All logic lives in OpportunityContactRollup so it can be called from a backfill too.
 *
 * after undelete is included because a restored junction row is a real link again.
 */
trigger OpportunityContactRollupTrigger on Opportunity_Contact__c (
    after insert, after update, after delete, after undelete
) {
    OpportunityContactRollup.handleTrigger(
        Trigger.isDelete ? null : Trigger.new,
        (Trigger.isInsert || Trigger.isUndelete) ? null : Trigger.old
    );
}
