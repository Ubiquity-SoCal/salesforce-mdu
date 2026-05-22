# Business Penetration Dashboard

Native Salesforce Lightning dashboard showing serviceable-business penetration
(lit buildings, active vs total units) off `Property_Location__c`. Built 2026-05-22
from the 5/22 meeting action item (Amir: penetration in lit buildings). Data comes
from Vetro via the existing vetro-sync, so the dashboard is live against SF.

- **Dashboard:** Inside Sales > Business Penetration
  (`01ZWR000004X6if2AC`, DeveloperName `Business_Penetration`)
- **Reports:** folder `PropertyReports`, prefix `BizPen_*`

## Definitions

Every report is scoped to `Address_Type__c = 'Business' AND Import_Delete_Property__c = false`.

- **Lit** = building has >=1 active OR >=1 deactivated unit = `Penetration_Priority__c IN ('Category 1','All Active')`.
- **Penetration** = `Active_Unit_Count__c / Property_Unit_Count__c` (door-weighted via a report
  Custom Summary Formula `Active:SUM / Total:SUM * 100` for rollups).

## Two new formula fields on Property_Location__c (non-destructive)

The existing `Priority__c` was left untouched. Two parallel fields were added:

- **`Penetration__c`** (Percent) = `IF(Property_Unit_Count__c > 0, Active_Unit_Count__c / Property_Unit_Count__c, 0)`.
  NOTE: Percent type multiplies the formula result by 100 for display, so the formula
  returns the raw ratio (Hutto 71/163 -> field value 43.6, displays 43.6%).
- **`Penetration_Priority__c`** (Text) = mirrors `Priority__c` BUT the deactivated check runs
  before the single-unit branch, so churned single-suite buildings land in Category 1
  (lit) instead of Category 3. This reclassified 80 business buildings (Cat3 -> Cat1),
  making lit = Cat1 + All Active = 679 in SF (matches the workbook's 686 minus 5/19-sync drift).

## Components

- KPI tiles: Lit Buildings (679), Overall Penetration (40.8%), Active Units (775),
  Deactivated (193), Category 1 (236), Category 2 pipeline (1,602).
- Charts: Penetration % by State (bar, CSF), Priority Mix (donut), Penetration Distribution (bar, bucket).
- Table: Category 1 Action List (lowest penetration first).
- Filters (re-slice all): State, Penetration Priority. (Owner filter omitted: not enumerable
  in metadata; the action list shows the owner column.)

## Rebuild / refresh

Numbers are as fresh as the last vetro-sync (run `Automation/vetro-sync` to refresh SF).
The dashboard/reports/fields are rebuilt by, in order:

1. `SalesForce/scripts/deploy/2026-05-22-build-penetration-fields.py` (fields + Admin FLS)
2. `SalesForce/scripts/deploy/2026-05-22-build-penetration-reports.py` (set `APPLY=1` to commit)
3. `SalesForce/scripts/deploy/2026-05-22-build-business-penetration-dashboard.py` (set `APPLY=1`)

All deploy scripts default to checkOnly validation; prod requires atomic deploys, so
validate first, then re-run with `APPLY=1`.

## To do (not blocking)

- Pin the dashboard to the Business Sales home tab (FlexiPage org-default assignment is a
  UI click, not settable via metadata).
- Broaden field FLS beyond System Administrator if the team needs to open the underlying
  reports directly (the dashboard runs as cass1, so viewing the dashboard already works).
