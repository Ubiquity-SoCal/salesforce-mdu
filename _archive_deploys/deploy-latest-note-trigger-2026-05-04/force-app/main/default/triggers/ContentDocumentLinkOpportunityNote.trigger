trigger ContentDocumentLinkOpportunityNote on ContentDocumentLink (after insert, after delete) {
    // Refresh Opportunity.Latest_Note_* whenever a ContentNote is linked or unlinked.
    Set<Id> oppIds = new Set<Id>();
    List<ContentDocumentLink> links = (Trigger.isDelete) ? Trigger.old : Trigger.new;
    for (ContentDocumentLink cdl : links) {
        Id linked = cdl.LinkedEntityId;
        if (linked != null && linked.getSObjectType() == Opportunity.SObjectType) {
            oppIds.add(linked);
        }
    }
    if (!oppIds.isEmpty()) {
        LatestNoteHandler.refreshOpps(oppIds);
    }
}
