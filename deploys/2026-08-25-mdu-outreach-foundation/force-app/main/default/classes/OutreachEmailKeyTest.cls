@isTest
private class OutreachEmailKeyTest {

    @isTest
    static void lowercasesAndTrims() {
        System.assertEquals('owner@example.com', OutreachEmailKey.normalise('  Owner@Example.COM '));
    }

    @isTest
    static void stripsPlusTags() {
        System.assertEquals('owner@example.com', OutreachEmailKey.normalise('owner+mdu@example.com'));
    }

    @isTest
    static void stripsDotsForGmailOnly() {
        System.assertEquals('johnsmith@gmail.com', OutreachEmailKey.normalise('john.smith@gmail.com'));
        System.assertEquals('johnsmith@googlemail.com', OutreachEmailKey.normalise('john.smith@googlemail.com'));
    }

    @isTest
    static void keepsDotsEverywhereElse() {
        System.assertEquals('john.smith@example.com', OutreachEmailKey.normalise('John.Smith@Example.com'),
            'dots are significant outside gmail and must not be stripped');
    }

    @isTest
    static void realOmahaAddressesSurviveUnchanged() {
        System.assertEquals('mhardy@elevateliving.com', OutreachEmailKey.normalise('mhardy@elevateliving.com'));
        System.assertEquals('sheiman@burlingtoncapital.com', OutreachEmailKey.normalise('sheiman@burlingtoncapital.com'));
    }

    @isTest
    static void rejectsUnusableInput() {
        System.assertEquals(null, OutreachEmailKey.normalise(null));
        System.assertEquals(null, OutreachEmailKey.normalise('   '));
        System.assertEquals(null, OutreachEmailKey.normalise('no-at-sign'));
        System.assertEquals(null, OutreachEmailKey.normalise('@example.com'));
        System.assertEquals(null, OutreachEmailKey.normalise('owner@'));
        System.assertEquals(null, OutreachEmailKey.normalise('+only@example.com'),
            'a local part that is nothing but a plus tag leaves no address');
    }

    @isTest
    static void usesTheLastAtSignInAWayThatWouldFailIfItUsedTheFirst() {
        // Chosen so the two readings diverge observably. Splitting at the LAST @ gives
        // local 'a.b@x' and domain 'gmail.com', so dot folding fires and the dot goes.
        // Splitting at the FIRST @ gives domain 'x@gmail.com', which is not in
        // DOTLESS_DOMAINS, so the dot survives. A plain equality on 'a@b@example.com'
        // cannot tell these apart, which is why the earlier version of this test passed
        // under a knowingly broken implementation.
        System.assertEquals('ab@x@gmail.com', OutreachEmailKey.normalise('a.b@x@gmail.com'));
    }

    @isTest
    static void whitespaceBesideTheAtSignDoesNotCreateASecondKey() {
        String canonical = OutreachEmailKey.normalise('owner@example.com');
        System.assertEquals(canonical, OutreachEmailKey.normalise('owner @example.com'));
        System.assertEquals(canonical, OutreachEmailKey.normalise('owner@ example.com'));
        System.assertEquals(canonical, OutreachEmailKey.normalise('own er@exam ple.com'),
            'one person with a stray space must never become two recipients');
    }

    @isTest
    static void whitespaceDoesNotSilentlyDisableDotFolding() {
        System.assertEquals('johnsmith@gmail.com',
            OutreachEmailKey.normalise('john.smith@ gmail.com'),
            'a space before the domain must not stop it matching DOTLESS_DOMAINS');
    }

    @isTest
    static void plusTagAndDotFoldingApplyTogetherOnGmail() {
        System.assertEquals('johndoe@gmail.com',
            OutreachEmailKey.normalise('john.doe+work@gmail.com'));
    }

    @isTest
    static void anUppercaseGmailDomainStillFolds() {
        System.assertEquals('johnsmith@gmail.com',
            OutreachEmailKey.normalise('John.Smith@GMAIL.COM'));
    }

    @isTest
    static void aDomainWithNoDotIsRejected() {
        System.assertEquals(null, OutreachEmailKey.normalise('owner@localhost'));
        System.assertEquals(null, OutreachEmailKey.normalise('owner@.com'));
        System.assertEquals(null, OutreachEmailKey.normalise('owner@example.'));
    }
}
