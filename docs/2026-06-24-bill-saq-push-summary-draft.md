# DRAFT — Salesforce update from Bill's MDU master list (2026-06-24)

*Audience: Bill (sheet owner). Retarget for the team/Taylor if needed. Can be dropped into an Outlook draft on request.*

---

**Subject:** MDU statuses synced to Salesforce — a few items need your input

Hi Bill,

I took the statuses from your *Master List MDU Assignments* workbook and synced them into
Salesforce so the Opportunity stages now match where you have each site. Quick rundown of
what changed, what I held back, and where I need a decision from you.

## What I updated (~300 opportunities)

Mapped your SAQ Status column onto the SF pipeline:

| Your status | → Salesforce stage | Count |
|---|---|---|
| Closed - Lost / Closed - Contact Info | Closed Lost (with a loss reason) | ~218 |
| Engaged | Engaged | 43 |
| Proposal Sent | Proposal Sent | 20 |
| Proposal Review / Pending Signature | Contract Negotiations | 11 |
| Hold | On Hold | 9 |

For the closes, I set the loss reason from your notes — 117 "No Contact Info", 67 "No
Decision / Non-Responsive", 26 "Not Interested", and a handful of others. Every change is
logged with before/after values.

## Held back — need your call (nothing changed on these)

**1. Sites you marked closed that Salesforce shows as already secured or built (6).**
These look like the sheet is out of date — closing them would erase a won site, so I left
them alone:
- 78th Place Apartments, Bristol Square, Orchard Park, Paul Mark Apts, Beacons Beach Village
  MHP (all at *PAL/ROE Complete*) and Newark Beach Estates (*Marketing/Bulk Complete*).
- **Q: are these genuinely dead, or should the sheet be updated to match SF?**

**2. Sites you closed that SF shows as live deals (7).**
- *Contract Negotiations:* Cicada Springs RV Park, Garden Place, Santa Helena Park
- *Marketing/Bulk In Progress:* Paloma Gardens (×2), Saffari Apts, Soaring Eagle
- **Q: confirm these should be closed and I'll push them.**

**3. Sites you're working that SF had as Closed Lost (7).** Want me to reopen them to match
your sheet? (Most are yours.)

**4. Two records with conflicting entries in your sheet:**
- *Encore on First* vs *Mesa Housing Associates LLC* — same property? (one row said Proposal
  Sent, the other Closed Lost)
- *Mesa Coronado Condos* vs *Mesa Coronado II* — same property or two different ones?

## Cleanup items in the sheet (FYI)

- **~52 rows have no AgreeName key** — I matched them to SF by property name this time, but
  if you can backfill the key column, future syncs will be exact.
- **5 properties have duplicate records in Salesforce** (Oak Ridge, Sire Wellington, The Wyatt
  at Presidio Junction, Westbrook Gardens) — I'll clean these up separately.
- **1 bad close date** ("12/102025" on Pleasant View MHP) — fixed the status, left the date.

Happy to walk through any of these. Just need your yes/no on items 1–4 and I'll finish the rest.

Thanks,
Cass
