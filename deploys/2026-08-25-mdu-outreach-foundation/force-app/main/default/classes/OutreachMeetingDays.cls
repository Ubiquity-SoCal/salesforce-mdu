/**
 * The two weekday names offered in "Would you have 20 minutes [day] or [day]?".
 *
 * There is deliberately no fixed default. A hardcoded "Tuesday or Thursday" is wrong the
 * moment the merge runs on a Wednesday, so the days are computed from the run date and
 * frozen onto the batch at confirm.
 *
 * Ported from draft_bulk_outreach_from_list.py::next_meeting_days.
 */
public with sharing class OutreachMeetingDays {

    /** Calendar days of lead before the first day offered. Two means a Tuesday run
     *  offers Thursday at the earliest, never tomorrow. */
    private static final Integer LEAD_DAYS = 2;

    private static final List<String> DAY_NAMES = new List<String>{
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
    };

    public static List<String> nextTwo(Date runDate) {
        List<String> out = new List<String>();
        Date d = runDate.addDays(LEAD_DAYS);

        while (out.size() < 2) {
            Integer dow = dayOfWeekMondayZero(d);
            if (dow < 5) {
                out.add(DAY_NAMES[dow]);
            }
            d = d.addDays(1);
        }
        return out;
    }

    /**
     * Apex has no weekday accessor on Date. Datetime.format('u') would depend on the
     * running user's locale, so the day is derived arithmetically instead.
     * 1900-01-01 was a Monday, which makes it a safe zero point.
     */
    private static Integer dayOfWeekMondayZero(Date d) {
        Date mondayEpoch = Date.newInstance(1900, 1, 1);
        Integer days = mondayEpoch.daysBetween(d);
        Integer dow = Math.mod(days, 7);
        return dow < 0 ? dow + 7 : dow;
    }
}
