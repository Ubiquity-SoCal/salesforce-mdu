/**
 * Backs the outreach selection screen.
 *
 * Eligibility is computed server side because every reason a property cannot be mailed lives in
 * Salesforce data. A blocked row is returned with its reason rather than filtered out: the rep
 * needs to see that 186 Omaha properties have no contact, because that, not this tool, is the
 * real ceiling on outreach volume.
 */
public with sharing class OutreachSelectionController {

    private static final Set<String> INELIGIBLE_STAGES = new Set<String>{
        'Closed Lost', 'PAL/ROE Complete'
    };

    // MDU/SFU, verified against the live org 2026-08-25. Without this filter the tab lists
    // Business Sales and Business ROE opportunities alongside MDU ones, and a rep would mail
    // a property owner about the wrong kind of deal entirely.
    private static final Id MDU_RECORD_TYPE_ID = '012WR00000Ra0mkYAB';

    /**
     * Rows returned to the screen at once. See the note on truncation in candidates().
     *
     * Not final, and TestVisible, purely so the overflow branch can be exercised. Proving
     * truncation with the real value would mean inserting 2,001 Opportunities in a test, which
     * nobody will do, so the branch would stay unproven forever and the flag would be a
     * decoration. A test lowers this to 2 and inserts 3.
     */
    @TestVisible
    private static Integer PAGE_CAP = 2000;

    public class Candidate {
        @AuraEnabled public Id opportunityId;
        @AuraEnabled public String propertyName;
        @AuraEnabled public Decimal units;
        @AuraEnabled public String stage;
        @AuraEnabled public Id contactId;
        @AuraEnabled public String contactFirstName;
        @AuraEnabled public String contactEmail;
        @AuraEnabled public String emailKey;
        @AuraEnabled public String chip;
        @AuraEnabled public Boolean selectable;
        /** True on every row when the result hit the cap and rows were dropped. */
        @AuraEnabled public Boolean listTruncated;
    }

    @AuraEnabled(cacheable=true)
    public static List<Candidate> candidates(String city, String state, String stageFilter,
                                             Decimal minUnits, Boolean mineOnly) {
        String cityLike = String.isBlank(city) ? '%' : '%' + city + '%';
        String stateValue = String.isBlank(state) ? null : state;
        Id me = UserInfo.getUserId();
        Id recordTypeId = MDU_RECORD_TYPE_ID;

        // Dynamic SOQL, because SOQL has no way to express an optional filter in a static
        // query. Verified against the live org 2026-08-25: a bind variable cannot sit on the
        // left of a comparison, so `:stageFilter = null` and `:onlyMine = false` are both
        // syntax errors, not merely odd style. Nothing here is concatenated from caller input;
        // every value arrives through a bind, so there is no injection surface.
        String soql =
            'SELECT Id, Name, Units__c, StageName, OwnerId, Primary_Contact__c, ' +
            'Primary_Contact__r.FirstName, Primary_Contact__r.Email ' +
            'FROM Opportunity WHERE RecordTypeId = :recordTypeId';

        if (stateValue != null || !String.isBlank(city)) {
            soql += ' AND (Property_City__c LIKE :cityLike OR Property_State__c = :stateValue)';
        }
        if (minUnits != null) {
            soql += ' AND Units__c >= :minUnits';
        }
        if (!String.isBlank(stageFilter)) {
            soql += ' AND StageName = :stageFilter';
        }
        if (mineOnly == true) {
            soql += ' AND OwnerId = :me';
        }
        // Deliberately one MORE than the cap. Verified against the org 2026-08-25: an
        // unfiltered query returns exactly 2000 rows against 3,646 MDU opportunities, so a rep
        // who clears the city filter would see a truncated list with nothing telling them so.
        // Asking for 2001 makes truncation detectable; the extra row is dropped before return.
        soql += ' ORDER BY Units__c DESC NULLS LAST, Name ASC LIMIT ' + (PAGE_CAP + 1);

        List<Opportunity> opps = Database.query(soql);
        Boolean truncated = opps.size() > PAGE_CAP;
        if (truncated) {
            opps.remove(opps.size() - 1);
        }

        Map<Id, String> keyByOpp = new Map<Id, String>();
        Map<String, Integer> keyCounts = new Map<String, Integer>();

        for (Opportunity o : opps) {
            String key = o.Primary_Contact__c == null || o.Primary_Contact__r == null
                ? null
                : OutreachEmailKey.normalise(o.Primary_Contact__r.Email);
            keyByOpp.put(o.Id, key);
            if (key != null) {
                keyCounts.put(key, (keyCounts.containsKey(key) ? keyCounts.get(key) : 0) + 1);
            }
        }

        Set<String> alreadyMailed = new Set<String>();
        if (!keyCounts.isEmpty()) {
            for (Outreach_Recipient__c r : [SELECT Email_Key__c FROM Outreach_Recipient__c
                                            WHERE Email_Key__c IN :keyCounts.keySet()]) {
                alreadyMailed.add(r.Email_Key__c.toLowerCase());
            }
        }

        List<Candidate> out = new List<Candidate>();
        for (Opportunity o : opps) {
            Candidate c = new Candidate();
            c.opportunityId = o.Id;
            c.propertyName = o.Name;
            c.units = o.Units__c;
            c.stage = o.StageName;
            c.contactId = o.Primary_Contact__c;
            c.emailKey = keyByOpp.get(o.Id);
            if (o.Primary_Contact__r != null) {
                c.contactFirstName = o.Primary_Contact__r.FirstName;
                c.contactEmail = o.Primary_Contact__r.Email;
            }
            c.chip = chipFor(o, c.emailKey, keyCounts, alreadyMailed);
            c.selectable = (c.chip == 'Ready' || c.chip == 'Duplicate recipient');
            c.listTruncated = truncated;
            out.add(c);
        }
        return out;
    }

    /**
     * Precedence, most blocking first. Order here IS the specification.
     *
     * Duplicate recipient is checked BEFORE No first name, not after. A property whose own
     * Primary_Contact__c has no first name (a company record, an info@ mailbox) is still
     * mailable when a sibling property on the same normalised address has a contact who IS
     * greetable: OutreachGrouper already resolves exactly this by picking the greetable
     * candidate among everyone sharing the key. Blocking the company-linked row here would
     * contradict what the grouper does with it a moment later. The single-property case is
     * unaffected: with only one occurrence at that key, the duplicate check does not fire and
     * this falls through to No first name as before.
     */
    private static String chipFor(Opportunity o, String key, Map<String, Integer> keyCounts,
                                  Set<String> alreadyMailed) {
        if (key != null && alreadyMailed.contains(key)) {
            return 'Already mailed';
        }
        if (INELIGIBLE_STAGES.contains(o.StageName)) {
            return 'Ineligible stage';
        }
        if (o.Primary_Contact__c == null) {
            return 'No contact';
        }
        if (key == null) {
            return 'No email';
        }
        if (keyCounts.get(key) > 1) {
            return 'Duplicate recipient';
        }
        if (String.isBlank(o.Primary_Contact__r.FirstName)) {
            return 'No first name';
        }
        return 'Ready';
    }
}
