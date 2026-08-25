@isTest
private class OutreachMeetingDaysTest {

    // 2026-08-24 is a Monday. Expected values are the verified output of the Python
    // original, run across a full week on 2026-08-25.
    private static final Date MONDAY = Date.newInstance(2026, 8, 24);

    private static void assertOffers(Integer daysAfterMonday, String first, String second) {
        List<String> got = OutreachMeetingDays.nextTwo(MONDAY.addDays(daysAfterMonday));
        System.assertEquals(first, got[0]);
        System.assertEquals(second, got[1]);
    }

    @isTest
    static void mondayOffersWednesdayAndThursday() { assertOffers(0, 'Wednesday', 'Thursday'); }

    @isTest
    static void tuesdayOffersThursdayAndFriday() { assertOffers(1, 'Thursday', 'Friday'); }

    @isTest
    static void wednesdayOffersFridayAndMonday() { assertOffers(2, 'Friday', 'Monday'); }

    @isTest
    static void thursdayOffersMondayAndTuesday() { assertOffers(3, 'Monday', 'Tuesday'); }

    @isTest
    static void fridayOffersMondayAndTuesday() { assertOffers(4, 'Monday', 'Tuesday'); }

    @isTest
    static void saturdayOffersMondayAndTuesday() { assertOffers(5, 'Monday', 'Tuesday'); }

    @isTest
    static void sundayOffersTuesdayAndWednesday() {
        // Sunday plus the two day lead lands on Tuesday. Offering Monday would be one day
        // out and would break the lead rule. The prose table in the old doc says Monday
        // or Tuesday here and is wrong.
        assertOffers(6, 'Tuesday', 'Wednesday');
    }

    @isTest
    static void neverOffersAWeekend() {
        Set<String> weekend = new Set<String>{'Saturday', 'Sunday'};
        for (Integer i = 0; i < 30; i++) {
            for (String day : OutreachMeetingDays.nextTwo(MONDAY.addDays(i))) {
                System.assertEquals(false, weekend.contains(day),
                    'offered a weekend for run date ' + MONDAY.addDays(i));
            }
        }
    }

    @isTest
    static void alwaysReturnsExactlyTwo() {
        for (Integer i = 0; i < 30; i++) {
            System.assertEquals(2, OutreachMeetingDays.nextTwo(MONDAY.addDays(i)).size());
        }
    }
}
