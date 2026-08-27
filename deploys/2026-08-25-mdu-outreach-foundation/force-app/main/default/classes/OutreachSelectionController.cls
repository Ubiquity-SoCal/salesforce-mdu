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

        // Two independent clauses, not one OR. The OR made BOTH single-value cases degenerate to
        // match-all: with no city, cityLike was '%' and the LIKE matched every row that had any
        // city, so the state filter did nothing; with no state, Property_State__c = null matched
        // every blank-state row. Unreachable while the LWC hardcoded Omaha and NE, and a real bug
        // the moment the filter inputs existed, which is the very next task. Demonstrated before
        // fixing: a state filter of NE returned an Arizona property.
        if (!String.isBlank(city)) {
            soql += ' AND Property_City__c LIKE :cityLike';
        }
        if (stateValue != null) {
            soql += ' AND Property_State__c = :stateValue';
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

    public class PreviewItem {
        @AuraEnabled public String toAddress;
        @AuraEnabled public String subject;
        @AuraEnabled public String bodyHtml;
        @AuraEnabled public Integer propertyCount;
        @AuraEnabled public Decimal totalUnits;
        @AuraEnabled public String variant;
    }

    private static final Integer PREVIEW_LIMIT = 3;
    private static final String TEMPLATE_NAME = 'MDU_Outreach_Fiber';

    /**
     * Renders through the same path confirm uses, with no DML at all. What the rep approves is
     * exactly what confirm freezes.
     *
     * There is no human approver for this batch by design, so this preview IS the approval
     * gate. It calls OutreachConfirm.senderFromRunningUser() rather than building its own
     * sender, on purpose: that method both builds the signature AND validates it, throwing
     * OutreachConfirm.SenderProfileException when the running user's profile cannot produce
     * one (every real User in this org has a null Phone, verified 2026-08-25). An earlier
     * version of this method carried its own copy of that logic without the validation, and
     * the concrete consequence was every preview item failing the renderer's bracket guard on
     * an unfilled [phone] token, being silently skipped by the catch below, and the rep seeing
     * an empty preview with a Confirm button that could never enable and nothing explaining
     * why. An empty preview must be an explained failure, never a blank screen, so this throws
     * loudly instead of swallowing that case.
     */
    /**
     * The four exceptions this project raises on purpose all carry a message written for a rep.
     * Rethrowing them as AuraHandledException is the only thing that stops Lightning replacing
     * that message with "An internal server error has occurred".
     *
     * setMessage() is not redundant with the constructor: the constructor's argument does not
     * survive to getMessage() on the client, which is why the throttle path already did both.
     *
     * Genuinely unexpected exceptions are deliberately NOT caught here. A NullPointerException
     * is an internal error and should read as one rather than being dressed up as advice.
     */
    private static AuraHandledException asRepFacing(Exception e) {
        AuraHandledException wrapped = new AuraHandledException(e.getMessage());
        wrapped.setMessage(e.getMessage());
        return wrapped;
    }

    /**
     * Wraps previewInternal rather than wrapping the body in place, so the ~45 line method below
     * keeps its indentation and its diff stays readable.
     */
    @AuraEnabled
    public static List<PreviewItem> preview(List<Id> opportunityIds) {
        try {
            return previewInternal(opportunityIds);
        } catch (OutreachConfirm.SenderProfileException e) {
            throw asRepFacing(e);
        } catch (OutreachRenderer.MissingTemplateException e) {
            throw asRepFacing(e);
        } catch (OutreachRenderer.UnknownTemplateTokenException e) {
            throw asRepFacing(e);
        }
    }

    private static List<PreviewItem> previewInternal(List<Id> opportunityIds) {
        List<OutreachGrouper.RecipientGroup> groups =
            OutreachGrouper.group(new Set<Id>(opportunityIds));

        // Most unusual first: a batch containing a seventeen property group must not preview as
        // three ordinary single property emails. The rep is approving the whole batch, so the
        // message most worth checking has to be the one they see.
        for (Integer i = 0; i < groups.size(); i++) {
            for (Integer j = i + 1; j < groups.size(); j++) {
                if (groups[j].properties.size() > groups[i].properties.size()) {
                    OutreachGrouper.RecipientGroup swap = groups[i];
                    groups[i] = groups[j];
                    groups[j] = swap;
                }
            }
        }

        EmailTemplate tpl = OutreachRenderer.loadTemplate(TEMPLATE_NAME);
        List<String> days = OutreachMeetingDays.nextTwo(Date.today());
        // The canonical builder, validation included. A rep whose profile cannot produce a
        // signature gets a named exception saying which field to fix, rather than an empty
        // preview and a Confirm button that never enables. Do not reintroduce a local copy.
        OutreachRenderer.SenderContext sender = OutreachConfirm.senderFromRunningUser();

        List<PreviewItem> out = new List<PreviewItem>();
        for (OutreachGrouper.RecipientGroup g : groups) {
            if (out.size() == PREVIEW_LIMIT) {
                break;
            }
            try {
                OutreachRenderer.Rendered r =
                    OutreachRenderer.render(g, sender, days, tpl.Subject, tpl.HtmlValue);
                PreviewItem item = new PreviewItem();
                item.toAddress = g.toAddress;
                item.subject = r.subject;
                item.bodyHtml = r.bodyHtml;
                item.propertyCount = g.properties.size();
                item.totalUnits = g.totalUnits;
                item.variant = g.variant;
                out.add(item);
            } catch (OutreachRenderer.UnfilledTokenException e) {
                continue;
            }
        }
        return out;
    }

    /**
     * What the screen gets back after a rep confirms a selection. Four channels, kept apart on
     * purpose because collapsing any two of them tells a rep something false:
     *   - messageCount: what actually got sent.
     *   - rejectedAddresses: people already claimed, permanently. Never retry these.
     *   - deferredKeys: transient failures (for example a row lock). Not contacted, safe to
     *     retry, and NOT the same thing as rejected.
     *   - refusals: nothing was sent at all for these.
     *   - overrideWarnings: a message WAS sent, but the rep's contact pick did not apply.
     */
    public class ConfirmResult {
        @AuraEnabled public Id batchId;
        @AuraEnabled public Integer messageCount;
        @AuraEnabled public List<String> rejectedAddresses;
        @AuraEnabled public List<String> refusals;
        @AuraEnabled public List<String> overrideWarnings;
        /** Transient failures, safe to retry. A List rather than a Set because
         *  @AuraEnabled does not support Set<String>, confirmed on this org. */
        @AuraEnabled public List<String> deferredKeys;
    }

    /**
     * Turns a rep's selection into a confirmed batch.
     *
     * This is a thin wrapper. OutreachConfirm does the real work: group, validate sender,
     * render, claim only what rendered, freeze. Nothing clever belongs here; this method's only
     * job is exposing that entry point to Lightning and translating its outcome into shapes a
     * screen can render.
     *
     * `chosenContactByKey` maps a group's emailKey to the Contact record the rep picked. An
     * absent key keeps the defaulted pick, so a rep who changes nothing sends nothing different.
     * The choice is recorded on the message only; Primary_Contact__c is never written back.
     *
     * A throttle breach surfaces as AuraHandledException carrying the original message, so the
     * rep sees the cap and their current count rather than "an internal server error".
     */
    @AuraEnabled
    public static ConfirmResult confirmSelection(List<Id> opportunityIds,
                                                 Map<String, Id> chosenContactByKey) {
        try {
            OutreachConfirm.Outcome outcome =
                OutreachConfirm.confirm(new Set<Id>(opportunityIds), TEMPLATE_NAME, chosenContactByKey);

            ConfirmResult r = new ConfirmResult();
            r.batchId = outcome.batchId;
            r.messageCount = outcome.messageCount;
            r.rejectedAddresses = new List<String>(outcome.rejectedKeys);
            r.refusals = outcome.refusals;
            r.overrideWarnings = outcome.overrideWarnings;
            r.deferredKeys = new List<String>(outcome.deferredKeys);
            return r;
        } catch (OutreachConfirm.ThrottleException e) {
            // Surface the cap and the running total. "An internal server error has occurred"
            // teaches the rep nothing and generates a support request.
            throw asRepFacing(e);
        } catch (OutreachConfirm.SenderProfileException e) {
            // The one that fires FIRST in practice: all three real Users in this org have a null
            // Phone, verified 2026-08-27. Catching only ThrottleException meant the single most
            // likely failure was the one nobody was told about.
            throw asRepFacing(e);
        } catch (OutreachRenderer.MissingTemplateException e) {
            throw asRepFacing(e);
        } catch (OutreachRenderer.UnknownTemplateTokenException e) {
            throw asRepFacing(e);
        }
    }
}
