trigger ContentVersionOpportunityNote on ContentVersion (after insert, after update) {
    // Refresh Opportunity.Latest_Note_* whenever a ContentNote (FileType=SNOTE) is created or edited.
    // Insert fires when a brand-new note is saved; update fires on subsequent edits.
    Set<Id> docIds = new Set<Id>();
    for (ContentVersion cv : Trigger.new) {
        if (cv.FileType == 'SNOTE') {
            docIds.add(cv.ContentDocumentId);
        }
    }
    if (docIds.isEmpty()) {
        return;
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
        LatestNoteHandler.refreshOpps(oppIds);
    }
}
