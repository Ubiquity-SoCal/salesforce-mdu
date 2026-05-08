# Salesforce Opportunity Name Cleanup Log

> Hand-cleaned Opportunity.Name values post-migration. Any future sync that treats
> Monday.com (or another external source) as source-of-truth for Opp.Name **must
> not overwrite these records** unless the cleaned name is also written back upstream.

## Phase 1 — 2026-04-20 (complete, 21 records)

**Fixed:** collapsed runs of whitespace, unwrapped 4 raw Monday.com export strings
of the form `{"text6__1"=>"<value>"}`.

- Audit script: `scripts/analysis/audit_opp_names.py`
- Cleanup scripts:
  - `scripts/cleanup/phase1_clean_opp_names.py` — the 7 Opps that weren't blocked
  - `scripts/cleanup/phase1_fill_status_and_rename.py` — the 14 Opps blocked by the
    `Require_Sales_Status_Prospecting` validation rule; filled `Sales_Status__c` from
    notes at the same time as the rename
- Rollback CSVs (Id, old_name, new_name [, old_status, new_status]):
  - `scripts/cleanup/rollback/phase1_rollback_20260420_082136.csv` (7 rows)
  - `scripts/cleanup/rollback/phase1b_rollback_20260420_082541.csv` (14 rows)

### Sales_Status__c set during Phase 1 (from notes)

| Opp Id | Status set | Rationale |
|---|---|---|
| 006WR00000wjdkrYAA | Contact Pending | no notes |
| 006WR00000wkA7CYAU | Reached Out - Pending Response | talked w/ Nick Eddy (Lumen) |
| 006WR00000wkA7EYAU | Reached Out - Pending Response | talked w/ Nick Eddy (Lumen) |
| 006WR00000wkA7JYAU | Reached Out - Pending Response | emailed Highmark |
| 006WR00000wkA7KYAU | Reached Out - Pending Response | emailed Highmark |
| 006WR00000wkA7NYAU | Reached Out - Pending Response | emailed Highmark |
| 006WR00000wkACYYA2 | Contact Pending | no notes |
| 006WR00000wkAk1YAE | Reached Out - Pending Response | emailed Irene, dropped proposal |
| 006WR00000wkDstYAE | Reached Out - Pending Response | Draft PAL sent 8/11/2025 |
| 006WR00000wkDszYAE | Reached Out - Pending Response | "not a fit" (likely Closed Lost) |
| 006WR00000wkDtGYAU | Reached Out - Pending Response | "Moving status to Low Return" |
| 006WR00000wkDtMYAU | Contact Pending | internal research only |
| 006WR00000wkDtNYAU | Contact Pending | "16 units — too small" (likely Closed Lost) |
| 006WR00000wkDtOYAU | Contact Pending | "NO MDU at this location" (likely Closed Lost) |

Several of the above (Arbor, Harker Heights, Cherry Tree, 58th Plaza, Fort Hood)
are probably more accurately `Closed Lost` at the Stage level — deferred to a
separate stage-review pass.

## Phase 1c — strip decorative unicode symbols (complete, 15 records)

Stripped ⚫ (U+26AB MEDIUM BLACK CIRCLE) suffix from 15 Opportunity names.
Preserves letters-with-diacritics (`Villas de la Montaña` kept intact).
Script: `scripts/cleanup/phase1c_strip_symbols.py` (strips unicode categories
So, Sk, Cf, Cc).

For 5 records blocked by `Require_Sales_Status_Prospecting`, set
`Sales_Status__c = Reached Out - Pending Response` based on note review (all had
PALs sent, emails with named contacts, or active call logs): Camelot Village,
Keystone Park Apartments, Shadow Ridge Apartments, Copper Ridge HOA, Station 121
at Town Center.

Rollback: `scripts/cleanup/rollback/phase1c_rollback_20260420_083850.csv`

## Phase 2 — ALL CAPS / trailing punctuation / proper case (complete, 62 records)

Script: `scripts/cleanup/phase2_titlecase.py` (and one-off `phase2b` for 2 Closed
Lost records).

Acronym whitelist includes: HOA, MDU, SFU, SMB, LLC, Inc, MHP, MHC, RV, SLA, ISP,
MSO, ROE, PAL, EMA, VoIP, SAQ, BL, LTE, FDH, ONT, OLT, GPON, all US state codes,
directionals, roman numerals, AJ, FKA, AKA, RE, CP, LTD, CO. Short unit tokens
(1G, 300M, SA01, FDH08, PA02) preserved as uppercase. Single-letter tokens mid-name
(`- A`, `Phase I`) kept uppercase as designators.

Separated synthetic migration-key names (matching `_SA\d+_`, `_FDH\d+_`, `_PA\d+_`,
`_MDU_`, `_SFU_`) into `scripts/cleanup/phase2_migration_keys_for_review.csv`.
Koa reviewed and approved title-casing them (rather than replacing with real
property names) — applied 2026-04-20 via `phase2c_apply_migration_keys.py`. 11/11
applied. Rollback: `scripts/cleanup/rollback/phase2c_migkeys_rollback_20260420_091234.csv`.

**Status defaults during apply:**
- 22 Opps in `Prospecting` with blank `Sales_Status__c` were populated using a note
  keyword heuristic: notes containing outreach tokens (pal sent, emailed, lvm,
  called, met with, proposal sent, followed up, etc.) → `Reached Out - Pending
  Response`; otherwise `Contact Pending`.
- 2 Opps in `Closed Lost` with blank `Loss_Reason__c` were set to `Other`
  (Greater Omaha Refrig, Outsource One) — can be refined later.
- 1 Opp skipped: `TEST PROPERTY` (006WR000010BbmwYAC). Created 2026-04-15 by
  Taylor Mauney, Closed Lost with blank Loss_Reason and blank Sales_Status, no
  Monday_Item_ID__c, no notes, but **has child Agreement AGR-1415 (Completed)**.
  Left as-is pending a check with Taylor — do not auto-delete, the Agreement
  relationship makes this look like deliberate test state.

**Known residual issue:** `MCQUEEN LANDING HOA` became `Mcqueen Landing HOA` —
proper names with internal capitals (McQueen, O'Brien, DeSoto) are out of scope
for automated rules. Fix manually if wanted.

Rollback CSVs:
- `scripts/cleanup/rollback/phase2_rollback_20260420_090717.csv` (60 rows)
- `scripts/cleanup/rollback/phase2b_closedlost_rollback_20260420_090814.csv` (2 rows)

## Status field backfill + state normalization — 2026-04-20

Driven by state-field normalization (Koa wanted `Property_State__c` consistent) —
hit existing data gaps that were blocking any update on those records.

**Backfill of required validation fields** (`scripts/cleanup/backfill_required_statuses.py`):
- 2,286 Prospecting Opps with blank `Sales_Status__c` → populated via note-keyword
  heuristic. 1,513 → `Contact Pending`, 773 → `Reached Out - Pending Response`.
  Same outreach keyword list used in Phase 2. Future sales-team edits will refine.
- 40 Closed Lost Opps with blank `Loss_Reason__c` → `Other`.
- 18 On Hold Opps with blank `Hold_Reason__c` → `Other`.
- Rollback: `scripts/cleanup/rollback/backfill_statuses_rollback_20260420_093022.csv`.

**State normalization** (`scripts/cleanup/normalize_states.py`):
- `Opportunity.Property_State__c`: 3,462 full-name → 2-letter (Texas→TX, Arizona→AZ,
  etc.) + 1 case fix (`Ca`→`CA`). Final distribution: 71 blank, rest are 2-letter
  codes matching the Property_Location__c picklist.
- `Account.BillingState`: 1 expansion (Texas→TX). `Ontario` left alone (Canadian).
- Rollbacks:
  - `scripts/cleanup/rollback/normalize_states_rollback_20260420_092312.csv` (1,213 rows, first run)
  - `scripts/cleanup/rollback/normalize_states_rollback_20260420_093118.csv` (2,250 rows, second run)

## Property_State__c blank backfill via inference — 2026-04-20

Script: `scripts/cleanup/infer_property_state.py`.

Signal priority: Account.BillingState → SiteTracker_Project__c.State__c →
regex state abbreviation in name (with context guards for "NE"=Northeast
false positives) → full state name in name → known-city lookup.

Results: 42/71 filled. Sources: 32 from Account, 7 from name-abbr (SMB ROE
Project MESA AZ entries + Mineral Wells TX), 2 from city (Omaha Steaks → NE,
Shell of Bridgeport → TX), 1 from name-full (ABC Seamless of Nebraska).

29 remain blank — all generic business names with no usable signal
(Fish District, Foodies, Go Dogs, etc.). Left for manual review.

Rollback: `scripts/cleanup/rollback/state_infer_rollback_20260420_093544.csv`.

## Link backfill — 2026-04-20

**SiteTracker → Opportunity linking:**
- Automated linker run (`Automation/sitetracker/link_sitetracker_opportunities.py`):
  37 ST projects auto-matched against Opp.Name. Started at 396 linked / 68
  unlinked, moved to 433 / 31.
- Manual link pass (`scripts/cleanup/rollback/manual_st_link_20260420_095521.csv`):
  14 more ST projects linked after fuzzy matching + city/state verification.
  Confidence levels:
  - **9 slam-dunk** (near-exact after stripping "Apartments/Apt" suffix):
    Cottages of Edina, Northampton Arms, Alexandra, Pheasant Run (×4),
    Cambria HOA.
  - **5 medium**, all confirmed by matching city+state: Pacifica Leucadia HOA,
    Versante (Avondale AZ), Henderson Terrace (Bridgeport TX — Opp address is
    literally on Henderson St), Adiamo Pine/Palm Valley (Goodyear AZ — Pine/Palm
    looks like a typo, flag for team), Seattle Heights.
- **Final:** 447/464 ST projects linked. 17 remain — all unmatchable: raw street
  addresses (4706 Cass St etc.), synthetic feeder keys (`TX_DFW_Feeder_*`,
  `CA_CARLSBAD_SA07_*`), 2 CALIFORNIA_TEST_SITE records, a few Encinitas/
  Solana Beach properties that don't have an Opp.

**Agreement_Name__c backfill on linked Opps:**
- 25 Opps backfilled from their linked ST's `Site_Name__c` value (canonical
  `City_MDU_Name` format). Rollback:
  `scripts/cleanup/rollback/agreement_name_backfill_20260420_094545.csv`.
- 6 more backfilled in the manual-link pass (Versante, Cottages of Edina,
  Adiamo Palm Valley, Seattle Heights, Pacifica Leucadia, Cambria HOA).
- 3 blocked by **DUPLICATE_VALUE** — same property has two Opps, one from the
  Monday migration (3/24) and one from a later 3/31 import. See task #7 for
  reconciliation.
- **Final:** 1,075 / 3,648 Opps have Agreement_Name populated (+31 from this
  pass). 2,573 still blank — most are MDU Opps without a linked ST project;
  would need Property_Location__c cross-referencing for the next pass.

## Handoff to team — 2026-04-20 (easy-wins cut, human review next)

Stopping automated passes here. Remaining items pass to the sales/ops team for
real-eyes review rather than more heuristics:

- **Phase 3 — mixed caps bucket (~114 records)**: names with at least one ALL
  CAPS word mixed with title-case. Brand acronyms (MAA, IMT, IPG, LYV, CP, LLC,
  FKA, RE) make bulk automation too risky. Examples: `ANDERSON SIGNS - SMB 300m`,
  `MAA Copper Ridge`, `The ONE at Mountain Vista`, `Sunridge Manor Apts - NOW -
  The Manhattan`, `Bella Vista LOST`, `Artisan Luxury Apartments [JEFFERSON
  CENTER I]`.
- **Duplicate Opp reconciliation**: at least 3 known (Birchwood Apts, Bradley
  Arms, The Bungalows) where a Monday-migration Opp (3/24, Monday_Item_ID set)
  and a 3/31-import Opp (Agreement_Name set, `City_MDU_Name`) refer to the same
  property. Scan for the full set and merge.
- **29 blank Property_State__c**: generic business names with no location signal
  (Fish District, Foodies, Go Dogs, Keri Michelle Interiors, etc.). Team can
  look these up from account or context.
- **McQueen one-off**: `MCQUEEN LANDING HOA` became `Mcqueen Landing HOA` —
  should be `McQueen`. Fix manually.
- **Adiamo Pine/Palm Valley**: ST says `Adiamo Pine Valley`, Opp says `Adiamo
  Palm Valley`. Same property (Goodyear AZ confirmed by city/state). Pick the
  correct one.
- **Stage cleanup**: during Phase 1–2 several Opps landed in Prospecting or
  blank that are probably Closed Lost — Arbor on Broadway ("not a fit"), Harker
  Heights MHP ("Low Return"), Cherry Tree Apts ("16 units — too small"), 58th
  Plaza ("NO MDU"), Fort Hood MHP. Worth a sweep.
- **Next-level Agreement_Name backfill**: 2,573 Opps still have blank
  Agreement_Name. Most are MDU Opps without a linked ST project. Next pass
  would cross-reference Property_Location__c to find matches.

## Phase 3 — mixed caps bucket (deferred to team review)

Per-record manual judgment. Brand acronyms like MAA / IMT / IPG / LYV / CP / LLC /
FKA / RE make automation risky.

## Deferred decisions

- **⚫ (black circle) trailing markers** — 16 TX-area properties have a ⚫ suffix.
  Meaning unknown; left in place until clarified.
- **Trailing punctuation** — 6 records (`ADVANCED SPINE -`, `The Ridge & Shores
  Apartments -`, four `Apts.`/`Ave.`/`Inc.` records). First two likely drop the ` -`;
  rest keep the abbreviation period.

## Known downstream risks

- **`link_sitetracker_opportunities.py`** matches unlinked ST projects via
  `Agreement_Name__c` (priority) then `Opportunity.Name` (fallback). Agreement_Name
  is currently populated on **0 of 37** future-matchable ST projects — backfilling
  it is a separate tracked task.
- No other script updates Opp.Name; migration importers (`migration_phase2_opportunities.py`)
  INSERT only, so re-running would create duplicates, not overwrite.
