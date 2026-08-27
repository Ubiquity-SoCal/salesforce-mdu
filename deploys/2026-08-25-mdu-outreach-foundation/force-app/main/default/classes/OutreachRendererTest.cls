@isTest
private class OutreachRendererTest {

    private static final String SUBJECT_TPL = 'Fiber at [Property Name], no cost to ownership';

    private static final String BODY_TPL =
        '<p>Hello [First Name],</p>' +
        '<p>My name is [Sender Name] and I am part of the [Company] team here in Omaha. ' +
        'I am reaching out about [Property Block].</p>' +
        '<p>Would you have 20 minutes [day 1] or [day 2]?</p>' +
        '<p><b>[Sender Name]</b><br>[Company]<br>[phone]  |  [email]</p>';

    private static OutreachRenderer.SenderContext sender() {
        OutreachRenderer.SenderContext s = new OutreachRenderer.SenderContext();
        s.fullName = 'Rosemarie Shortino';
        s.company = 'FiberFirst';
        s.phone = '816-225-5897';
        s.email = 'rosemarie.shortino@ubiquitygp.com';
        return s;
    }

    private static List<String> days() {
        return new List<String>{'Thursday', 'Friday'};
    }

    private static OutreachGrouper.RecipientGroup groupOf(String firstName, List<String> names,
                                                          List<Integer> units) {
        OutreachGrouper.RecipientGroup g = new OutreachGrouper.RecipientGroup();
        g.firstName = firstName;
        g.emailKey = 'test@example.com';
        g.toAddress = 'test@example.com';
        for (Integer i = 0; i < names.size(); i++) {
            g.properties.add(new Opportunity(Name = names[i], Units__c = units[i]));
            g.totalUnits += units[i];
        }
        g.named = g.properties[0];
        Integer n = g.properties.size();
        g.variant = n == 1 ? 'A' : (n <= 3 ? 'B' : 'C');
        return g;
    }

    @isTest
    static void variantAMatchesTheApprovedWording() {
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Michelle', new List<String>{'Camelot Village'}, new List<Integer>{485}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assertEquals('Fiber at Camelot Village, no cost to ownership', r.subject);
        System.assert(r.bodyHtml.contains('Hello Michelle,'));
        System.assert(r.bodyHtml.contains('Camelot Village (485 units)'),
            'one property renders as the approved "Name (N units)" phrasing');
        System.assert(r.bodyHtml.contains('Thursday or Friday'));
        System.assert(r.bodyHtml.contains('Rosemarie Shortino'));
    }

    @isTest
    static void variantBNamesTwoOrThreeInline() {
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Phil',
                new List<String>{'The Richards Apartments', 'St Frances Apartments', '817 N 47th St'},
                new List<Integer>{30, 15, 8}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('The Richards Apartments'));
        System.assert(r.bodyHtml.contains('St Frances Apartments'));
        System.assert(r.bodyHtml.contains('817 N 47th St'));
        System.assert(r.bodyHtml.contains('53 units'), 'variant B states the portfolio total');
        System.assert(!r.bodyHtml.contains('<li>'), 'two or three properties stay inline');
    }

    @isTest
    static void variantCNamesThreeAndCountsTheRestAsProse() {
        List<String> names = new List<String>();
        List<Integer> units = new List<Integer>();
        for (Integer i = 0; i < 17; i++) {
            names.add('Property ' + i);
            units.add(10);
        }
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Paladino', names, units), sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('your Omaha portfolio of 17 properties'));
        System.assert(r.bodyHtml.contains('170 units in total'));
        System.assert(r.bodyHtml.contains('Property 0, Property 1 and Property 2'),
            'three named, the rest carried by the count');
        System.assertEquals(0, r.bodyHtml.countMatches('<ul>'),
            'the token sits mid sentence inside a paragraph; a list here nests a block element '
            + 'inside a <p> and strands the template full stop after the closing tag');
        System.assertEquals(0, r.bodyHtml.countMatches('<li>'));
    }

    @isTest
    static void variantCWithExactlyFourNamesThreeAndCountsOne() {
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Owner',
                new List<String>{'Alpha Court', 'Bravo Place', 'Charlie Row', 'Delta Walk'},
                new List<Integer>{10, 10, 10, 10}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('portfolio of 4 properties'));
        System.assert(r.bodyHtml.contains('Alpha Court, Bravo Place and Charlie Row'));
        System.assert(!r.bodyHtml.contains('Delta Walk'),
            'the fourth is carried by the count, not named');
    }

    @isTest
    static void subjectAlwaysNamesTheNamedProperty() {
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Paladino', new List<String>{'The Frederick', 'Cottonwood East'},
                    new List<Integer>{40, 20}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assertEquals('Fiber at The Frederick, no cost to ownership', r.subject);
    }

    @isTest
    static void aPropertyWhoseRealNameContainsBracketsStillSends() {
        // Not hypothetical. Three Omaha properties carry square brackets in their real names
        // and two of them are mailable today, including this one at 52 units already in
        // Contract Negotiations. A guard that matches any bracketed text refuses them and
        // reports the property's own former name as an unfilled token.
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Michelle', new List<String>{'Bedford Square [fmr Maplewood Court]'},
                    new List<Integer>{52}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('Bedford Square [fmr Maplewood Court]'),
            'a bracketed alternate name is data, not an unfilled token');
        System.assert(r.subject.contains('Bedford Square [fmr Maplewood Court]'),
            'and the subject must survive it too');
    }

    @isTest
    static void refusesATemplateUsingTheApprovedCopysOwnUnknownTokens() {
        // Not hypothetical. build_mdu_outreach_email_docx.py, the single source of the approved
        // wording, uses [X] for units and "[day] or [day]" for the meeting days. This renderer
        // fills neither, because [day] occurs twice in one sentence and had to be split into
        // [day 1] and [day 2]. Transcribing the approved copy verbatim into the Lightning
        // template must fail loudly here, not send with visible brackets.
        String approvedish = '<p>Hello [First Name], about [Property Name] ([X] units).</p>'
            + '<p>Would you have 20 minutes [day] or [day]?</p>';

        Boolean threw = false;
        try {
            OutreachRenderer.render(
                groupOf('Michelle', new List<String>{'Camelot Village'}, new List<Integer>{485}),
                sender(), days(), SUBJECT_TPL, approvedish);
        } catch (OutreachRenderer.UnknownTemplateTokenException e) {
            threw = true;
            System.assert(e.getMessage().contains('[X]') || e.getMessage().contains('[day]'),
                'the message must name the offending token: ' + e.getMessage());
        }
        System.assertEquals(true, threw,
            'an unknown token in the TEMPLATE is a configuration mistake and must stop the run');
    }

    @isTest
    static void aPropertyNamesBracketsDoNotTripTheTemplateGuard() {
        // The template guard is broad, the output guard is exact. This proves the split: a
        // bracketed PROPERTY NAME still renders, because it never appears in the template.
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Michelle', new List<String>{'Bedford Square [fmr Maplewood Court]'},
                    new List<Integer>{52}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('Bedford Square [fmr Maplewood Court]'));
    }

    @isTest
    static void refusesWhenATokenSurvives() {
        // Uses a REAL token rather than a synthetic one. Since the guard checks only the known
        // token set, an invented '[Unknown Token]' can no longer trip it by design, which is
        // the trade accepted when the guard stopped refusing real bracketed property names.
        // This exercises the guarantee the guard still makes: a token the approved copy
        // actually uses, left without a value, is caught. Only one meeting day is supplied, so
        // [day 2] is never substituted.
        Boolean threw = false;
        try {
            OutreachRenderer.render(
                groupOf('Michelle', new List<String>{'Camelot Village'}, new List<Integer>{485}),
                sender(), new List<String>{'Thursday'}, SUBJECT_TPL, BODY_TPL);
        } catch (OutreachRenderer.UnfilledTokenException e) {
            threw = true;
            System.assert(e.getMessage().contains('[day 2]'),
                'the error must name the token that survived');
        }
        System.assertEquals(true, threw,
            'a body reaching an owner with a bracket in it is worse than no email at all');
    }

    @isTest
    static void refusesWhenTheFirstNameIsMissing() {
        Boolean threw = false;
        try {
            OutreachRenderer.render(
                groupOf(null, new List<String>{'Camelot Village'}, new List<Integer>{485}),
                sender(), days(), SUBJECT_TPL, BODY_TPL);
        } catch (OutreachRenderer.UnfilledTokenException e) {
            threw = true;
        }
        System.assertEquals(true, threw, '24 Omaha contacts have no first name; none may slip through');
    }

    @isTest
    static void escapesHtmlInPropertyNames() {
        OutreachRenderer.Rendered r = OutreachRenderer.render(
            groupOf('Michelle', new List<String>{'Bracket <Trap> Apartments'}, new List<Integer>{10}),
            sender(), days(), SUBJECT_TPL, BODY_TPL);

        System.assert(r.bodyHtml.contains('Bracket &lt;Trap&gt; Apartments'),
            'a property name must never inject markup into the body');
    }

    @isTest
    static void aMissingTemplateIsNamedRatherThanThrowingQueryException() {
        try {
            OutreachRenderer.loadTemplate('No_Such_Template_For_This_Test');
            System.assert(false, 'Expected MissingTemplateException');
        } catch (OutreachRenderer.MissingTemplateException e) {
            System.assert(e.getMessage().contains('No_Such_Template_For_This_Test'),
                'The message must name the template an admin has to create, actual: '
                + e.getMessage());
        }
    }

    @isTest
    static void aTextOnlyTemplateIsRefusedWithItsOwnMessage() {
        EmailTemplate textOnly = new EmailTemplate(
            DeveloperName = 'Text_Only', Name = 'Text Only', HtmlValue = null);
        try {
            OutreachRenderer.validateTemplate(textOnly, 'Text_Only');
            System.assert(false, 'Expected MissingTemplateException');
        } catch (OutreachRenderer.MissingTemplateException e) {
            System.assert(e.getMessage().contains('no HTML body'),
                'A text template needs its own message, not the missing-template one, actual: '
                + e.getMessage());
        }
    }

    @isTest
    static void aUsableTemplateComesBackUnchanged() {
        EmailTemplate ok = new EmailTemplate(
            DeveloperName = 'Ok', Name = 'Ok', Subject = 's', HtmlValue = '<p>body</p>');
        System.assertEquals('<p>body</p>',
            OutreachRenderer.validateTemplate(ok, 'Ok').HtmlValue,
            'A valid template must pass straight through');
    }
}
