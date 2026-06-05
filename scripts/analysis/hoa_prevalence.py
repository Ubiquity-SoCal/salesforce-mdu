"""
HOA prevalence analysis across MDU Opportunities, with emphasis on California
and on the two PAL/ROE cleanup worklists. Read-only.

HOA flag = Opportunity.HOA__c (boolean checkbox). NOTE: a checkbox defaults to
false, so HOA=false can mean "not an HOA" OR "not yet flagged" -- the true count
is a FLOOR, not a guaranteed-complete census.
"""
import os
from collections import Counter
from simple_salesforce import Salesforce

USER="cass1@ubiquitygp.com"; PW="Hawaiian1984"; TOK="IBSKT6CFUpSUJWxq1CMm0HkFC"
sf = Salesforce(username=os.environ.get("SF_MAIN_USERNAME", USER),
                password=os.environ.get("SF_MAIN_PASSWORD", PW),
                security_token=os.environ.get("SF_MAIN_TOKEN", TOK))

def qall(q):
    r = sf.query(q); recs = r["records"]
    while not r["done"]:
        r = sf.query_more(r["nextRecordsUrl"], True); recs += r["records"]
    return recs

def c(q):
    return sf.query(q)["records"][0]["expr0"]

BEYOND = "('PAL/ROE Complete','Marketing/Bulk In Progress','Marketing/Bulk Complete')"

opps = qall("SELECT Property_State__c, HOA__c FROM Opportunity WHERE RecordType.DeveloperName='MDU'")
tot = Counter(); hoa = Counter()
for o in opps:
    st = o["Property_State__c"] or "(blank)"
    tot[st] += 1
    if o["HOA__c"]: hoa[st] += 1
T = len(opps); H = sum(hoa.values())
print(f"=== All MDU Opps: {T} total | HOA flagged: {H} ({100*H/T:.1f}%) ===")
print(f"{'State':<10}{'Opps':>7}{'HOA':>7}{'HOA%':>8}")
for st, n in tot.most_common():
    h = hoa[st]
    print(f"{st:<10}{n:>7}{h:>7}{(100*h/n if n else 0):>7.1f}%")

ca = tot.get("CA", 0); cah = hoa.get("CA", 0)
noncah = H - cah; noncat = T - ca
print(f"\nCA: {cah}/{ca} HOA ({100*cah/ca:.1f}%) vs non-CA: {noncah}/{noncat} ({100*noncah/noncat:.1f}%)")
print(f"CA share of ALL HOA-flagged MDU opps: {cah}/{H} = {100*cah/H:.1f}%")

print("\n=== HOA inside the populations / cleanup worklists ===")
# Signed PAL/ROE population (agreement grain, dedup) -- the dashboard set
sp_base = ("FROM Agreement__c WHERE Opportunity__r.RecordType.DeveloperName='MDU' AND Signed_Date__c!=null "
           "AND (Agreement_Type__c='PAL' OR (Agreement_Type__c='ROE' AND Opportunity__r.Signed_PAL_Date_Count__c=0))")
print(f"Signed PAL/ROE total: {c('SELECT COUNT(Id) '+sp_base)} | HOA: {c('SELECT COUNT(Id) '+sp_base+' AND Opportunity__r.HOA__c=true')}")

# Not Linked worklist (agreement grain)
nl_base = (f"FROM Agreement__c WHERE Opportunity__r.RecordType.DeveloperName='MDU' AND Opportunity__r.ST_Build_Status__c=null "
           f"AND (Signed_Date__c!=null OR Opportunity__r.StageName IN {BEYOND}) "
           f"AND (Agreement_Type__c='PAL' OR (Agreement_Type__c='ROE' AND Opportunity__r.Signed_PAL_Date_Count__c=0))")
print(f"Not Linked to SiteTracker total: {c('SELECT COUNT(Id) '+nl_base)} | HOA: {c('SELECT COUNT(Id) '+nl_base+' AND Opportunity__r.HOA__c=true')}")

# No Agreement worklist (opp grain)
na_base = f"FROM Opportunity WHERE RecordType.DeveloperName='MDU' AND StageName IN {BEYOND} AND Agreement_Count__c=0"
print(f"PAL/ROE Complete No Agreement total: {c('SELECT COUNT(Id) '+na_base)} | HOA: {c('SELECT COUNT(Id) '+na_base+' AND HOA__c=true')}")
