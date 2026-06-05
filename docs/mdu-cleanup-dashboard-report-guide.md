# MDU Cleanup Dashboard: report guide

Plain-English explanation of every tile on the **MDU Cleanup Dashboard** (folder: MDU Sales Dashboards): what each report looks for and exactly which filters make a record show up in the count. Live counts are as of 2026-06-01.

Two things that apply to most tiles:

- **Record Type:** every tile except the new one is scoped to **MDU** Opportunities only. The new "Signed PAL/ROE: Stage Not Advanced" tile includes **MDU and SFU**.
- **Grain:** most tiles count **Opportunities**. Two tiles count **Agreement rows** instead ("Not Linked to SiteTracker" and "Signed PAL/ROE: Stage Not Advanced"), so one Opp with two qualifying agreements counts twice. The tile's metric label says which.

A "parameter" below = one filter line on the report. A record only appears if it passes **all** of them (the boolean logic is noted where it is not a plain AND).

---

## Left column

### 1. Need IronClad ID, Signed  (`Cleanup_Opps_Need_IC_ID_Signed`) - 330
Opps holding a signed/completed agreement that has no IronClad ID recorded. A source-of-truth gap: the paper is done but it is not tied back to IronClad.
- **Record Type = MDU.**
- **Agreements Signed Missing IC > 0** (`Agreements_Signed_Missing_IC__c`): a roll-up that counts this Opp's agreements in Sign or Completed status with a blank IronClad ID. Any count above zero lands the Opp here.

### 2. Under Contract: No PAL  (`Cleanup_Under_Contract_No_PAL`) - 103
Opps that reached PAL/ROE Complete but have no **signed PAL** on file.
- **Record Type = MDU.**
- **Stage = PAL/ROE Complete.**
- **Signed PAL Count = 0** (`Signed_PAL_Count__c`).
- **Caveat for Taylor:** this counts PALs only. A property secured by a **signed ROE** (no PAL) still shows here even though it is legitimately complete. Expect ROE-only properties in this list; they are not necessarily errors.

### 3. No RE Assigned (active stages)  (`Cleanup_Opps_No_RE_Assigned`) - 270
Active pursuits with no real-estate owner assigned.
- **Record Type = MDU.**
- **RE Assigned is blank** (`RE_Assigned__c`).
- **Stage is one of:** Engaged, Proposal Sent, Contract Negotiations, PAL/ROE Complete.

---

## Middle column

### 4. Need IC ID, Out for Sign  (`Cleanup_Opps_Need_IC_ID_OutForSign`) - 1
Agreements currently out for signature that have no IronClad ID yet.
- **Record Type = MDU.**
- **Agreements Sign Missing IC > 0** (`Agreements_Sign_Missing_IC__c`): roll-up of agreements at **Sign** status with a blank IronClad ID.

### 5. No Property Location  (`Cleanup_Opps_No_Property_Location`) - 338
Active Opps not linked to a Property Location record.
- **Record Type = MDU.**
- **Property Location is blank** (`Property_Location__c`).
- **Stage is one of:** Engaged, Proposal Sent, Contract Negotiations, PAL/ROE Complete, **EMA/Bulk In Progress**.
- **Caveat:** "EMA/Bulk In Progress" was **deactivated** in the 2026-04-29 stage restructure (renamed to Marketing/Bulk In Progress). That value matches nothing today, so any Opp now at Marketing/Bulk In Progress is **not** counted here. The number is low by however many sit at that stage. Flagged to fix.

### 6. No Projected Close Date  (`Cleanup_Opps_No_Projected_Close`) - 309
Active pursuits with no forecasted close date.
- **Record Type = MDU.**
- **Projected Close Date is blank** (`Projected_Close_Date__c`, the custom forecast field, not standard Close Date).
- **Stage is one of:** Engaged, Proposal Sent, Contract Negotiations, PAL/ROE Complete.

---

## Right column

### 7. Stale Active Opps (60+ days)  (`Cleanup_Stale_Active_Opps`) - 338
Active Opps that have not been touched in two months.
- **Record Type = MDU.**
- **Stage is one of:** Engaged, Proposal Sent, Contract Negotiations, PAL/ROE Complete, **EMA/Bulk In Progress**.
- **Last Modified on or before LAST_N_DAYS:60** (no edit in the last 60 days).
- **Caveat:** same deactivated "EMA/Bulk In Progress" stage value as tile 5. Marketing/Bulk In Progress Opps are not counted. Flagged to fix.

### 8. Stale Marketing/Bulk on wrong stage  (`Cleanup_Stale_EMA_Bulk_Opps`) - 90
Opps that carry an active EMA/Bulk agreement but sit at a stage that does not match.
- **Record Type = MDU.**
- **Stage is NOT one of:** PAL/ROE Complete, Marketing/Bulk In Progress, Marketing/Bulk Complete. (Uses the current stage names.)
- **Active EMA/Bulk Count > 0** (`Active_EMA_Bulk_Count__c`).

### 9. Not Linked to SiteTracker  (`PALROE_Not_Linked_SiteTracker`) - 72  *(counts agreement rows)*
Signed PAL/ROE (or an Opp already at PAL/ROE Complete or beyond) with no SiteTracker project linked.
- **Record Type = MDU.**
- **ST Build Status is blank** (`ST_Build_Status__c`): the surfaced SiteTracker status is empty, i.e. nothing linked. This is the reason it is on the list.
- **Signed/complete condition (either side):** the agreement has a **Signed Date** and a status of **Completed or Cancelled**, OR the Opp **Stage is** PAL/ROE Complete / Marketing/Bulk In Progress / Marketing/Bulk Complete.
- **Type de-dup:** the agreement is a **PAL**, OR it is a **ROE** on a property with no signed PAL (`Signed_PAL_Date_Count__c = 0`). This keeps a property that has both a PAL and an ROE from being counted twice; it counts once as the PAL.
- Full logic: `1 AND 2 AND ((3 AND 8) OR 4) AND (5 OR (6 AND 7))`.

### 10. PAL/ROE Complete: No Agreement  (`PALROE_Complete_No_Agreement`) - 10
Opps at PAL/ROE Complete or beyond with **no agreement record at all**.
- **Record Type = MDU.**
- **Stage is one of:** PAL/ROE Complete, Marketing/Bulk In Progress, Marketing/Bulk Complete.
- **Agreement Count = 0** (`Agreement_Count__c`): zero child agreements. Either the agreement was never created in SF, or the stage was set by hand.

### 11. Signed PAL/ROE: Stage Not Advanced  (`PALROE_Signed_Stage_Lagging`) - 68  *(NEW, added 2026-06-01, counts agreement rows)*
The **reverse** check the dashboard was missing: the paperwork is signed but the stage never caught up. Every other tile asks "advanced stage, is the paper present?" This one asks "paper present, did the stage advance?"
- **Record Type = MDU or SFU.**
- **Agreement Type = PAL or ROE.**
- **Agreement Status = Completed.**
- **Stage is one of:** Prospects, Prospecting, Engaged, Proposal Sent, Contract Negotiations, On Hold, Closed Lost (i.e. anything *before* PAL/ROE Complete, plus the parked/lost stages).
- **Fix:** advance the Opp to PAL/ROE Complete. Today 62 of the 68 are owned by Chuck McNeely (inactive user), so these also need reassignment. 3 are Closed Lost with a signed agreement, worth confirming the loss is real.
- Grouped by Owner then Stage so the inactive-owner block is obvious.

---

## Known fixes queued
- Tiles **5** and **7** filter on the deactivated stage value **"EMA/Bulk In Progress"** and therefore miss any Opp now at **Marketing/Bulk In Progress**. Update both to the current stage name.
- Tile **2** ("No PAL") includes ROE-secured properties by design of the `Signed_PAL_Count__c` field. If Taylor wants ROE-only properties excluded, switch it to a PAL-or-ROE count.
