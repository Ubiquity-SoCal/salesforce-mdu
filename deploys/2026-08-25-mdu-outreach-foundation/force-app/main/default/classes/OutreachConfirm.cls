/**
 * Turns a selection into a confirmed batch: claim, group, render, freeze.
 *
 * Ordering matters, and the safety argument runs the OPPOSITE direction from an earlier
 * version of this class. Render happens first and claim happens second, because a claim is
 * permanent under the never-re-mail rule: a group that fails to render must never have been
 * claimed, or that person becomes uncontactable forever over a data quality problem (for
 * example a blank first name) that has nothing to do with whether they should be contacted.
 * Rendering is pure string building with no DML, so the only cost of rendering everything
 * first is wasted work on groups that turn out to already be claimed by someone else. That is
 * a trivial price for making the permanent step the LAST thing that can go wrong.
 */
public with sharing class OutreachConfirm {

    public class ThrottleException extends Exception {}

    public class SenderProfileException extends Exception {}

    public class Outcome {
        public Id batchId;
        public Integer messageCount = 0;
        public Set<String> rejectedKeys = new Set<String>();

        /**
         * Claimed by nobody, for a transient reason such as a row lock, most likely because
         * another rep was confirming the same person at that moment. NOT contacted and NOT
         * permanently blocked: these are safe and correct to retry, unlike rejectedKeys.
         */
        public Set<String> deferredKeys = new Set<String>();

        /** Nothing was sent to these. Unreachable property, or a group that would not render. */
        public List<String> refusals = new List<String>();

        /**
         * A message WAS sent, but the rep's contact override did not apply.
         *
         * Kept separate from refusals because those are opposite outcomes and a caller reading
         * one flat list cannot tell them apart. "3 refusals" must not mean "3 people got a
         * message with the wrong greeting". Split before any UI consumed it, on the reasoning
         * that the fix gets more expensive once something is parsing message substrings.
         */
        public List<String> overrideWarnings = new List<String>();
    }

    // Outreach_Setting__mdt does not exist in this org. Attempted as specified in an earlier
    // round: the object and its two fields validate cleanly on their own (proven with an
    // isolated dry-run, numberComponentsDeployed 3, success true), but deploying the Default
    // record alongside the brand new type in the same validate-only deploy fails every time
    // with a platform UNKNOWN_EXCEPTION (error code -315522575, reproduced identically across
    // two attempts, including one deliberate XML correction moving the xsi namespace
    // declaration from each <value> tag up to the <CustomMetadata> root). That is a
    // checkOnly-specific platform limitation on a first-time type-plus-record deploy, not a
    // malformed file, but the net effect is the same one the brief warned about: it blocks the
    // rest of this task. Per the brief's escape hatch, the custom metadata type and its record
    // were deleted and these two values are literal until the project deploys for real instead
    // of validation-only, at which point they belong on
    // Outreach_Setting__mdt.getInstance('Default') again. Confirmed with the reviewer this
    // round: the escape hatch stays; do not restore the type.
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
        applyChosenContacts(groups, chosenContactByKey, out);

        EmailTemplate tpl = [SELECT Subject, HtmlValue FROM EmailTemplate
                             WHERE DeveloperName = :templateDeveloperName LIMIT 1];

        // RENDER BEFORE CLAIMING. This ordering is the safety argument of the whole method.
        //
        // A claim is permanent: the never-re-mail rule means an Outreach_Recipient__c row can
        // never be released, so claiming first and rendering second means a group that fails to
        // render has already burned a real person's only chance of ever being contacted. Nobody
        // notices, because the outcome is a person who quietly never receives anything.
        //
        // That is not hypothetical. A Contact with a blank FirstName leaves [First Name]
        // unfilled and the renderer refuses the message, and 24 Omaha contacts have no first
        // name today. Losing one of them permanently over a missing first name, a data quality
        // problem with nothing to do with whether they should be contacted, is the worst
        // outcome this system can produce.
        //
        // Rendering is pure string building with no DML and no SOQL, so the only cost of doing
        // it first is wasted work on groups that turn out to be already claimed. That is a
        // trivial price for making the permanent step the LAST thing that can go wrong.
        Map<String, OutreachRenderer.Rendered> renderedByKey =
            new Map<String, OutreachRenderer.Rendered>();
        for (OutreachGrouper.RecipientGroup g : groups) {
            try {
                renderedByKey.put(g.emailKey,
                    OutreachRenderer.render(g, sender, days, tpl.Subject, tpl.HtmlValue));
            } catch (OutreachRenderer.UnfilledTokenException e) {
                out.refusals.add(g.toAddress + ': ' + e.getMessage());
            }
        }

        if (renderedByKey.isEmpty()) {
            // Nothing rendered, so there is nothing to claim and no batch worth creating.
            return out;
        }

        insert batch;
        out.batchId = batch.Id;

        // Claim ONLY the groups that actually rendered.
        Map<String, Id> keyToContact = new Map<String, Id>();
        for (OutreachGrouper.RecipientGroup g : groups) {
            if (renderedByKey.containsKey(g.emailKey)) {
                keyToContact.put(g.emailKey, g.contactId);
            }
        }
        OutreachClaim.Result claim = OutreachClaim.claim(keyToContact, batch.Id);
        out.rejectedKeys = claim.rejected;
        out.deferredKeys = claim.deferred;

        List<Outreach_Message__c> messages = new List<Outreach_Message__c>();
        List<OutreachGrouper.RecipientGroup> rendered = new List<OutreachGrouper.RecipientGroup>();

        for (OutreachGrouper.RecipientGroup g : groups) {
            if (!claim.claimed.containsKey(g.emailKey)) {
                continue;
            }
            OutreachRenderer.Rendered r = renderedByKey.get(g.emailKey);
            messages.add(new Outreach_Message__c(
                Batch__c = batch.Id,
                Recipient__c = claim.claimed.get(g.emailKey),
                Contact__c = g.contactId,
                To_Address__c = g.toAddress,
                Subject__c = r.subject,
                Body_Html__c = r.bodyHtml,
                Status__c = 'Queued'));
            rendered.add(g);
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
                                            Map<String, Id> chosenContactByKey,
                                            Outcome out) {
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
            [SELECT Id, FirstName, Email FROM Contact WHERE Id IN :chosenIds]);

        for (OutreachGrouper.RecipientGroup g : groups) {
            if (!chosenContactByKey.containsKey(g.emailKey)) {
                continue;
            }
            Contact c = chosenContacts.get(chosenContactByKey.get(g.emailKey));

            if (c == null) {
                // Silently falling back would tell the rep their choice took when it did not.
                out.overrideWarnings.add(g.toAddress + ': the chosen contact could not be '
                    + 'found, so the default was used instead');
                continue;
            }

            // A picker chooses WHO is greeted, never WHERE the mail goes. Every candidate the
            // UI offers shares this mailbox by construction, so a chosen contact that does not
            // is either a stale id or a caller that is not the picker. Refuse it rather than
            // quietly addressing one person's message to another person's inbox.
            if (OutreachEmailKey.normalise(c.Email) != g.emailKey) {
                out.overrideWarnings.add(g.toAddress + ': the chosen contact does not share '
                    + 'this address, so the default was used instead');
                continue;
            }

            g.contactId = c.Id;
            g.firstName = c.FirstName;
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
