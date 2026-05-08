trigger ContentDocumentOpportunityNote on ContentDocument (before delete) {
    // CDL triggers don't fire on cascade delete from ContentDocument, so we handle clear-on-delete here.
    // before-delete: CDL still exists, so we tell refreshOpps to exclude these doc Ids
    // (simulating the post-delete state).
    Set<Id> docIds = new Set<Id>();
    for (ContentDocument cd : Trigger.old) {
        docIds.add(cd.Id);
    }

    Set<Id> oppIds = new Set<Id>();
    for (ContentDocumentLink cdl : [
        SELECT LinkedEntityId FROM ContentDocumentLink WHERE ContentDocumentId IN :docIds
    ]) {
        Id linked = cdl.LinkedEntityId;
        if (linked != null && linked.getSObjectType() == Opportunity.SObjectType) {
            oppIds.add(linked);
        }
    }

    if (!oppIds.isEmpty()) {
        LatestNoteHandler.refreshOpps(oppIds, docIds);
    }
}
