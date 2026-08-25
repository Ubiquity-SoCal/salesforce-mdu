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

        // Readability only. This guard has NO externally observable effect and cannot be
        // covered by a test: measured against the org 2026-08-25, Database.insert on an empty
        // list consumes zero DML statements and creates zero rows, so deleting this line
        // changes nothing a caller or a test could detect. Kept because it states the intent
        // plainly. Do not write a test claiming to cover it; three separate attempts to do so
        // produced assertions that could not fail.
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
