/**
 * Fills the approved copy for one recipient.
 *
 * A rendered body that still contains a bracketed token is refused, never sent. A draft
 * reaching an owner that reads "Fiber at [Property Name]" is worse than no draft. Ported
 * from the same rule in draft_bulk_outreach_from_list.py.
 */
public with sharing class OutreachRenderer {

    public class UnfilledTokenException extends Exception {}

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

        Rendered out = new Rendered();
        out.subject = stripTags(apply(subjectTemplate, tokens));
        out.bodyHtml = apply(bodyTemplate, tokens);

        guard(out.subject);
        guard(out.bodyHtml);
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

    private static void guard(String rendered) {
        Matcher m = Pattern.compile('\\[[^\\]]+\\]').matcher(rendered);
        if (m.find()) {
            throw new UnfilledTokenException(
                'Refusing to send: unfilled token ' + m.group(0) + ' survived rendering.');
        }
    }

    private static String esc(String raw) {
        return raw == null ? null : raw.escapeHtml4();
    }

    private static String stripTags(String s) {
        return s == null ? null : s.stripHtmlTags();
    }
}
