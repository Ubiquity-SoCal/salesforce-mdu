/**
 * Turns a set of selected Opportunities into recipients.
 *
 * The unit of sending is the person, never the property. In the Omaha data 147 mailable
 * properties belong to 103 people, and one address sits on seventeen properties. Grouping
 * here is what stops that person receiving seventeen near identical emails.
 */
public with sharing class OutreachGrouper {

    public class RecipientGroup {
        public String emailKey;
        public String toAddress;
        public Id contactId;
        public String firstName;
        public List<Opportunity> properties = new List<Opportunity>();
        public Opportunity named;
        public Decimal totalUnits = 0;
        public String variant;
        public List<Contact> candidates = new List<Contact>();
    }

    public static List<RecipientGroup> group(Set<Id> opportunityIds) {
        List<RecipientGroup> out = new List<RecipientGroup>();
        if (opportunityIds == null || opportunityIds.isEmpty()) {
            return out;
        }

        List<Opportunity> opps = [
            SELECT Id, Name, Units__c, Primary_Contact__c,
                   Primary_Contact__r.FirstName, Primary_Contact__r.LastName,
                   Primary_Contact__r.Email
            FROM Opportunity
            WHERE Id IN :opportunityIds
            ORDER BY Name ASC
        ];

        Map<String, RecipientGroup> byKey = new Map<String, RecipientGroup>();
        Map<String, Map<Id, Contact>> contactsByKey = new Map<String, Map<Id, Contact>>();

        for (Opportunity o : opps) {
            if (o.Primary_Contact__c == null || o.Primary_Contact__r == null) {
                continue;
            }
            String key = OutreachEmailKey.normalise(o.Primary_Contact__r.Email);
            if (key == null) {
                continue;
            }

            RecipientGroup g = byKey.get(key);
            if (g != null) {
                // Deterministic default, deliberately independent of which properties this
                // call happened to select. Prefer a Contact we can greet, because the
                // alternative is an unfillable [First Name], a refused render, and a multi
                // property owner never contacted at all. Among equally greetable records the
                // lowest Contact Id wins.
                //
                // The Id tie-break is the part that matters. An earlier version kept the first
                // record seen in Opportunity Name order, which meant two partial sends over the
                // same mailbox could greet that person by two different names, since group()
                // has no memory across calls. Apex compares Id with < directly, verified
                // against the org 2026-08-25.
                Boolean incomingGreetable = String.isNotBlank(o.Primary_Contact__r.FirstName);
                Boolean storedGreetable = String.isNotBlank(g.firstName);
                Boolean better = (incomingGreetable && !storedGreetable)
                    || (incomingGreetable == storedGreetable
                        && o.Primary_Contact__c < g.contactId);
                if (better) {
                    g.firstName = o.Primary_Contact__r.FirstName;
                    g.contactId = o.Primary_Contact__c;
                    g.toAddress = o.Primary_Contact__r.Email.replaceAll('\\s+', '');
                }
            }
            if (g == null) {
                g = new RecipientGroup();
                g.emailKey = key;
                // Defensive only, and deliberately kept despite being unreachable from this
                // source. Measured against the org 2026-08-25: the standard Email field
                // REJECTS internal whitespace with INVALID_EMAIL_ADDRESS, trims the ends, AND
                // lowercases the value on save. Do not write a test for the whitespace strip:
                // a Contact holding interior whitespace cannot be created, so any such test
                // asserts something the platform forbids.
                //
                // An earlier version of this comment claimed case is preserved here, unlike in
                // the key. That was wrong. The platform lowercases Contact.Email before Apex
                // ever reads it, so for this data path toAddress and emailKey differ only by
                // plus-tag stripping and gmail dot folding, never by case. The strip stays
                // because a future caller may hand us a string that never passed through an
                // Email field, not because Contact data can be dirty.
                g.toAddress = o.Primary_Contact__r.Email.replaceAll('\\s+', '');
                g.contactId = o.Primary_Contact__c;
                g.firstName = o.Primary_Contact__r.FirstName;
                byKey.put(key, g);
            }

            if (!contactsByKey.containsKey(key)) {
                contactsByKey.put(key, new Map<Id, Contact>());
            }
            // Keyed by Id so a contact appearing on seventeen properties is one candidate,
            // not seventeen identical rows in a picker.
            contactsByKey.get(key).put(o.Primary_Contact__c, o.Primary_Contact__r);

            g.properties.add(o);
            g.totalUnits += (o.Units__c == null ? 0 : o.Units__c);

            Boolean isBigger = g.named == null
                || (o.Units__c == null ? 0 : o.Units__c) > (g.named.Units__c == null ? 0 : g.named.Units__c);
            if (isBigger) {
                g.named = o;
            }
        }

        for (RecipientGroup g : byKey.values()) {
            Integer n = g.properties.size();
            g.variant = n == 1 ? 'A' : (n <= 3 ? 'B' : 'C');

            Map<Id, Contact> found = contactsByKey.get(g.emailKey);
            if (found.containsKey(g.contactId)) {
                g.candidates.add(found.get(g.contactId));
            }
            for (Contact c : found.values()) {
                if (c.Id != g.contactId) {
                    g.candidates.add(c);
                }
            }
            out.add(g);
        }
        return out;
    }
}
