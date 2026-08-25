/**
 * Turns a selection into a confirmed batch: claim, group, render, freeze.
 *
 * Ordering matters. Claiming happens first, so a recipient another batch already holds is
 * refused before any work is spent rendering for them.
 */
public with sharing class OutreachConfirm {

    public class ThrottleException extends Exception {}

    public class SenderProfileException extends Exception {}

    public class Outcome {
        public Id batchId;
        public Integer messageCount = 0;
        public Set<String> rejectedKeys = new Set<String>();
        public List<String> refusals = new List<String>();
    }

    // Outreach_Setting__mdt does not exist in this org. Attempted as specified: the object
    // and its two fields validate cleanly on their own (proven with an isolated dry-run,
    // numberComponentsDeployed 3, success true), but deploying the Default record alongside
    // the brand new type in the same validate-only deploy fails every time with a platform
    // UNKNOWN_EXCEPTION (error code -315522575, reproduced identically across two attempts,
    // including one deliberate XML correction moving the xsi namespace declaration from each
    // <value> tag up to the <CustomMetadata> root). That is a checkOnly-specific platform
    // limitation on a first-time type-plus-record deploy, not a malformed file, but the net
    // effect is the same one the brief warned about: it blocks the rest of this task. Per the
    // brief's escape hatch, the custom metadata type and its record were deleted and these two
    // values are literal until the project deploys for real instead of validation-only, at
    // which point they belong on Outreach_Setting__mdt.getInstance('Default') again.
    private static final Integer PER_REP_DAILY_CAP = 40;
    private static final Integer ORG_DAILY_CAP = 100;

    public static Outcome confirm(Set<Id> opportunityIds, String templateDeveloperName) {
        return confirm(opportunityIds, templateDeveloperName, new Map<String, Id>());
    }

    public static Outcome confirm(Set<Id> opportunityIds, String templateDeveloperName,
                                  Map<String, Id> chosenContactByKey) {
        Outcome out = new Outcome();

        List<OutreachGrouper.RecipientGroup> groups = OutreachGrouper.group(opportunityIds);
        reportUnreachable(opportunityIds, groups, out);

        if (groups.isEmpty()) {
            return out;
        }

        enforceThrottle(groups.size());

        // Before any DML. A sender whose profile cannot produce a signature must cost nothing:
        // claiming first would burn recipients permanently under the never-re-mail rule, for a
        // batch that was never going to render.
        OutreachRenderer.SenderContext sender = senderFromRunningUser();

        List<String> days = OutreachMeetingDays.nextTwo(Date.today());

        Outreach_Batch__c batch = new Outreach_Batch__c(
            Status__c = 'Confirmed',
            Template_Name__c = templateDeveloperName,
            Meeting_Day_1__c = days[0],
            Meeting_Day_2__c = days[1],
            Confirmed_At__c = System.now());
        insert batch;
        out.batchId = batch.Id;

        applyChosenContacts(groups, chosenContactByKey);

        Map<String, Id> keyToContact = new Map<String, Id>();
        for (OutreachGrouper.RecipientGroup g : groups) {
            keyToContact.put(g.emailKey, g.contactId);
        }
        OutreachClaim.Result claim = OutreachClaim.claim(keyToContact, batch.Id);
        out.rejectedKeys = claim.rejected;

        EmailTemplate tpl = [SELECT Subject, HtmlValue FROM EmailTemplate
                             WHERE DeveloperName = :templateDeveloperName LIMIT 1];

        List<Outreach_Message__c> messages = new List<Outreach_Message__c>();
        List<OutreachGrouper.RecipientGroup> rendered = new List<OutreachGrouper.RecipientGroup>();

        for (OutreachGrouper.RecipientGroup g : groups) {
            if (!claim.claimed.containsKey(g.emailKey)) {
                continue;
            }
            try {
                OutreachRenderer.Rendered r =
                    OutreachRenderer.render(g, sender, days, tpl.Subject, tpl.HtmlValue);
                messages.add(new Outreach_Message__c(
                    Batch__c = batch.Id,
                    Recipient__c = claim.claimed.get(g.emailKey),
                    Contact__c = g.contactId,
                    To_Address__c = g.toAddress,
                    Subject__c = r.subject,
                    Body_Html__c = r.bodyHtml,
                    Status__c = 'Queued'));
                rendered.add(g);
            } catch (OutreachRenderer.UnfilledTokenException e) {
                out.refusals.add(g.toAddress + ': ' + e.getMessage());
            }
        }

        insert messages;
        out.messageCount = messages.size();

        List<Outreach_Message_Property__c> lines = new List<Outreach_Message_Property__c>();
        for (Integer i = 0; i < messages.size(); i++) {
            OutreachGrouper.RecipientGroup g = rendered[i];
            for (Opportunity o : g.properties) {
                lines.add(new Outreach_Message_Property__c(
                    Message__c = messages[i].Id,
                    Opportunity__c = o.Id,
                    Is_Named__c = (o.Id == g.named.Id)));
            }
        }
        insert lines;

        return out;
    }

    /**
     * Applies a rep's explicit Contact pick over the grouper's default, before claiming and
     * rendering, so the greeting, the linked Contact and the frozen body all agree.
     *
     * OutreachGrouper.RecipientGroup carries exactly one contactId per email key, not a list
     * of every Contact that shares the address, so the override is resolved with a direct
     * bulk lookup of the chosen Contacts rather than a search through a candidate list the
     * grouper does not track.
     */
    private static void applyChosenContacts(List<OutreachGrouper.RecipientGroup> groups,
                                            Map<String, Id> chosenContactByKey) {
        if (chosenContactByKey == null || chosenContactByKey.isEmpty()) {
            return;
        }

        Set<Id> chosenIds = new Set<Id>();
        for (Id chosenId : chosenContactByKey.values()) {
            if (chosenId != null) {
                chosenIds.add(chosenId);
            }
        }
        if (chosenIds.isEmpty()) {
            return;
        }

        Map<Id, Contact> chosenContacts = new Map<Id, Contact>(
            [SELECT Id, FirstName FROM Contact WHERE Id IN :chosenIds]);

        for (OutreachGrouper.RecipientGroup g : groups) {
            if (!chosenContactByKey.containsKey(g.emailKey)) {
                continue;
            }
            Contact c = chosenContacts.get(chosenContactByKey.get(g.emailKey));
            if (c != null) {
                g.contactId = c.Id;
                g.firstName = c.FirstName;
            }
        }
    }

    private static void reportUnreachable(Set<Id> opportunityIds,
                                          List<OutreachGrouper.RecipientGroup> groups,
                                          Outcome out) {
        Set<Id> covered = new Set<Id>();
        for (OutreachGrouper.RecipientGroup g : groups) {
            for (Opportunity o : g.properties) {
                covered.add(o.Id);
            }
        }
        for (Opportunity o : [SELECT Id, Name FROM Opportunity
                              WHERE Id IN :opportunityIds AND Id NOT IN :covered]) {
            out.refusals.add(o.Name + ': no contact with a usable email address');
        }
    }

    private static void enforceThrottle(Integer wanted) {
        Integer perRep = PER_REP_DAILY_CAP;
        Integer orgCap = ORG_DAILY_CAP;

        DateTime dayStart = DateTime.newInstance(Date.today(), Time.newInstance(0, 0, 0, 0));

        Integer mineToday = [SELECT COUNT() FROM Outreach_Recipient__c
                             WHERE CreatedDate >= :dayStart AND CreatedById = :UserInfo.getUserId()];
        if (mineToday + wanted > perRep) {
            throw new ThrottleException('Daily cap for you is ' + perRep
                + '. You have claimed ' + mineToday + ' today and asked for ' + wanted + '.');
        }

        Integer orgToday = [SELECT COUNT() FROM Outreach_Recipient__c WHERE CreatedDate >= :dayStart];
        if (orgToday + wanted > orgCap) {
            throw new ThrottleException('Org wide daily cap is ' + orgCap
                + '. The org has claimed ' + orgToday + ' today and you asked for ' + wanted + '.');
        }
    }

    /**
     * Builds the signature from the running user's own record, and REFUSES THE RUN if that
     * record cannot produce a complete signature.
     *
     * Measured against the org 2026-08-25: Title, CompanyName and Phone are null on every
     * User who would send this, including both reps. Without this check the run proceeds,
     * every rendered body keeps an unfilled [phone] token, the renderer refuses all of them
     * one by one, and the rep sees a batch that produced nothing with no idea why.
     *
     * A missing sender phone is a configuration mistake, not per-row data, so it stops the
     * run ONCE with a message naming what to fix. Same principle the Python original used
     * for an unset --sender-phone.
     */
    private static OutreachRenderer.SenderContext senderFromRunningUser() {
        User u = [SELECT Name, Title, CompanyName, Phone, Email FROM User
                  WHERE Id = :UserInfo.getUserId()];

        List<String> missing = new List<String>();
        if (String.isBlank(u.Phone)) {
            missing.add('Phone');
        }
        if (String.isBlank(u.Email)) {
            missing.add('Email');
        }
        if (!missing.isEmpty()) {
            throw new SenderProfileException(
                'Your Salesforce user record is missing ' + String.join(missing, ' and ')
                + ', which the email signature needs. Set it on your own user record in Setup, '
                + 'then confirm this batch again. Nothing has been claimed or sent.');
        }

        OutreachRenderer.SenderContext s = new OutreachRenderer.SenderContext();
        s.fullName = u.Name;
        s.title = u.Title;
        // Company defaults rather than refusing: the FiberFirst versus Ubiquity decision is
        // still open, so a blank CompanyName is expected today, not a misconfiguration.
        s.company = String.isBlank(u.CompanyName) ? 'FiberFirst' : u.CompanyName;
        s.phone = u.Phone;
        s.email = u.Email;
        return s;
    }
}
