public with sharing class CampaignDashboardController {

    @AuraEnabled(cacheable=true)
    public static CampaignSummary getCampaignSummary(Id campaignId) {
        CampaignSummary result = new CampaignSummary();

        Campaign camp = [
            SELECT Id, Name, Type, Status, StartDate, EndDate, IsActive, Description,
                   NumberOfOpportunities, AmountAllOpportunities, Resolution_Stage__c
            FROM Campaign
            WHERE Id = :campaignId
            LIMIT 1
        ];
        result.campaign = camp;

        result.opps = [
            SELECT Id, Name, StageName, Sales_Status__c, Sub_Bucket__c, CloseDate,
                   LastStageChangeDate, OwnerId, Owner.Name,
                   RE_Assigned__c, RE_Assigned__r.Name,
                   Loss_Reason__c, Units__c,
                   Property_State__c, Property_City__c, Property_Address__c,
                   Agreement_Name__c,
                   Submitted_to_Market__c, Submitted_to_FiberFirst__c,
                   RecordType.Name, RecordType.DeveloperName
            FROM Opportunity
            WHERE CampaignId = :campaignId
            ORDER BY Property_State__c NULLS LAST, Name
        ];

        result.siteTrackerProjects = [
            SELECT Id, Name, Build_Status__c, Site_Status__c,
                   Design_Phase_Complete_A__c,
                   Opportunity__c, Opportunity__r.Name, Opportunity__r.Property_State__c,
                   Opportunity__r.Units__c
            FROM SiteTracker_Project__c
            WHERE Opportunity__r.CampaignId = :campaignId
            ORDER BY Build_Status__c NULLS LAST, Name
        ];

        result.agreements = [
            SELECT Id, Agreement_Type__c, Status__c, Signed_Date__c,
                   IronClad_Record__r.Workflow_Completed_Date__c,
                   Opportunity__c, Opportunity__r.Name, Opportunity__r.Property_State__c,
                   Opportunity__r.Units__c, Opportunity__r.Owner.Name
            FROM Agreement__c
            WHERE Opportunity__r.CampaignId = :campaignId
              AND Status__c = 'Completed'
            ORDER BY Signed_Date__c DESC NULLS LAST
        ];

        return result;
    }

    public class CampaignSummary {
        @AuraEnabled public Campaign campaign;
        @AuraEnabled public List<Opportunity> opps;
        @AuraEnabled public List<SiteTracker_Project__c> siteTrackerProjects;
        @AuraEnabled public List<Agreement__c> agreements;
    }
}
