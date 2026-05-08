@isTest
private class CampaignDashboardControllerTest {

    @isTest
    static void getCampaignSummary_returnsCampaignAndOpps() {
        Campaign camp = new Campaign(Name = 'Test Project', Type = 'Other', Status = 'In Progress', IsActive = true);
        insert camp;

        Opportunity opp = new Opportunity(
            Name = 'Test Opp',
            StageName = 'Prospecting',
            CloseDate = Date.today().addDays(30),
            CampaignId = camp.Id,
            Property_City__c = 'Test City',
            Property_State__c = 'Nebraska',
            Property_Zip__c = '68101',
            Sales_Status__c = 'Contact Pending'
        );
        insert opp;

        Test.startTest();
        CampaignDashboardController.CampaignSummary result =
            CampaignDashboardController.getCampaignSummary(camp.Id);
        Test.stopTest();

        System.assertNotEquals(null, result);
        System.assertEquals(camp.Id, result.campaign.Id);
        System.assertEquals(1, result.opps.size());
        System.assertEquals(opp.Id, result.opps[0].Id);
    }

    @isTest
    static void getCampaignSummary_emptyCampaign_returnsEmptyOpps() {
        Campaign camp = new Campaign(Name = 'Empty Project', Type = 'Other', Status = 'Planned', IsActive = true);
        insert camp;

        Test.startTest();
        CampaignDashboardController.CampaignSummary result =
            CampaignDashboardController.getCampaignSummary(camp.Id);
        Test.stopTest();

        System.assertEquals(0, result.opps.size());
    }
}
