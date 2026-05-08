public with sharing class MduCleanupDashboardController {

    public class CleanupCategory {
        @AuraEnabled public String key;
        @AuraEnabled public String label;
        @AuraEnabled public String severity;
        @AuraEnabled public Integer count;
        @AuraEnabled public List<CleanupRow> rows;
    }

    public class CleanupRow {
        @AuraEnabled public Id recordId;
        @AuraEnabled public String recordType;
        @AuraEnabled public String name;
        @AuraEnabled public String stage;
        @AuraEnabled public String agreementType;
        @AuraEnabled public String status;
        @AuraEnabled public Date signedDate;
        @AuraEnabled public String oppName;
        @AuraEnabled public Id oppId;
        @AuraEnabled public String oppOwner;
        @AuraEnabled public String reAssigned;
        @AuraEnabled public String city;
        @AuraEnabled public String stateCode;
        @AuraEnabled public Date projectedClose;
        @AuraEnabled public Date lastModified;
        @AuraEnabled public String missingFields;
    }

    private static final Set<String> ACTIVE_STAGES = new Set<String>{
        'Engaged', 'Contract Negotiations', 'ROE Secured', 'Under Contract'
    };
    private static final Set<String> POST_ROE_STAGES = new Set<String>{
        'ROE Secured', 'Contract Negotiations', 'Under Contract'
    };

    @AuraEnabled(cacheable=true)
    public static List<CleanupCategory> getCleanupSummary() {
        List<CleanupCategory> result = new List<CleanupCategory>();

        // 1. Agreements missing IronClad ID - High (Completed/Archive)
        result.add(buildAgreementMissingIcCategory(
            'ic_high',
            'Missing IronClad ID — High',
            'critical',
            new Set<String>{'Completed', 'Archive'}
        ));

        // 2. Agreements missing IronClad ID - Medium (Sign)
        result.add(buildAgreementMissingIcCategory(
            'ic_med',
            'Missing IronClad ID — Out for Signature',
            'warning',
            new Set<String>{'Sign'}
        ));

        // 3. Active Opps without Property Location
        result.add(buildOppMissingFieldCategory(
            'no_property_location',
            'Active Opps: No Property Location',
            'warning',
            'Property_Location__c = null',
            ACTIVE_STAGES
        ));

        // 4. Active Opps without RE Assigned (ROE+)
        result.add(buildOppMissingFieldCategory(
            'no_re',
            'Post-Engagement: No RE Assigned',
            'warning',
            'RE_Assigned__c = null',
            POST_ROE_STAGES
        ));

        // 5. Opps in active negotiation without Projected Close Date
        result.add(buildOppMissingFieldCategory(
            'no_close',
            'Active Pursuits: No Projected Close Date',
            'info',
            'Projected_Close_Date__c = null',
            POST_ROE_STAGES
        ));

        // 6. Under Contract Opps without a signed PAL
        result.add(buildUnderContractNoPalCategory());

        // 7. Stale active Opps (no modification in 60+ days)
        result.add(buildStaleOppsCategory());

        return result;
    }

    private static CleanupCategory buildAgreementMissingIcCategory(
        String key, String label, String severity, Set<String> statuses
    ) {
        CleanupCategory c = new CleanupCategory();
        c.key = key;
        c.label = label;
        c.severity = severity;
        c.rows = new List<CleanupRow>();
        for (Agreement__c a : [
            SELECT Id, Name, Agreement_Type__c, Status__c, Signed_Date__c,
                   Opportunity__c, Opportunity__r.Name, Opportunity__r.StageName,
                   Opportunity__r.Owner.Name, Opportunity__r.RE_Assigned__r.Name,
                   Opportunity__r.Property_City__c, Opportunity__r.Property_State__c,
                   LastModifiedDate
            FROM Agreement__c
            WHERE Status__c IN :statuses
              AND IronClad_ID__c = NULL
              AND Opportunity__r.RecordType.DeveloperName = 'MDU'
            ORDER BY Signed_Date__c DESC NULLS LAST
            LIMIT 500
        ]) {
            CleanupRow row = new CleanupRow();
            row.recordId = a.Id;
            row.recordType = 'Agreement';
            row.name = a.Name;
            row.agreementType = a.Agreement_Type__c;
            row.status = a.Status__c;
            row.signedDate = a.Signed_Date__c;
            row.oppId = a.Opportunity__c;
            row.oppName = a.Opportunity__r.Name;
            row.stage = a.Opportunity__r.StageName;
            row.oppOwner = a.Opportunity__r.Owner != null ? a.Opportunity__r.Owner.Name : null;
            row.reAssigned = a.Opportunity__r.RE_Assigned__r != null ? a.Opportunity__r.RE_Assigned__r.Name : null;
            row.city = a.Opportunity__r.Property_City__c;
            row.stateCode = a.Opportunity__r.Property_State__c;
            row.lastModified = a.LastModifiedDate != null ? a.LastModifiedDate.date() : null;
            c.rows.add(row);
        }
        c.count = c.rows.size();
        return c;
    }

    private static CleanupCategory buildOppMissingFieldCategory(
        String key, String label, String severity, String missingFieldClause, Set<String> stages
    ) {
        CleanupCategory c = new CleanupCategory();
        c.key = key;
        c.label = label;
        c.severity = severity;
        c.rows = new List<CleanupRow>();

        String soql =
            'SELECT Id, Name, StageName, Property_City__c, Property_State__c, ' +
            ' Property_Location__c, Projected_Close_Date__c, ' +
            ' Owner.Name, RE_Assigned__r.Name, LastModifiedDate ' +
            'FROM Opportunity ' +
            'WHERE RecordType.DeveloperName = \'MDU\' ' +
            'AND IsClosed = FALSE ' +
            'AND StageName IN :stages ' +
            'AND ' + missingFieldClause + ' ' +
            'ORDER BY LastModifiedDate DESC ' +
            'LIMIT 500';
        for (Opportunity o : Database.query(soql)) {
            CleanupRow row = new CleanupRow();
            row.recordId = o.Id;
            row.recordType = 'Opportunity';
            row.name = o.Name;
            row.oppId = o.Id;
            row.oppName = o.Name;
            row.stage = o.StageName;
            row.oppOwner = o.Owner != null ? o.Owner.Name : null;
            row.reAssigned = o.RE_Assigned__r != null ? o.RE_Assigned__r.Name : null;
            row.city = o.Property_City__c;
            row.stateCode = o.Property_State__c;
            row.projectedClose = o.Projected_Close_Date__c;
            row.lastModified = o.LastModifiedDate != null ? o.LastModifiedDate.date() : null;
            c.rows.add(row);
        }
        c.count = c.rows.size();
        return c;
    }

    private static CleanupCategory buildUnderContractNoPalCategory() {
        CleanupCategory c = new CleanupCategory();
        c.key = 'under_contract_no_pal';
        c.label = 'Under Contract: No Signed PAL';
        c.severity = 'critical';
        c.rows = new List<CleanupRow>();

        Set<Id> oppsWithSignedPal = new Set<Id>();
        for (Agreement__c a : [
            SELECT Opportunity__c FROM Agreement__c
            WHERE Agreement_Type__c = 'PAL'
              AND Status__c IN ('Completed', 'Archive', 'Sign')
              AND Opportunity__r.RecordType.DeveloperName = 'MDU'
              AND Opportunity__r.StageName = 'Under Contract'
        ]) {
            oppsWithSignedPal.add(a.Opportunity__c);
        }

        for (Opportunity o : [
            SELECT Id, Name, StageName, Property_City__c, Property_State__c,
                   Owner.Name, RE_Assigned__r.Name, LastModifiedDate
            FROM Opportunity
            WHERE RecordType.DeveloperName = 'MDU'
              AND StageName = 'Under Contract'
              AND IsClosed = FALSE
            ORDER BY LastModifiedDate DESC
            LIMIT 500
        ]) {
            if (oppsWithSignedPal.contains(o.Id)) continue;
            CleanupRow row = new CleanupRow();
            row.recordId = o.Id;
            row.recordType = 'Opportunity';
            row.name = o.Name;
            row.oppId = o.Id;
            row.oppName = o.Name;
            row.stage = o.StageName;
            row.oppOwner = o.Owner != null ? o.Owner.Name : null;
            row.reAssigned = o.RE_Assigned__r != null ? o.RE_Assigned__r.Name : null;
            row.city = o.Property_City__c;
            row.stateCode = o.Property_State__c;
            row.lastModified = o.LastModifiedDate != null ? o.LastModifiedDate.date() : null;
            c.rows.add(row);
        }
        c.count = c.rows.size();
        return c;
    }

    private static CleanupCategory buildStaleOppsCategory() {
        CleanupCategory c = new CleanupCategory();
        c.key = 'stale';
        c.label = 'Stale Active Opps (60+ days)';
        c.severity = 'info';
        c.rows = new List<CleanupRow>();

        DateTime threshold = DateTime.now().addDays(-60);
        for (Opportunity o : [
            SELECT Id, Name, StageName, Property_City__c, Property_State__c,
                   Owner.Name, RE_Assigned__r.Name, LastModifiedDate
            FROM Opportunity
            WHERE RecordType.DeveloperName = 'MDU'
              AND IsClosed = FALSE
              AND StageName IN :ACTIVE_STAGES
              AND LastModifiedDate < :threshold
            ORDER BY LastModifiedDate ASC
            LIMIT 500
        ]) {
            CleanupRow row = new CleanupRow();
            row.recordId = o.Id;
            row.recordType = 'Opportunity';
            row.name = o.Name;
            row.oppId = o.Id;
            row.oppName = o.Name;
            row.stage = o.StageName;
            row.oppOwner = o.Owner != null ? o.Owner.Name : null;
            row.reAssigned = o.RE_Assigned__r != null ? o.RE_Assigned__r.Name : null;
            row.city = o.Property_City__c;
            row.stateCode = o.Property_State__c;
            row.lastModified = o.LastModifiedDate != null ? o.LastModifiedDate.date() : null;
            c.rows.add(row);
        }
        c.count = c.rows.size();
        return c;
    }
}
