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
    }

    public static List<RecipientGroup> group(Set<Id> opportunityIds) {
        List<RecipientGroup> out = new List<RecipientGroup>();
        if (opportunityIds == null || opportunityIds.isEmpty()) {
            return out;
        }

        List<Opportunity> opps = [
            SELECT Id, Name, Units__c, Primary_Contact__c,
                   Primary_Contact__r.FirstName, Primary_Contact__r.Email
            FROM Opportunity
            WHERE Id IN :opportunityIds
            ORDER BY Name ASC
        ];

        Map<String, RecipientGroup> byKey = new Map<String, RecipientGroup>();

        for (Opportunity o : opps) {
            if (o.Primary_Contact__c == null || o.Primary_Contact__r == null) {
                continue;
            }
            String key = OutreachEmailKey.normalise(o.Primary_Contact__r.Email);
            if (key == null) {
                continue;
            }

            RecipientGroup g = byKey.get(key);
            if (g != null && String.isBlank(g.firstName)
                    && String.isNotBlank(o.Primary_Contact__r.FirstName)) {
                // Two Contact records share this mailbox and only one of them is a person.
                // Prefer the one we can greet: the alternative is an unfillable [First Name],
                // a refused render, and a multi property owner never contacted at all.
                g.firstName = o.Primary_Contact__r.FirstName;
                g.contactId = o.Primary_Contact__c;
            }
            if (g == null) {
                g = new RecipientGroup();
                g.emailKey = key;
                // Defensive only, and deliberately kept despite being unreachable from this
                // source. Measured against the org 2026-08-25: the standard Email field type
                // REJECTS internal whitespace with INVALID_EMAIL_ADDRESS and trims the ends
                // on save, so Primary_Contact__r.Email can never arrive dirty. Kept because
                // this mirrors OutreachEmailKey and costs nothing, and because a future
                // caller may hand us an address that never passed through an Email field.
                // Do not write a test for it: a Contact with interior whitespace cannot be
                // created, so any such test asserts something the platform forbids.
                // Case is preserved unlike the key. The key is an identity, this is an address.
                g.toAddress = o.Primary_Contact__r.Email.replaceAll('\\s+', '');
                g.contactId = o.Primary_Contact__c;
                g.firstName = o.Primary_Contact__r.FirstName;
                byKey.put(key, g);
            }

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
            out.add(g);
        }
        return out;
    }
}
