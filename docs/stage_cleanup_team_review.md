# MDU Stage Cleanup — Team Review List

Compiled during stage-by-stage cleanup of MDU pipeline (post 2026-04-29 restructure).
Each item below is an Opp where the current stage placement needs the owner to confirm or correct.

---

## Justin Barry

### Engaged — verify status accurate

| Opp | SF Id | Last documented contact | Question |
|---|---|---|---|
| 1342 Eolus Ave | 006WR00000yur0lYAA | 1/27 voicemail to Stephanie (homeowner). Three prior calls in late 2025 / early 2026 with no callback. Note: "10/10 pending contact from Mason." | Is this still Engaged? If yes, set `Next_Action__c`. If unreachable, move to Prospects (cold) or Closed Lost / No Contact Info. |
| 978 Hygeia Ave | 006WR00000ywTYXYA2 | 3/11 followed up with Simon. 2/11 sent Easement Agreement for private road signatures. 1/27/26 completed easement with exhibit. | Is Simon still moving on this? If yes, set `Next_Action__c` with target. If stalled, drop stage accordingly. |
| Bridgeport_MDU_Federal Housing Administration | 006WR00000xuFKAYA2 | Moved into Engaged 2026-05-01. No `Next_Action__c` set. | Set `Next_Action__c` describing where this stands. |

---

## Brett Spivey

### Contract Negotiations — verify status accurate

| Opp | SF Id | Agreement state | Question |
|---|---|---|---|
| Biltmore Terrace Condominiums | 006WR00000wj8KSYAY | PAL Paused (manual SF entry, no IronClad) | No Next_Action, no Projected, no IronClad. Still in Contract Negotiations? Set Next_Action / Projected, or move to On Hold. |
| Diamond Fork Apartments | 006WR00000wkAW3YAM | PAL Paused (manual) | Same — still in negotiations or On Hold? |

---

## Jeff Chao

### Contract Negotiations — verify status accurate

| Opp | SF Id | Agreement state | Question |
|---|---|---|---|
| The Upland | 006WR00000wjnlUYAQ | PAL Paused + EMA Review (manual) | No Next_Action, no Projected, no IronClad. Still alive or On Hold? |
| University Apartments | 006WR00000wjnmKYAQ | PAL Paused + EMA `Completed` signed 2025-01-21 (manual, no IronClad backing) | EMA shows Completed/signed 1/21/25 — if real, this is PAL/ROE Complete, not Contract Negotiations. Confirm: was the EMA actually signed? |

---

## Tanya Friese

### Contract Negotiations — verify status accurate

| Opp | SF Id | Agreement state | Question |
|---|---|---|---|
| Taschner Apartments | 006WR00000wk9SGYAY | PAL Review (manual) | No Next_Action, no Projected, no IronClad. Still active or On Hold? |

---

## Melissa Baker

### Contract Negotiations — verify status accurate

| Opp | SF Id | Agreement state | Question |
|---|---|---|---|
| Converge Justin | 006WR000011cV9lYAE | NONE — empty record | Zero data: no agreements, no notes, no Next_Action, no Projected. Was this created in error or as a placeholder? Delete or define purpose. |

---

## Chuck McNeely (inactive — needs reassignment)

These 4 Opps were owned by Chuck McNeely, who is no longer active. They need an owner reassignment AND stage verification.

| Opp | SF Id | Agreement state | Question |
|---|---|---|---|
| Chalet Apartments | 006WR00000wk9SjYAI | PAL Review + ROE Cancelled (manual) | Reassign owner. Verify Contract Negotiations is correct. |
| Kirshenbaum Apartments | 006WR00000wk9S0YAI | PAL Review (manual) | Reassign owner. Verify stage. |
| Spindrift Del Mar HOA | 006WR00000wk9SwYAI | PAL Paused (manual) | Reassign owner. Likely On Hold given Paused agreement + zero recent signals. |
| Temple Square Apts | 006WR00000wk9S5YAI | PAL+EMA Paused (manual) | Reassign owner. Likely On Hold. |

---

## PAL/ROE Complete — review items

### Justin Barry — verify Bulk signed and create Agreement records

The text scan found 4 Opps where Jeff Chao (Oct 2024) noted "Ting Bulk confirmed by SFU Team" but no Bulk Agreement__c record exists. Need Justin to verify and either create the Bulk Agreement record (then auto-bumps to EMA/Bulk Complete) or confirm not active.

| Opp | SF Id | Note evidence |
|---|---|---|
| Solana Beach and Tennis Club | 006WR00000wk9YTYAY | "Confirmed Ting bulk signed at this property per Dave Putnam" (10/4/24) |
| Del Mar Shores Terrace | 006WR00000wkCllYAE | "Ting BULK Confirmed by SFU Team" (10/8/24) |
| Las Brisas | 006WR00000wkClkYAE | "Ting Bulk confirmed by SFU Team" (10/8/24) |
| Del Mar Beach Club | 006WR00000wkClNYAU | "Ting BULK Confirmed by SFU Team" (10/8/24) |

### Tanya Friese — confirm EMA pursuit status

| Opp | SF Id | Note | Question |
|---|---|---|---|
| 1507 N 8th Apartments_Colt RE | 006WR00000wkEbPYAU | "PAL signed, waitin on PAL addendum and verbal on EMA" (4/24/26) | Is the EMA active enough to bump to EMA/Bulk In Progress, or stay in PAL/ROE Complete? |
| Killeen_MDU_Bradley Arms | 006WR00000xuzoQYAQ | "verbal on EMA" (same weekly tracker note) | Same — confirm EMA status |

### Justin Barry — Agreement Status mismatch

| Opp | SF Id | Issue |
|---|---|---|
| Green Valley Mobile Estates Encinitas | 006WR00000wkA6iYAE | ROE AGR-1417 Status=`Sign` but Next_Action says "ROE signed - awaiting build orders". Update Status to `Completed` + populate Signed_Date |

### Brett Spivey — reconcile Bulk status

| Opp | SF Id | Issue |
|---|---|---|
| Capri on Camelback | 006WR00000wkEc3YAE | Bulk AGR-1040 Status=`Completed` but Signed_Date=None and no IronClad. Next_Action says "Brett to contact owner re bulk requirement". Either Bulk really is Completed (fill Signed_Date + create IronClad link) or the Status is wrong |

### Possible duplicates — verify and consolidate

| Pair | Notes |
|---|---|
| ~~San Ito (006WR00000ywTezYAE) ↔ Ito San (006WR0000112vHHYAY)~~ | Closed by Koa 2026-05-01 |
| Converge Justin (Brett, 006WR00000yvY5dYAE) ↔ Converge Justin (Melissa, 006WR000011cV9lYAE) | Both empty records, same name. Different stages (PAL/ROE Complete vs Contract Negotiations). Likely the same Opp made twice — pick one to keep, close the other |
| Killeen_MDU_Bradley Arms (Tanya, 006WR00000xuzoQYAQ) ↔ Bradley Arms_Colt RE (Melissa, 006WR00000wkCjuYAE) | Different naming sources (PowerBI/CHR vs Colt RE) for what may be the same Killeen TX property. Tanya/Melissa to confirm |

### Chuck McNeely (inactive)

| Opp | SF Id | Issue |
|---|---|---|
| Lexington Place (Monterey) | 006WR00000wkEcKYAU | No Agreement, no Next_Action, no Projected, owner inactive. Reassign + verify stage |

### Missing PAL/ROE Agreement record (data gap, stage OK per CX-tracking rule)

These belong in PAL/ROE Complete (Melissa/Tanya tracking CX post-PAL even without EMA/Bulk pursuit) but they're missing the PAL/ROE Agreement__c record itself. Decision: backfill PAL Agreement records, or accept the gap?

| Opp | Owner |
|---|---|
| Decatur_MDU_Smallwood Trailer Park | Melissa Baker |
| Omaha_MDU_4612 Redman Ave | Melissa Baker |
| Omaha_MDU_4760 LAFAYETTE AVE | Melissa Baker |
| Omaha_MDU_5004 Davenport St | Melissa Baker |
| Omaha_MDU_9208 Ohio St | Melissa Baker |
| Omaha_MDU_Benson Crest Apartments 2 | Melissa Baker |
| Omaha_MDU_Farnam Flats | Melissa Baker |
| Killeen_MDU_Bradley Arms | Tanya Friese (also possible dupe with Colt RE — see above) |
| Paul Mark Apts | Tanya Friese |
| 512-514 Via De La Valle | Justin Barry |

---

## EMA/Bulk In Progress — review items

### Brett Spivey — confirm 31 SoCal Opps actually in EMA/Bulk negotiation

All 31 share the same shape: PAL `Completed` (signed 2023-11-01 — likely a bulk-import date), EMA + Bulk both `Review` status with **zero IronClad linkage** (manual SF entries), SiteTracker project at "1. Project - PAL/ROE Signed" (no construction yet), no `Next_Action`, no `Projected_Close_Date`. Pattern looks like a SoCal placeholder import where EMA/Bulk records were created to track future pursuit but nothing is actively being negotiated. Per the methodology, "PAL/ROE Complete" is the correct stage when no EMA/Bulk is actively being pursued.

**Action required per row:** For each Opp, confirm one of:
- **(A) IN NEGOTIATION** — keep at EMA/Bulk In Progress, set `Next_Action__c` + `Projected_Close_Date__c`
- **(B) NOT NEGOTIATING** — drop to PAL/ROE Complete; cancel/remove placeholder EMA + Bulk Agreement records
- **(C) OTHER** — explain (e.g. ready to move to EMA/Bulk Complete because signed)

| Opp | SF Id | EMA AGR | Bulk AGR | ST Project | Action |
|---|---|---|---|---|---|
| Baldwin Manor | 006WR00000wkEaRYAU | AGR-0793 Review | AGR-0794 Review | P-003350 | A / B / C? |
| Bali Apartments | 006WR00000wkEaTYAU | AGR-0799 Review | AGR-0800 Review | P-003352 | A / B / C? |
| Brody Terrace (Riverside) | 006WR00000wkEahYAE | AGR-0841 Review | AGR-0842 Review | P-003331 | A / B / C? |
| Brookside Terrace Apartments | 006WR00000wkEbLYAU | AGR-0935 Review | AGR-0936 Review | P-003349 | A / B / C? |
| Casa Linda | 006WR00000wkEaXYAU | AGR-0811 Review | AGR-0812 Review | P-003347 | A / B / C? |
| Chatsworth Plaza | 006WR00000wkEaVYAU | AGR-0805 Review | AGR-0806 Review | P-003345 | A / B / C? |
| Coliseum Apartments | 006WR00000wkEaZYAU | AGR-0817 Review | AGR-0818 Review | P-003343 | A / B / C? |
| Colonial Manor Apartments | 006WR00000wkEaaYAE | AGR-0820 Review | AGR-0821 Review | P-003342 | A / B / C? |
| Corbett Avenue Apartments | 006WR00000wkEaUYAU | AGR-0802 Review | AGR-0803 Review | P-003383 | A / B / C? |
| First Casa De Marina | 006WR00000wkEbIYAU | AGR-0926 Review | AGR-0927 Review | P-003281 | A / B / C? |
| Jaclyn Terrace | 006WR00000wkEagYAE | AGR-0838 Review | AGR-0839 Review | P-003338 | A / B / C? |
| John Manor | 006WR00000wkEaWYAU | AGR-0808 Review | AGR-0809 Review | P-003384 | A / B / C? |
| Kling Trio Apartments | 006WR00000wkEafYAE | AGR-0835 Review | AGR-0836 Review | P-003336 | A / B / C? |
| Krystal Terrace | 006WR00000wkEadYAE | AGR-0829 Review | AGR-0830 Review | P-003387 | A / B / C? |
| Lombardi Apartments | 006WR00000wkEbJYAU | AGR-0929 Review | AGR-0930 Review | P-003335 | A / B / C? |
| Parkview Terrace | 006WR00000wkEaiYAE | AGR-0844 Review | AGR-0845 Review | P-003334 | A / B / C? |
| Parkway Terrace | 006WR00000wkEaeYAE | AGR-0832 Review | AGR-0833 Review | P-003388 | A / B / C? |
| Parthenia Terrace | 006WR00000wkEbNYAU | AGR-0941 Review | AGR-0942 Review | P-003332 | A / B / C? |
| Riverside Villa Apartments | 006WR00000wkEakYAE | AGR-0850 Review | AGR-0851 Review | P-003330 | A / B / C? |
| Roxanne Apartments | 006WR00000wkEajYAE | AGR-0847 Review | AGR-0848 Review | P-003353 | A / B / C? |
| San Vicente Apartments | 006WR00000wkEabYAE | AGR-0823 Review | AGR-0824 Review | P-003385 | A / B / C? |
| St. Andrews Manor | 006WR00000wkEacYAE | AGR-0826 Review | AGR-0827 Review | P-003386 | A / B / C? |
| The Banyans | 006WR00000wkEalYAE | AGR-0853 Review | AGR-0854 Review | P-003351 | A / B / C? |
| The Meadows at Westlake Village | 006WR00000wkEbKYAU | AGR-0932 Review | AGR-0933 Review | P-003348 | A / B / C? |
| The Palms | 006WR00000wkEapYAE | AGR-0865 Review | AGR-0866 Review | P-003346 | A / B / C? |
| Topanga Apartments | 006WR00000wkEamYAE | AGR-0856 Review | AGR-0857 Review | P-003344 | A / B / C? |
| Topanga Terrace | 006WR00000wkEanYAE | AGR-0859 Review | AGR-0860 Review | P-003341 | A / B / C? |
| Vista Apartments | 006WR00000wkEaoYAE | AGR-0862 Review | AGR-0863 Review | P-003340 | A / B / C? |
| White Oak Terrace | 006WR00000wkEaSYAU | AGR-0796 Review | AGR-0797 Review | P-003337 | A / B / C? |
| Windsor Manor | 006WR00000wkEaYYAU | AGR-0814 Review | AGR-0815 Review | P-003381 | A / B / C? |
| Woodland Trio The Oaks | 006WR00000wkEaQYAU | AGR-0790 Review | AGR-0791 Review | P-003339 | A / B / C? |

---

## EMA/Bulk Complete — review items

### Chuck McNeely (inactive) — 3 Opps with no signed EMA/Bulk

All 3 share the same shape: PAL `Completed` + IronClad-linked, PAL Addendum `Completed`, EMA in `Archive` status (never signed), SiteTracker project at "4. Project - Completed" (build is done). Per the methodology, EMA/Bulk Complete requires a signed/Completed EMA or Bulk Agreement. These have only PAL + PAL Addendum signed — they belong in **PAL/ROE Complete**.

**Action required per row:** Reassign owner from Chuck. Confirm one of:
- **(A) MOVE TO PAL/ROE COMPLETE** — EMA was never actually signed (Archive status correct)
- **(B) STAY IN EMA/BULK COMPLETE** — EMA/Bulk was signed but record Status is wrong (fix Status + Signed_Date)

| Opp | SF Id | Agreement state | ST Build | Action |
|---|---|---|---|---|
| Arbors of Killeen | 006WR00000wkEcmYAE | PAL AGR-1165 Completed (IC-1084), EMA AGR-1166 Archive, PAL Addendum AGR-1167 Completed | P-004231 (Project Completed) | Reassign + A / B? |
| The Bluffs of Brookside | 006WR00000wk1ElYAI | PAL AGR-1298 Completed (IC-1499), EMA AGR-1299 Archive, PAL Addendum AGR-1300 Completed | P-006292 (Project Completed) | Reassign + A / B? |
| The Renaissance at Stoney Creek | 006WR00000wk1EjYAI | PAL AGR-1291 Completed (IC-1504), EMA AGR-1292 Archive, PAL Addendum AGR-1293 Completed | P-006296 (Project Completed) | Reassign + A / B? |

---

## On Hold — low-priority bucket

**On Hold is the lowest-priority cleanup target.** 282 records, all have `Hold_Reason__c` populated (validation rule holding), 277 use generic `'Other'`. We're leaving the dormant set alone — they can be revisited when a richer Hold_Reason picklist exists.

**Only 3 On Hold records look like they're actively being worked** (have signal beyond status documentation):

| Opp | SF Id | Owner | Signal | Action |
|---|---|---|---|---|
| The Traditions Apartments | (look up) | Brett Spivey | Next_Action: "Niraj sending legal note to Caitlin re cancellation comm to..." | Cancellation in progress — should this close out as Closed Lost rather than sit On Hold? |
| Horizon Heights | (look up) | Melissa Baker | Next_Action: "Need Data and approval to walk [Placeholder forecast — updat..." + Projected_Close 2026-07-27 | Active work + forecasted close date. Why is this On Hold rather than Engaged or Prospecting? |
| TEST PROPERTY 2 | (look up) | Taylor Mauney | Projected_Close 2026-07-31, name = "TEST PROPERTY 2" | Delete — test record in production pipeline. |

The other 3 records with populated Next_Action (Fowler's RV Park, Pecan Acres RV Park, Monte Mira HOA) use Next_Action as status documentation ("Stalled — owner out of country", "Build not approved (budget)") — On Hold placement is consistent with the documented state, leave alone.

### Systemic items (later, not blocking team review)

- **`Hold_Reason__c` picklist needs richer values.** 277 of 282 use `'Other'`. Suggest: `Build Capacity`, `Owner Unresponsive`, `Negotiation Stalled`, `Property Sold`, `Vendor Conflict`, `Construction Blocked`. Currently only `Build Not Approved` (3), `Budget / Timing` (1), `Ownership Change` (1) get used.
- **Chuck McNeely owns 64 On Hold Opps.** Bulk owner reassignment needed (admin task — defer until reassignment plan exists). Texas-heavy names suggest Marty Samuels as likely target.
- **Owner concentration:** Jeff Chao 148 (52%), Chuck 64, Brett 35, Marty 17, Bill 7, Jeff Wickersham 5, Melissa 3, Justin 2, Taylor 1.

---

## Stage moves applied (audit trail)

| Date | Opp | SF Id | From | To | Reason |
|---|---|---|---|---|---|
| 2026-05-01 | Capri on Camelback | 006WR00000wkEc3YAE | Contract Negotiations | PAL/ROE Complete | All 3 Agreements completed; AGR-1039 IronClad-confirmed (IC-153, stage=completed, status=active) |
| 2026-05-01 | San Ito | 006WR00000ywTezYAE | PAL/ROE Complete | (closed by Koa as dup of Ito San) | CA MDU Merge dedup orphan |

---

## Systemic flags (not blocking; for later)

- **76% of Agreement__c records are not IronClad-linked** (1,143 of 1,514 org-wide). Status__c on those is whatever the team typed, not synced from IronClad. Worth a follow-up sweep with the bulk linker + a convention call on whether pre-IronClad placeholders should live in Agreement records or only in Sales_Status / Next_Action.

---

*(continues — PAL/ROE Complete, EMA/Bulk In Progress, EMA/Bulk Complete, On Hold)*
