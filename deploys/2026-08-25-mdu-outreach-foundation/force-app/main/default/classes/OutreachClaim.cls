/**
 * Reserves recipients for a batch.
 *
 * Deliberately an insert, never an upsert. Upserting on Email_Key__c would UPDATE a row
 * that already exists, which is exactly the case we need to refuse, and the duplicate
 * guarantee would silently evaporate. Insert with allOrNone false lets the platform reject
 * the collisions and keep the rest.
 */
public with sharing class OutreachClaim {

    public class Result {
        public Map<String, Id> claimed = new Map<String, Id>();
        public Set<String> rejected = new Set<String>();
    }

    public static Result claim(Map<String, Id> keyToContactId, Id batchId) {
        Result out = new Result();

        List<String> keys = new List<String>();
        List<Outreach_Recipient__c> toInsert = new List<Outreach_Recipient__c>();

        for (String key : keyToContactId.keySet()) {
            if (String.isBlank(key)) {
                continue;
            }
            keys.add(key);
            toInsert.add(new Outreach_Recipient__c(
                Email_Key__c = key,
                Contact__c = keyToContactId.get(key),
                Last_Batch__c = batchId,
                Status__c = 'Claimed'
            ));
        }

        if (toInsert.isEmpty()) {
            return out;
        }

        List<Database.SaveResult> results = Database.insert(toInsert, false);

        for (Integer i = 0; i < results.size(); i++) {
            Database.SaveResult sr = results[i];
            if (sr.isSuccess()) {
                out.claimed.put(keys[i], sr.getId());
            } else {
                out.rejected.add(keys[i]);
            }
        }
        return out;
    }
}
