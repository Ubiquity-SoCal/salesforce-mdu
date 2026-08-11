# NE/TX opportunity contact reports: restrict to MDU record type

**Date:** 2026-07-13
**Org:** cass1@ubiquitygp.com (fun-power-747)
**Status:** deployed and verified

## Problem

The two NE/TX contact reports built on 2026-07-09 were pulling Business
opportunities alongside MDUs. Their only filters were:

1. Property State equals NE, TX
2. Category not equal to Cat 2, Cat 3

Neither report filtered on Opportunity record type, so every Business ROE and
Business Sales opportunity in NE/TX came through.

`NE TX Opportunities Primary Contact` was returning 1,067 rows:

| Record type      | Rows  |
| ---------------- | ----- |
| MDU/SFU          |   823 |
| Business ROE     |   213 |
| Business Sales   |    30 |
| (no record type) |     1 |
| **Total**        | 1,067 |

## Root cause

The filter could not simply be added in the report builder. Both custom report
types were created without Record Type in their field layout, so
`Opportunity$RecordType` was not a selectable or filterable field on any report
built from them. Deploying the filter alone fails with
`Invalid field name: Opportunity$RecordType`.

The fix is therefore two components per report:

1. Add `RecordType` to the report type field layout (additive, does not alter
   existing reports built on it).
2. Add the filter `Record Type equals MDU/SFU` to the report.

## Metadata gotchas hit here

- In `ReportType` XML the field token is `RecordType`, **not** `RecordTypeId`.
  `RecordTypeId` fails with `Could not find field RecordTypeId in table Opportunity`.
- In `Report` XML the filter value must be **fully qualified**: `Opportunity.MDU`
  (object + record type developer name). Both `MDU` and the label `MDU/SFU` fail
  with `no RecordType named ... found`.
- The `package.xml` report member uses the folder **developer** name
  (`MDU_Sales_Reports/...`), not the folder label (`MDU Sales Reports/...`).

## Components changed

| Component                                              | Type       | Change                       |
| ------------------------------------------------------ | ---------- | ---------------------------- |
| `MDU_Opportunities_Primary_Contact`                    | ReportType | added `RecordType` field     |
| `MDU_Opportunities_with_Contacts`                      | ReportType | added `RecordType` field     |
| `MDU_Sales_Reports/NE_TX_Opportunity_Primary_Contact`  | Report     | added Record Type = MDU/SFU  |
| `MDU_Sales_Reports/NE_TX_Opportunity_Contacts_Ownership` | Report    | added Record Type = MDU/SFU  |

## Verification

Ran both reports through the Analytics REST API after deploy (`allData: true`,
so no truncation) and cross-checked every row against SOQL.

- **NE TX Opportunities Primary Contact:** 1,067 rows to 823. The 244 removed
  reconcile exactly to 213 Business ROE + 30 Business Sales + 1 null record type.
  Zero non-MDU opportunities remain.
- **NE TX Opportunity Contacts Ownership:** 940 detail rows across 816 distinct
  opportunities. Zero non-MDU opportunities remain.

The contacts report shows 816 distinct opportunities rather than 823 because it
joins to contacts, so the 7 MDU opportunities with no linked contact drop out.
That is expected for a with-contacts report type, not a filter defect.

## Rollback

`rollback/` holds the pristine pre-change metadata retrieved from the org.

```
sf project deploy start --metadata-dir rollback --wait 10
```

## Open data issue (not fixed here)

Opportunity `Omaha Steaks` (`006WR00000vbyfWYAQ`, NE, Prospecting) has a **null
RecordTypeId**. It is a business, not an MDU, and it is now correctly excluded,
but an opportunity with no record type is a data-hygiene problem worth assigning
a record type to.
