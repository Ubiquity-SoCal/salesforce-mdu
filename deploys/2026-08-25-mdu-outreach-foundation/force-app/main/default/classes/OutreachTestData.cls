/**
 * Test data shared by every Outreach test class.
 *
 * Opportunities get distinct street addresses on purpose: OpportunityAddressDupHelper
 * blocks duplicates on insert and will fail test setup otherwise.
 */
@isTest
public class OutreachTestData {

    // MDU/SFU. The selection controller filters on this, so test Opportunities must carry it
    // or they are invisible to every query in OutreachSelectionControllerTest.
    public static final Id MDU_RECORD_TYPE_ID = '012WR00000Ra0mkYAB';

    private static Integer counter = 0;

    public static Opportunity opportunity(String name, Integer units) {
        return opportunity(name, units, null);
    }

    public static Opportunity opportunity(String name, Integer units, Contact primary) {
        counter++;
        Opportunity o = new Opportunity(
            Name = name,
            StageName = 'Prospects',
            CloseDate = Date.today().addDays(90),
            Units__c = units,
            Property_City__c = 'Omaha',
            Property_State__c = 'NE',
            Property_Zip__c = '68102',
            Property_Street__c = counter + ' Test Street',
            RecordTypeId = MDU_RECORD_TYPE_ID
        );
        if (primary != null) {
            o.Primary_Contact__c = primary.Id;
        }
        insert o;
        return o;
    }

    public static Contact contact(String firstName, String lastName, String email) {
        Contact c = new Contact(FirstName = firstName, LastName = lastName, Email = email);
        insert c;
        return c;
    }
}
