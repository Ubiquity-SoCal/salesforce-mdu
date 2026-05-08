trigger OpportunityUnitLinkTrigger on Opportunity (after insert, after update) {
    // Maintains the reverse link: when an Opp has Property_Unit__c set/changed,
    // update the target Unit's Opportunity__c so cross-object formulas (e.g.
    // Unit.Opportunity_Stage__c) work without manual backfills.
    //
    // Behavior:
    //  - On insert: if Property_Unit__c is set, link the Unit.
    //  - On update: only act if Property_Unit__c changed.
    //  - When 2+ Opps target the same Unit in one transaction, the last one wins.

    Map<Id, Id> unitIdToOppId = new Map<Id, Id>();

    for (Opportunity opp : Trigger.new) {
        Id newUnit = opp.Property_Unit__c;
        if (newUnit == null) {
            continue;
        }
        if (Trigger.isUpdate) {
            Opportunity oldOpp = Trigger.oldMap.get(opp.Id);
            if (oldOpp.Property_Unit__c == newUnit) {
                continue;
            }
        }
        unitIdToOppId.put(newUnit, opp.Id);
    }

    if (unitIdToOppId.isEmpty()) {
        return;
    }

    List<Property_Unit__c> updates = new List<Property_Unit__c>();
    for (Id unitId : unitIdToOppId.keySet()) {
        updates.add(new Property_Unit__c(
            Id = unitId,
            Opportunity__c = unitIdToOppId.get(unitId)
        ));
    }
    update updates;
}
