# Signed MDUs - Duplicate Record Cleanup List (2026-05-19)

Surfaced while importing MDU Categorization from `Signed MDU Agreement Analysis V1.xlsx` (sheet Signed MDUs).

**Headline: there are no exact duplicates.** All 316 rows have unique SiteTracker Project IDs. The items below are cases where two distinct SiteTracker projects share an address and/or name, in some cases collapsing onto a single Salesforce Opportunity. None affected the categorization write (every group shares the same value). They are listed for SiteTracker / data-owner review.

Owner to confirm: SiteTracker / source-file maintainer (Craig / Taylor as appropriate).

---

## A. Likely SiteTracker mis-link (two different properties on one Opp)

Two distinct properties (different name, address, unit count) both link to the single Opportunity **Indian Hills Terrace**:

| Project ID | Site | Units | Address |
|---|---|---|---|
| P-005578 | Omaha_MDU_Indian Hills Terrace | 30 | 102 S 85th St, Omaha NE 68114 |
| P-006838 | Omaha_MDU_Indian Hills Village Court | 12 | 8509 Indian Hills Dr, Omaha NE 68114 |

**Recommended action:** Indian Hills Village Court (P-006838) should have its own Opportunity. Re-point its SiteTracker link off the Indian Hills Terrace Opp.

---

## B. Real duplicate suspects (same address + same name + `-2` suffix)

Same street address, identical Monday.com name, second record carries a `-2` suffix, unit counts differ. Either two real buildings/sections, or a SiteTracker re-entry.

### B1. Orchard Park Apartments - 7805 Harney St, Omaha NE 68114
| Project ID | Site | Units |
|---|---|---|
| P-006834 | Omaha_MDU_Orchard Park Apartments | 19 |
| P-006874 | Omaha_MDU_Orchard Park Apartments**-2** | 25 |

### B2. Indian Hills Village Apartments - 107 S 87th St, Omaha NE 68114
| Project ID | Site | Units |
|---|---|---|
| P-006837 | Omaha_MDU_Indian Hills Village Apartments | 21 |
| P-006872 | Omaha_MDU_Indian Hills Village Apartments**-2** | 15 |

**Recommended action:** Confirm whether each `-2` is a real second building or a duplicate entry.
- If duplicate: retire the `-2` SiteTracker project and clean its Opportunity link.
- If a real second building: rename it (for example "Bldg 2") and give it its own Opportunity rather than bundling both onto one.

Both pairs currently collapse onto a single Opportunity each.

---

## C. Adjacent buildings bundled onto one Opp (low priority)

Two adjacent addresses, same unit count, both linked to the single Opportunity **Omaha_MDU_4760 LAFAYETTE AVE**. The Full Address cell on the 4750 row is a copy of 4760 (data entry slip).

| Project ID | Site | Units | Address (as entered) |
|---|---|---|---|
| P-006494 | Omaha_MDU_4760 LAFAYETTE AVE | 23 | 4760 Lafayette Ave, Omaha NE 68132 |
| P-006876 | Omaha_MDU_4750 LAFAYETTE AVE | 23 | 4760 Lafayette Ave, Omaha NE 68132 (should be 4750) |

**Recommended action:** Fix the 4750 row's address. Decide whether 4750 and 4760 should be one Opportunity (bundle) or two.

---

## D. Not a duplicate (no action, documented for completeness)

Two genuinely different properties at a shared campus address. They mapped to separate Opportunities, so no collision.

| Project ID | Site | Units | Address |
|---|---|---|---|
| P-003282 | Los Angeles_MDU_Gloria homes | 423 | 4928 W MLK Jr Blvd, Los Angeles CA 90016 |
| P-003352 | Los Angeles_MDU_Bali Apartments | 74 | 4928 W MLK Jr Blvd, Los Angeles CA 90016 |
