public with sharing class PropertyLocationSummaryController {

    @AuraEnabled(cacheable=true)
    public static Summary getSummary(Id opportunityId) {
        Summary s = new Summary();
        if (opportunityId == null) {
            return s;
        }

        List<Opportunity> opps = [
            SELECT Property_Location__c,
                   Property_Location__r.Name,
                   Property_Location__r.Property_Unit_Count__c,
                   Property_Location__r.Active_Unit_Count__c
            FROM Opportunity
            WHERE Id = :opportunityId
            LIMIT 1
        ];
        if (opps.isEmpty() || opps[0].Property_Location__c == null) {
            return s;
        }

        Id plId = opps[0].Property_Location__c;
        s.plId = plId;
        s.plName = opps[0].Property_Location__r.Name;
        s.unitCount = opps[0].Property_Location__r.Property_Unit_Count__c;
        s.activeUnitCount = opps[0].Property_Location__r.Active_Unit_Count__c;
        s.oppCount = [
            SELECT COUNT()
            FROM Opportunity
            WHERE Property_Location__c = :plId
        ];
        return s;
    }

    public class Summary {
        @AuraEnabled public Id plId;
        @AuraEnabled public String plName;
        @AuraEnabled public Integer oppCount;
        @AuraEnabled public Decimal unitCount;
        @AuraEnabled public Decimal activeUnitCount;
    }
}
