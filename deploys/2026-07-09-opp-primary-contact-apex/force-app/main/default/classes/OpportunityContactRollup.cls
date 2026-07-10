/**
 * Keeps Opportunity.Primary_Contact__c / Primary_Contact_Role__c / Contact_Count__c in sync
 * with the Opportunity_Contact__c junction.
 *
 * Primary contact rule (Koa, 2026-07-09): highest ROLE priority wins; the oldest link
 * breaks ties. Contact_Count__c counts DISTINCT contacts, so an opportunity that has the
 * same person linked twice still reads 1.
 *
 * Why Apex and not a Flow: a record-triggered Flow cannot combine after-save with delete,
 * delete-triggered flows run before the row is gone (so you must exclude it by Id), and
 * Opportunity__c is master-detail with cascade delete -- a flow that updates the parent
 * while the parent is being deleted can block the delete outright. This handles all of it
 * in one bulk-safe place.
 */
public with sharing class OpportunityContactRollup {

    // Who we actually want to call, best first. Anything not listed sorts last.
    private static final List<String> ROLE_PRIORITY = new List<String>{
        'Property Owner',
        'Property Manager',
        'Leasing Contact',
        'HOA Contact',
        'Broker',
        'Developer',
        'Legal Contact',
        'Other'
    };

    private static Map<String, Integer> rankByRole {
        get {
            if (rankByRole == null) {
                rankByRole = new Map<String, Integer>();
                for (Integer i = 0; i < ROLE_PRIORITY.size(); i++) {
                    rankByRole.put(ROLE_PRIORITY[i], i);
                }
            }
            return rankByRole;
        }
        set;
    }
    private static final Integer UNRANKED = 999;

    /** Reentrancy guard: our own Opportunity update must not bounce back in. */
    private static Boolean running = false;

    private static Integer rankOf(String role) {
        if (String.isBlank(role)) return UNRANKED;
        Integer r = rankByRole.get(role);
        return r == null ? UNRANKED : r;
    }

    /**
     * Recalculate the three denormalised fields for the given opportunities.
     * Safe to call with ids whose parent no longer exists (cascade delete).
     */
    public static void recalculate(Set<Id> opportunityIds) {
        if (running || opportunityIds == null || opportunityIds.isEmpty()) {
            return;
        }

        opportunityIds.remove(null);
        if (opportunityIds.isEmpty()) {
            return;
        }

        // Parents may be mid-cascade-delete. Only touch ones that are still alive.
        Map<Id, Opportunity> parents = new Map<Id, Opportunity>([
            SELECT Id, Primary_Contact__c, Primary_Contact_Role__c, Contact_Count__c
            FROM Opportunity
            WHERE Id IN :opportunityIds
        ]);
        if (parents.isEmpty()) {
            return;
        }

        // Oldest first, so the first record seen at a given rank is the tiebreak winner.
        List<Opportunity_Contact__c> links = [
            SELECT Id, Opportunity__c, Contact__c, Role__c, CreatedDate
            FROM Opportunity_Contact__c
            WHERE Opportunity__c IN :parents.keySet()
              AND Contact__c != null
            ORDER BY CreatedDate ASC, Id ASC
        ];

        Map<Id, Id> bestContact = new Map<Id, Id>();
        Map<Id, String> bestRole = new Map<Id, String>();
        Map<Id, Integer> bestRank = new Map<Id, Integer>();
        Map<Id, Set<Id>> distinctContacts = new Map<Id, Set<Id>>();

        for (Opportunity_Contact__c link : links) {
            Id oppId = link.Opportunity__c;

            if (!distinctContacts.containsKey(oppId)) {
                distinctContacts.put(oppId, new Set<Id>());
            }
            distinctContacts.get(oppId).add(link.Contact__c);

            Integer rank = rankOf(link.Role__c);
            // Strictly-less-than keeps the earliest link at an equal rank.
            if (!bestRank.containsKey(oppId) || rank < bestRank.get(oppId)) {
                bestRank.put(oppId, rank);
                bestContact.put(oppId, link.Contact__c);
                bestRole.put(oppId, link.Role__c);
            }
        }

        List<Opportunity> toUpdate = new List<Opportunity>();
        for (Id oppId : parents.keySet()) {
            Opportunity current = parents.get(oppId);

            Id newContact = bestContact.get(oppId);
            String newRole = bestRole.get(oppId);
            Set<Id> contacts = distinctContacts.get(oppId);
            Decimal newCount = (contacts == null || contacts.isEmpty())
                ? null
                : contacts.size();

            Boolean changed =
                current.Primary_Contact__c != newContact
                || current.Primary_Contact_Role__c != newRole
                || current.Contact_Count__c != newCount;

            if (changed) {
                toUpdate.add(new Opportunity(
                    Id = oppId,
                    Primary_Contact__c = newContact,
                    Primary_Contact_Role__c = newRole,
                    Contact_Count__c = newCount
                ));
            }
        }

        if (toUpdate.isEmpty()) {
            return;
        }

        running = true;
        try {
            // allOrNone = false: a parent that vanished mid-transaction, or one blocked by
            // an unrelated validation rule, must not abort the user's whole save.
            Database.update(toUpdate, false);
        } finally {
            running = false;
        }
    }

    /** Collect affected parents from trigger context. */
    public static void handleTrigger(
        List<Opportunity_Contact__c> newRows,
        List<Opportunity_Contact__c> oldRows
    ) {
        Set<Id> oppIds = new Set<Id>();
        if (newRows != null) {
            for (Opportunity_Contact__c r : newRows) oppIds.add(r.Opportunity__c);
        }
        if (oldRows != null) {
            for (Opportunity_Contact__c r : oldRows) oppIds.add(r.Opportunity__c);
        }
        recalculate(oppIds);
    }
}
