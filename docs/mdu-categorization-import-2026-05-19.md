# MDU Categorization Import - Summary (2026-05-19)

Source: `Signed MDU Agreement Analysis V1.xlsx`, sheet **Signed MDUs**, column **MDU Categorization**.
Target: new Opportunity field **`MDU_Categorization__c`** (restricted picklist: OnNet / OffNet / NearNet).

## What was done

1. Created `Opportunity.MDU_Categorization__c` (restricted picklist), assigned to MDU and Business record types, FLS granted to System Administrator + Standard User - Custom + B2B Vendor (mirrors the adjacent `Property_Category__c`).
2. Mapped all 316 source rows to Opportunities and wrote the categorization.
3. Added the field to the MDU Tracker as a column labeled "MDU Categorization", positioned right after "Category", across all 12 MDU views.

This field is distinct from:
- `Opportunity.Property_Category__c` (Cat 1 / Cat 2 / Cat 3, serviceability).
- `SiteTracker_Project__c.MDU_Category__c` (older 6-value scheme: Out of Footprint / On Net / In-Franchise / Near Net / National).

## Results

| Metric | Count |
|---|---|
| Source rows | 316 |
| Opportunities updated | 313 |
| Errors | 0 |
| Unmatched | 0 |

Match method:
- SiteTracker link (Monday name to ST to Opportunity): **301**
- Opportunity Name (exact): **11**
- Manual override (verified): **5**

Value distribution (unique Opps): **OnNet 151, OffNet 141, NearNet 21**.
(316 source rows resolve to 313 unique Opps: one row covers two Opps, and four Opps are each hit by two source rows. All collisions share the same value, so no conflicts. See the duplicate cleanup doc.)

## PAL reconciliation (sanity check)

Of 228 source rows that assert a signed PAL (PAL date populated), **227 (99.6%)** have a signed/Completed PAL Agreement in Salesforce, and **0** signed-PAL Opps are stuck at an early/hold/lost stage. The categorization sits on records whose PAL status genuinely lines up with SF.

Note: the "Signed MDUs" tab is not uniformly signed PALs. Only 228 of 316 rows have a PAL date; the rest are ROE-only, "Access Agreement in next 60 days," "Not Buildable PAL," or Cancelled/On Hold.

## Items that may need review

### Lower-confidence matches (verify the value landed on the right Opp)

Matched by Opportunity **Name** (no SiteTracker link). All name-for-name exact, but worth a spot check:

| Monday name | Opportunity | Value |
|---|---|---|
| Arcadia Walk | Arcadia Walk | OffNet |
| Sahara & Playa Palms Apartments | Sahara & Playa Palms Apartments | OffNet |
| Sunridge Patio Homes | Sunridge Patio Homes | OnNet |
| La Mesa Village Apartments | La Mesa Village Apartments | OnNet |
| Garden Place Apartments | Garden Place Apartments | OnNet |
| Falcon Glen Apartments | Falcon Glen Apartments | OnNet |
| Big Oaks Estates | Big Oaks Estates | OnNet |
| Pecan Acres RV Park | Pecan Acres RV Park | OnNet |
| Bradley Arms | Bradley Arms | OnNet |
| Sierra G Ranch | Sierra G Ranch | NearNet |
| The Laredo Apartments | The Laredo Apartments | OnNet |

Matched by **manual override** (auto-match failed; each verified as a single SF Opp):

| Source site | Opportunity | Value |
|---|---|---|
| Solana Beach_MDU_Santa Helena Park Condominiums | Santa Helena Park Condominiums | OnNet |
| Omaha_MDU_Farnam Flats | Omaha_MDU_Farnam Flats | OnNet |
| Killeen_SFU_Southern Hills MHP | Southern Hills Manufactured Home Community | OnNet |
| Killeen_MDU_1807 Mulford & 1810 N 8th St | 1807 Mulford Apartments_Colt RE | OnNet |
| Killeen_MDU_1807 Mulford & 1810 N 8th St | 1810 N 8th St_Colt RE | OnNet |

### OnNet to Cat 1 alignment + serviceability tool check

All 151 OnNet Opps were set to `Property_Category__c = Cat 1` (12 were not already Cat 1: 9 blank + 3 Cat 2). OnNet is treated as authoritative for now because the team categorized it by hand on a call. This is **not absolute**: a conflict between OnNet and the serviceability lookup is a signal to verify the tool.

Re-checked the 3 OnNet-vs-Cat 2 conflicts through the serviceability tool on 2026-05-19:
- **Arbors of Killeen**: tool returns Cat 1 at 150 ft. The old SF Cat 2 was stale; OnNet was correct.
- **Legend of Fort Worth** and **Enclave at Westport**: geocode failed (Census + Nominatim No_Match). Prior Cat 2 was never tool-verified.

Takeaway: the serviceability logic is sound; the **geocoder is the weak link** (fails on some addresses). Action item: improve geocoding (or supply manual coordinates) and re-run the serviceability audit so stale Cat 2 values get corrected tool-side, not just via the OnNet override.

### Data gaps surfaced during reconciliation (not categorization issues)

1. **1810 N 8th St_Colt RE** is at Marketing/Bulk In Progress (building) but has **no PAL Agreement record** in SF, though the source shows a completed access agreement. Consider creating the PAL `Agreement__c`.
2. **Birchwood Apts** has a signed PAL in SF but sits at **Prospects** stage. Its stage likely needs to advance.

## Artifacts

- Mapping script (re-runnable): `scripts/import/import_mdu_categorization_2026-05-19.py`
- Preview / rollback: `data/output/mdu_categorization_preview_*.csv`, `data/output/mdu_categorization_rollback_*.csv`
- Audit log: `data/output/audit_logs/mdu_categorization_applied_2026-05-19T15-08-45.csv`
- Tracker column script + config rollback: `scripts/fix/add_mdu_categorization_tracker_column_2026-05-19.py`, `data/output/tracker_view_config_rollback_*.json`
