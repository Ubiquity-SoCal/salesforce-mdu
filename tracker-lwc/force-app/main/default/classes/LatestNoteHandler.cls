public with sharing class LatestNoteHandler {

    private static final Integer SNIPPET_MAX = 4500;
    private static final Integer BODY_EXCERPT_MAX = 4000;

    /**
     * Recompute Latest_Note_Date__c + Latest_Note_Snippet__c for the given Opp Ids.
     * Reads the latest ContentNote linked to each Opp via ContentDocumentLink, strips HTML,
     * and writes a snippet of the form: "[YYYY-MM-DD] Title - body excerpt".
     */
    public static void refreshOpps(Set<Id> oppIds) {
        refreshOpps(oppIds, null);
    }

    /**
     * Recompute Latest_Note fields for the given Opp Ids.
     * @param oppIds          Opportunity Ids to refresh
     * @param excludeDocIds   ContentDocument Ids to ignore (used by ContentDocument before-delete trigger
     *                        to simulate the post-delete state since the CDL row still exists at that point)
     */
    public static void refreshOpps(Set<Id> oppIds, Set<Id> excludeDocIds) {
        if (oppIds == null || oppIds.isEmpty()) {
            return;
        }

        // Filter to actual Opportunity Ids (defensive — caller may pass mixed Ids)
        Set<Id> validOppIds = new Set<Id>();
        for (Id oid : oppIds) {
            if (oid.getSObjectType() == Opportunity.SObjectType) {
                validOppIds.add(oid);
            }
        }
        if (validOppIds.isEmpty()) {
            return;
        }

        Set<Id> excluded = excludeDocIds == null ? new Set<Id>() : excludeDocIds;

        // Map Opp -> latest note (ContentDocument Id + LastModifiedDate from ContentDocumentLink view)
        Map<Id, ContentDocumentLink> latestLinkByOpp = new Map<Id, ContentDocumentLink>();
        for (ContentDocumentLink cdl : [
            SELECT LinkedEntityId, ContentDocumentId,
                   ContentDocument.LatestPublishedVersion.Title,
                   ContentDocument.LatestPublishedVersion.LastModifiedDate,
                   ContentDocument.LatestPublishedVersion.FileType
            FROM ContentDocumentLink
            WHERE LinkedEntityId IN :validOppIds
        ]) {
            if (cdl.ContentDocument.LatestPublishedVersion.FileType != 'SNOTE') {
                continue;
            }
            if (excluded.contains(cdl.ContentDocumentId)) {
                continue;
            }
            ContentDocumentLink existing = latestLinkByOpp.get(cdl.LinkedEntityId);
            if (existing == null
                || cdl.ContentDocument.LatestPublishedVersion.LastModifiedDate
                   > existing.ContentDocument.LatestPublishedVersion.LastModifiedDate) {
                latestLinkByOpp.put(cdl.LinkedEntityId, cdl);
            }
        }

        // For each Opp's latest note, fetch ContentNote.Content (HTML) for body extraction
        Set<Id> latestDocIds = new Set<Id>();
        for (ContentDocumentLink cdl : latestLinkByOpp.values()) {
            latestDocIds.add(cdl.ContentDocumentId);
        }
        Map<Id, String> noteContentByDocId = new Map<Id, String>();
        if (!latestDocIds.isEmpty()) {
            for (ContentNote n : [
                SELECT Id, Content FROM ContentNote WHERE Id IN :latestDocIds
            ]) {
                String html = '';
                if (n.Content != null) {
                    html = n.Content.toString();
                }
                noteContentByDocId.put(n.Id, html);
            }
        }

        // Build updates
        List<Opportunity> updates = new List<Opportunity>();
        for (Id oppId : validOppIds) {
            Opportunity upd = new Opportunity(Id = oppId);
            ContentDocumentLink cdl = latestLinkByOpp.get(oppId);
            if (cdl == null) {
                upd.Latest_Note_Date__c = null;
                upd.Latest_Note_Snippet__c = null;
            } else {
                String title = cdl.ContentDocument.LatestPublishedVersion.Title;
                Datetime lastMod = cdl.ContentDocument.LatestPublishedVersion.LastModifiedDate;
                String html = noteContentByDocId.get(cdl.ContentDocumentId);
                String text = htmlToText(html);
                upd.Latest_Note_Date__c = lastMod;
                upd.Latest_Note_Snippet__c = buildSnippet(lastMod, title, text);
            }
            updates.add(upd);
        }

        if (!updates.isEmpty()) {
            update updates;
        }
    }

    private static String htmlToText(String html) {
        if (String.isBlank(html)) {
            return '';
        }
        // Strip tags and collapse whitespace
        String text = html.replaceAll('<[^>]+>', ' ');
        text = text.replace('&nbsp;', ' ')
                   .replace('&amp;', '&')
                   .replace('&lt;', '<')
                   .replace('&gt;', '>')
                   .replace('&quot;', '"')
                   .replace('&#39;', '\'');
        text = text.replaceAll('\\s+', ' ').trim();
        return text;
    }

    private static String buildSnippet(Datetime dt, String title, String bodyText) {
        String dateShort = (dt == null) ? '' : dt.formatGmt('yyyy-MM-dd');
        String t = String.isBlank(title) ? '(untitled)' : title.trim();
        String b = (bodyText == null) ? '' : bodyText.trim();
        if (b.length() > BODY_EXCERPT_MAX) {
            b = b.substring(0, BODY_EXCERPT_MAX).trim() + '...';
        }
        String snippet = String.isBlank(b)
            ? '[' + dateShort + '] ' + t
            : '[' + dateShort + '] ' + t + ' - ' + b;
        if (snippet.length() > SNIPPET_MAX) {
            snippet = snippet.substring(0, SNIPPET_MAX).trim() + '...';
        }
        return snippet;
    }
}