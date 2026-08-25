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
    static void usesTheLastAtSign() {
        System.assertEquals('a@b@example.com'.substringAfterLast('@'), 'example.com');
        System.assertEquals('a@b@example.com', OutreachEmailKey.normalise('A@B@Example.com'));
    }
}
