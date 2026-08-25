/**
 * Normalises a recipient address into the key that Outreach_Recipient__c.Email_Key__c is
 * unique on. Everything that decides whether two rows are the same person goes through
 * here, so that decision lives in exactly one place.
 */
public with sharing class OutreachEmailKey {

    private static final Set<String> DOTLESS_DOMAINS = new Set<String>{
        'gmail.com', 'googlemail.com'
    };

    public static String normalise(String raw) {
        if (String.isBlank(raw)) {
            return null;
        }
        String e = raw.trim().toLowerCase();

        Integer at = e.lastIndexOf('@');
        if (at <= 0 || at == e.length() - 1) {
            return null;
        }

        String localPart = e.substring(0, at);
        String domain = e.substring(at + 1);

        Integer plus = localPart.indexOf('+');
        if (plus >= 0) {
            localPart = localPart.substring(0, plus);
        }

        if (DOTLESS_DOMAINS.contains(domain)) {
            localPart = localPart.replace('.', '');
        }

        if (String.isBlank(localPart)) {
            return null;
        }
        return localPart + '@' + domain;
    }
}
