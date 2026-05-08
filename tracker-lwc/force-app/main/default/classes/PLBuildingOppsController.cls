public with sharing class PLBuildingOppsController {

    @AuraEnabled(cacheable=true)
    public static List<OppRow> getBuildingOpps(Id propertyLocationId) {
        List<OppRow> result = new List<OppRow>();
        if (propertyLocationId == null) {
            return result;
        }

        for (Opportunity o : [
            SELECT Id, Name, StageName, CloseDate, Sales_Status__c,
                   RecordType.Name, Owner.Name
            FROM Opportunity
            WHERE Property_Location__c = :propertyLocationId
              AND Property_Unit__c = null
            ORDER BY CloseDate DESC NULLS LAST, Name
        ]) {
            OppRow r = new OppRow();
            r.id = o.Id;
            r.name = o.Name;
            r.stage = o.StageName;
            r.closeDate = o.CloseDate;
            r.salesStatus = o.Sales_Status__c;
            r.recordType = o.RecordType != null ? o.RecordType.Name : null;
            r.ownerName = o.Owner != null ? o.Owner.Name : null;
            r.url = '/' + o.Id;
            result.add(r);
        }
        return result;
    }

    public class OppRow {
        @AuraEnabled public Id id;
        @AuraEnabled public String name;
        @AuraEnabled public String stage;
        @AuraEnabled public Date closeDate;
        @AuraEnabled public String salesStatus;
        @AuraEnabled public String recordType;
        @AuraEnabled public String ownerName;
        @AuraEnabled public String url;
    }
}
