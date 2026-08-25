/**
 * Fills the approved copy for one recipient.
 *
 * A rendered body that still contains a bracketed token is refused, never sent. A draft
 * reaching an owner that reads "Fiber at [Property Name]" is worse than no draft. Ported
 * from the same rule in draft_bulk_outreach_from_list.py.
 */
public with sharing class OutreachRenderer {

    public class UnfilledTokenException extends Exception {}

    public class UnknownTemplateTokenException extends Exception {}

    public class SenderContext {
        public String fullName;
        public String title;
        public String company;
        public String phone;
        public String email;
    }

    public class Rendered {
        public String subject;
        public String bodyHtml;
    }

    private static final Integer MAX_NAMED = 3;

    public static Rendered render(OutreachGrouper.RecipientGroup g, SenderContext sender,
                                  List<String> meetingDays, String subjectTemplate,
                                  String bodyTemplate) {

        Map<String, String> tokens = new Map<String, String>{
            '[First Name]'     => esc(g.firstName),
            '[Property Name]'  => esc(g.named == null ? null : g.named.Name),
            '[Property Block]' => propertyBlock(g),
            '[Sender Name]'    => esc(sender.fullName),
            '[Title]'          => esc(sender.title),
            '[Company]'        => esc(sender.company),
            '[phone]'          => esc(sender.phone),
            '[email]'          => esc(sender.email),
            '[day 1]'          => esc(meetingDays.size() > 0 ? meetingDays[0] : null),
            '[day 2]'          => esc(meetingDays.size() > 1 ? meetingDays[1] : null)
        };

        // Validate the TEMPLATE before substituting anything. This is the half of the old
        // broad guard that was correct to keep, applied where bracketed text is always a
        // token and never data.
        guardTemplate(subjectTemplate, tokens.keySet());
        guardTemplate(bodyTemplate, tokens.keySet());

        Rendered out = new Rendered();
        out.subject = stripTags(apply(subjectTemplate, tokens));
        out.bodyHtml = apply(bodyTemplate, tokens);

        guard(out.subject, tokens.keySet());
        guard(out.bodyHtml, tokens.keySet());
        return out;
    }

    private static String apply(String template, Map<String, String> tokens) {
        String s = template;
        for (String token : tokens.keySet()) {
            String value = tokens.get(token);
            if (value == null) {
                continue;
            }
            s = s.replace(token, value);
        }
        return s;
    }

    /**
     * The sentence fragment naming the property or properties.
     *   A: "Camelot Village (485 units)"
     *   B: "The Richards Apartments, St Frances Apartments and 817 N 47th St (53 units)"
     *   C: "your Omaha portfolio of 17 properties, 170 units in total, including A, B and C"
     */
    private static String propertyBlock(OutreachGrouper.RecipientGroup g) {
        Integer total = (g.totalUnits == null ? 0 : g.totalUnits).intValue();

        if (g.variant == 'A') {
            return esc(g.named.Name) + ' (' + total + ' units)';
        }

        if (g.variant == 'B') {
            List<String> names = new List<String>();
            for (Opportunity o : g.properties) {
                names.add(esc(o.Name));
            }
            String last = names.remove(names.size() - 1);
            return String.join(names, ', ') + ' and ' + last + ' (' + total + ' units)';
        }

        // Prose, not a list. The token sits mid sentence inside a <p>, so emitting a <ul> here
        // would nest a block element inside a paragraph, which Outlook renders inconsistently,
        // and would strand the template's full stop after the closing </ul>. A cold email is
        // also better served by three names and a count than by a seventeen item bullet list.
        List<String> names = new List<String>();
        Integer shown = Math.min(MAX_NAMED, g.properties.size());
        for (Integer i = 0; i < shown; i++) {
            names.add(esc(g.properties[i].Name));
        }
        String last = names.remove(names.size() - 1);
        String named = names.isEmpty() ? last : String.join(names, ', ') + ' and ' + last;

        return 'your Omaha portfolio of ' + g.properties.size() + ' properties, '
            + total + ' units in total, including ' + named;
    }

    /**
     * Refuses a message that still contains one of the KNOWN tokens.
     *
     * Deliberately checks exact token strings rather than an "any bracketed text" regex.
     * Measured against the org 2026-08-25: three Omaha properties and nineteen MDU properties
     * org wide carry square brackets in their real names, such as
     * "Bedford Square [fmr Maplewood Court]", and two of the three Omaha ones are mailable
     * today. A broad regex refused all of them and reported the property's own alternate name
     * as an unfilled token, which reads as nonsense and looks in production like "some
     * properties just never send".
     *
     * The token set is the same map used for substitution, so a token cannot be added to the
     * copy without this guard watching for it. A token MISSPELLED in the template is not caught
     * here; the rep sees it in the mandatory preview instead, which is a human gate the copy
     * passes through anyway.
     *
     * Using contains() rather than a Pattern also removes the last regex literal from this
     * class, and with it the double-backslash trap that has cost this project three rounds.
     */
    /**
     * Refuses a TEMPLATE containing any bracketed run this renderer does not know.
     *
     * The output guard checks exact known tokens, so that a property genuinely named
     * "Bedford Square [fmr Maplewood Court]" is not refused. That is right for output, where
     * brackets are usually data. It is wrong for the template, where brackets are always
     * meant to be tokens, and it left a real hole: the approved copy in
     * build_mdu_outreach_email_docx.py uses [X] and [day], neither of which this renderer
     * substitutes, because [day] appears twice in one sentence and had to become [day 1] and
     * [day 2]. An admin transcribing the approved wording into the Lightning EmailTemplate,
     * which lives outside version control and needs no deploy, would produce messages reading
     * "20 minutes [day] or [day]" and nothing would stop them.
     *
     * So: broad scan here, exact scan on the output. Property names never appear in the
     * template, only in substituted values, so nothing legitimate is caught.
     *
     * Fails once for the whole run with the offending token named, rather than per row,
     * because a wrong template is a configuration mistake and not per-recipient data.
     */
    private static void guardTemplate(String template, Set<String> knownTokens) {
        Matcher m = Pattern.compile('\\[[^\\]]+\\]').matcher(template);
        while (m.find()) {
            if (!knownTokens.contains(m.group(0))) {
                throw new UnknownTemplateTokenException(
                    'The email template contains ' + m.group(0) + ', which this renderer does '
                    + 'not fill. Known tokens are: ' + String.join(new List<String>(knownTokens), ', ')
                    + '. Nothing has been claimed or sent.');
            }
        }
    }

    private static void guard(String rendered, Set<String> tokenNames) {
        for (String token : tokenNames) {
            if (rendered.contains(token)) {
                throw new UnfilledTokenException(
                    'Refusing to send: unfilled token ' + token + ' survived rendering.');
            }
        }
    }

    private static String esc(String raw) {
        return raw == null ? null : raw.escapeHtml4();
    }

    private static String stripTags(String s) {
        return s == null ? null : s.stripHtmlTags();
    }
}
