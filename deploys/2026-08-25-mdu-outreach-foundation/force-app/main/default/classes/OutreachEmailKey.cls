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
        // Strip ALL whitespace, not just the ends. trim() leaves a stray space beside the @,
        // which produces a SECOND key for the same person: precisely the failure this key
        // exists to prevent. It also breaks dot folding silently, because " gmail.com" is
        // never a member of DOTLESS_DOMAINS.
        String e = raw.toLowerCase().replaceAll('\\s+', '');
        if (String.isBlank(e)) {
            return null;
        }

        Integer at = e.lastIndexOf('@');
        if (at <= 0 || at == e.length() - 1) {
            return null;
        }

        String localPart = e.substring(0, at);
        String domain = e.substring(at + 1);

        // A domain with no interior dot is not deliverable. Reject rather than claim a key
        // that could never be sent to, which would permanently block a real address that
        // someone later corrects.
        if (!domain.contains('.') || domain.startsWith('.') || domain.endsWith('.')) {
            return null;
        }

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
