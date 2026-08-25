/**
 * Test data shared by every Outreach test class.
 *
 * Opportunities get distinct street addresses on purpose: OpportunityAddressDupHelper
 * blocks duplicates on insert and will fail test setup otherwise.
 */
@isTest
public class OutreachTestData {

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
            Property_Street__c = counter + ' Test Street'
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
