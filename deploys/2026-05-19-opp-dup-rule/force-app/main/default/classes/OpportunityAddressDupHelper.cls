public with sharing class OpportunityAddressDupHelper {
    // Match key for OpportunityAddressDupBlock trigger.
    //
    // ~86% of existing Opps have Property_Address__c in the form
    //   '1942 South Emerson, Mesa, AZ 85210, USA'
    // (city/state/zip baked into the address field), while ~14% have just
    //   '1942 South Emerson'.
    //
    // State is also unreliable (some records 'AZ', some 'Arizona').
    //
    // So the key is: coreAddress(stuff before first comma, normalised) + zip.
    // Zip is consistently formatted and uniquely scopes the address regionally.
    public static String normKey(String addr, String zip) {
        return coreAddress(addr) + '|' + norm(zip);
    }

    // Take the portion of the address before the first comma, uppercase + trim,
    // collapse internal whitespace, strip trailing punctuation.
    @TestVisible
    private static String coreAddress(String addr) {
        if (String.isBlank(addr)) return '';
        String head = addr.split(',')[0];
        return norm(head);
    }

    @TestVisible
    private static String norm(String s) {
        if (s == null) return '';
        return s.trim().toUpperCase().replaceAll('\\s+', ' ');
    }
}
