trigger OpportunityAddressDupBlock on Opportunity (before insert, before update) {
    // Blocks creating/updating an Opportunity whose property address matches
    // an existing Opp's. Universal block: re-pursuing a Closed Lost property
    // should reopen the existing record, not create a new one.
    //
    // SF's standard Duplicate Management doesn't support Opportunity, so this
    // is the Apex equivalent.
    //
    // Match key: core address (everything before first comma in
    // Property_Address__c, normalised) + Property_Zip__c. City and State are
    // intentionally NOT in the key because the existing data has them embedded
    // in the address field on ~86% of records, and State varies in casing
    // ('AZ' vs 'Arizona'). Zip is a reliable regional scope.
    //
    // If either Property_Address__c or Property_Zip__c is blank, the check
    // is skipped (insufficient data to dedupe).

    List<Opportunity> toCheck = new List<Opportunity>();
    List<String> keysToLookFor = new List<String>();
    Set<String> rawZips = new Set<String>();

    for (Opportunity opp : Trigger.new) {
        String addr = opp.Property_Address__c;
        String zip = opp.Property_Zip__c;
        if (String.isBlank(addr) || String.isBlank(zip)) {
            continue;
        }
        if (Trigger.isUpdate) {
            Opportunity oldOpp = Trigger.oldMap.get(opp.Id);
            if (oldOpp.Property_Address__c == addr && oldOpp.Property_Zip__c == zip) {
                continue;
            }
        }
        toCheck.add(opp);
        keysToLookFor.add(OpportunityAddressDupHelper.normKey(addr, zip));
        rawZips.add(zip);
    }

    if (toCheck.isEmpty()) {
        return;
    }

    Set<Id> excludeIds = new Set<Id>();
    for (Opportunity opp : Trigger.new) {
        if (opp.Id != null) excludeIds.add(opp.Id);
    }

    // Narrow the candidate pool by Zip (selective + matches our partition).
    Map<String, Opportunity> existingByKey = new Map<String, Opportunity>();
    for (Opportunity existing : [
        SELECT Id, Name, Property_Address__c, Property_Zip__c, StageName
        FROM Opportunity
        WHERE Property_Zip__c IN :rawZips
          AND Property_Address__c != null
          AND Id NOT IN :excludeIds
    ]) {
        String k = OpportunityAddressDupHelper.normKey(
            existing.Property_Address__c, existing.Property_Zip__c);
        if (!existingByKey.containsKey(k)) {
            existingByKey.put(k, existing);
        }
    }

    for (Integer i = 0; i < toCheck.size(); i++) {
        Opportunity opp = toCheck.get(i);
        String key = keysToLookFor.get(i);
        Opportunity match = existingByKey.get(key);
        if (match != null) {
            opp.addError(
                'An Opportunity already exists at this property address: "'
                + match.Name + '" (Stage: ' + match.StageName + ', Id: ' + match.Id + '). '
                + 'Update the existing record instead of creating a duplicate. '
                + 'If the existing Opp is Closed Lost and you are re-pursuing the property, '
                + 'reopen it by changing its Stage.'
            );
        }
    }
}
