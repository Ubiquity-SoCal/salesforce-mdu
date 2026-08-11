"""
Build a meeting-driven update proposal for SF Opps.
Uses verified manual mapping + extracted action items from 4/29 10:34am call transcript.

Outputs a CSV proposal: per-property, what to change.
"""
import csv, json
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

# Manual mapping: Tracker Site Name -> SF Opp Id (verified by direct lookup)
# Format: tracker_site -> {sf_id, action, action_date, note, projected_close_override}
# action_date format: 'YYYY-MM-DD' or '' for none
# action: short text for Next_Action__c
# Action items derived from transcript at C:\Users\cass\Work_Projects\tl;dv\transcript_4-29_1034am_readable.txt

TODAY = '2026-04-30'

# Use date convention: tracker target close date drives Projected_Close_Date__c update.
# Action / Action Date / Note come from transcript only.

PLAN = [
    # === Brett's territory ===
    {
        'tracker': 'Mesa_MDU_Falcon Glen Apartments', 'sf_id': None, 'sf_name_filter': "Name='Falcon Glen Apartments'",
        'next_action': 'Brett to forward to owner Linda Inabe (CA) and pitch proposal; plan CA trip',
        'next_action_date': None,
        'note_topic': 'Falcon Glen — 4/29 call',
        'tracker_target': '2026-05-29',
    },
    {
        'tracker': 'Decatur_MDU_The Laredo Apartments', 'sf_id': None, 'sf_name_filter': "Name='The Laredo Apartments'",
        'next_action': 'Melissa to schedule meeting w/ Brett + Amy on NextLink offering; aggressive bulk pricing',
        'next_action_date': None,
        'note_topic': 'Laredo — 4/29 call',
        'tracker_target': '2026-05-29',
    },
    {
        'tracker': 'Mesa_MDU_Woodglen Square Condo II', 'sf_id': None, 'sf_name_filter': "Name='Woodglen Square ll'",
        'next_action': 'Maps/floor plans received from Taylor; awaiting address list to start engineering',
        'next_action_date': None,
        'note_topic': 'Wood Glen Square ll — 4/29 call',
        'tracker_target': None,
    },
    {
        'tracker': 'Capri on Camelback', 'sf_id': None, 'sf_name_filter': "Name='Capri on Camelback'",
        'next_action': 'Brett to contact owner re bulk requirement (hut needs bulk to work)',
        'next_action_date': None,
        'note_topic': 'Capri on Camelback — 4/29 call',
        'tracker_target': None,
    },
    {
        'tracker': 'Mesa_MDU_The Traditions Apartments', 'sf_id': None, 'sf_name_filter': "Name='The Traditions Apartments'",
        'next_action': 'Niraj to send legal note to Caitlin re cancellation comm to AT&T; PAL not being canceled',
        'next_action_date': None,
        'note_topic': 'Traditions — 4/29 call',
        'tracker_target': None,
    },
    {
        'tracker': 'Mesa_MDU_La Mesa Village Apartments', 'sf_id': None, 'sf_name_filter': "Name='La Mesa Village Apartments'",
        'next_action': 'MDU On Net — Access Agreement in next 30 days',
        'next_action_date': None,
        'note_topic': 'La Mesa Village — 4/29 call',
        'tracker_target': '2026-05-29',
    },
    {
        'tracker': 'Mesa_MDU_Garden Place Apartments', 'sf_id': None, 'sf_name_filter': "Name='Garden Place Apartments'",
        'next_action': 'MDU On Net — Access Agreement in next 30 days',
        'next_action_date': None,
        'note_topic': 'Garden Place — 4/29 call',
        'tracker_target': '2026-05-29',
    },
    {
        'tracker': 'Washington_MDU_Coyote Creek', 'sf_id': None, 'sf_name_filter': "Name='Coyote Creek'",
        'next_action': 'Brett to follow up with leadership and owner',
        'next_action_date': None,
        'note_topic': 'Coyote Creek — 4/29 call',
        'tracker_target': None,
    },

    # === Bill's territory ===
    {
        'tracker': 'Killeen_MDU_Eastgate Village Apartments', 'sf_id': None, 'sf_name_filter': "Name='Eastgate Village Apartments'",
        'next_action': 'Bill to coordinate with Angie to revive (reach out to owner Sean Darden); waiting on W-9 + PAL addendum signature',
        'next_action_date': None,
        'note_topic': 'Eastgate — 4/29 call',
        'tracker_target': '2026-06-01',
    },
    {
        'tracker': 'Mesa_MDU_Westmount at The District Apartments', 'sf_id': None, 'sf_name_filter': "Name='Westmount at The District Apartments'",
        'next_action': "Push PAL signature before Walker's paternity leave (early May); Kyle reaching out to backup",
        'next_action_date': '2026-05-08',
        'note_topic': 'Westmount at the District — 4/29 call',
        'tracker_target': '2026-06-15',
    },
    {
        'tracker': 'Mesa_MDU_Westmount at Urban Trails', 'sf_id': None, 'sf_name_filter': "Name='Westmount at Urban Trails'",
        'next_action': "Push PAL signature before Walker's paternity leave (early May); Kyle reaching out to backup",
        'next_action_date': '2026-05-08',
        'note_topic': 'Westmount at Urban Trails — 4/29 call',
        'tracker_target': '2026-06-15',
    },
    {
        'tracker': 'Mesa_MDU_Amberwood Manor', 'sf_id': None, 'sf_name_filter': "Name='Amberwood Manor'",
        'next_action': 'On HOA agenda for May; asked to be part of meeting, awaiting response',
        'next_action_date': None,
        'note_topic': 'Amberwood Manor — 4/29 call',
        'tracker_target': '2026-06-01',
    },
    {
        'tracker': 'Mesa_MDU_Bridgewood Townhomes', 'sf_id': None, 'sf_name_filter': "Name='Bridgewood Townhomes'",
        'next_action': 'On HOA agenda for May; asked to be part of meeting, awaiting response',
        'next_action_date': None,
        'note_topic': 'Bridgewood Townhomes — 4/29 call',
        'tracker_target': '2026-06-01',
    },
    {
        'tracker': 'Omaha_MDU_4813-4823 Boyd St Apartments', 'sf_id': None, 'sf_name_filter': "Name='4813-4823 Boyd St Apartments'",
        'next_action': 'Calling Dr. Kumar — hard to reach but willing to sign once contacted',
        'next_action_date': None,
        'note_topic': '4813-4823 Boyd St — 4/29 call',
        'tracker_target': '2026-06-30',
    },
    {
        'tracker': 'Omaha_MDU_Boyd Street Apartments', 'sf_id': None, 'sf_name_filter': "Name='6314 Boyd Street'",  # ambiguous, flag for Koa
        'next_action': 'Calling Dr. Kumar — hard to reach but willing to sign once contacted',
        'next_action_date': None,
        'note_topic': 'Boyd St Apartments — 4/29 call',
        'tracker_target': '2026-07-01',
        'AMBIGUOUS_MATCH': 'Tracker says "Boyd Street Apartments 26 units" — possible matches: 6314 Boyd Street (Bill, Prospecting, pc=2026-06-01), 6302 Boyd Street (Cass, Prospects). Verify which one.',
    },
    {
        'tracker': 'Omaha_MDU_Howard Street Apartments', 'sf_id': None, 'sf_name_filter': "Name='Howard Street'",
        'next_action': 'Kelly wants meeting this week; Melissa to set up face-to-face (Kelly owns both Howard + Terrace Garden)',
        'next_action_date': '2026-05-02',
        'note_topic': 'Howard Street — 4/29 call',
        'tracker_target': '2026-07-01',
    },
    {
        'tracker': 'Omaha_MDU_Terrace Garden Townhomes', 'sf_id': None, 'sf_name_filter': "Name='Terrace Garden Apartments'",
        'next_action': 'Kelly wants meeting this week; Melissa to set up face-to-face (Kelly owns both Howard + Terrace Garden)',
        'next_action_date': '2026-05-02',
        'note_topic': 'Terrace Garden — 4/29 call',
        'tracker_target': '2026-07-02',
    },
    {
        'tracker': 'Killeen_MDU_Liberty Manor', 'sf_id': None, 'sf_name_filter': "Name='Liberty Manor'",
        'next_action': 'Melissa to follow up — went radio silent after good initial call; SITAC + Bill calls unanswered',
        'next_action_date': None,
        'note_topic': 'Liberty Manor — 4/29 call',
        'tracker_target': '2026-06-01',
    },
    {
        'tracker': 'Killeen_MDU_Williamsburg Townhouses and Apts', 'sf_id': None, 'sf_name_filter': "Name='Williamsburg Townhomes and Apartments'",
        'next_action': 'Good text exchange showing interest; PAL under proposal review',
        'next_action_date': None,
        'note_topic': 'Williamsburg — 4/29 call',
        'tracker_target': '2026-06-01',
    },
    {
        'tracker': 'Bedford Square [fmr Maplewood Court]', 'sf_id': None, 'sf_name_filter': "Name='Bedford Square [fmr Maplewood Court]'",
        'next_action': 'Belinda interested; Taylor sent PAL 4/28 before going on break — owner reviewing',
        'next_action_date': None,
        'note_topic': 'Bedford Square — 4/29 call',
        'tracker_target': '2026-06-02',
    },
    {
        'tracker': 'Taylor_MDU_Gardens of Taylor', 'sf_id': None, 'sf_name_filter': "Name='Gardens of Taylor'",
        'next_action': 'Melissa to send PAL request to Caitlin (Taylor on break) cc Brett today; legal description received',
        'next_action_date': '2026-04-30',
        'note_topic': 'Gardens of Taylor — 4/29 call',
        'tracker_target': '2026-06-03',
    },
    {
        'tracker': 'Mineral Wells_MDU_Parkwood Apartments', 'sf_id': None, 'sf_name_filter': "Name='Parkwood Apartments'",
        'next_action': 'Still under discussion with owner',
        'next_action_date': None,
        'note_topic': 'Parkwood Apts (Mineral Wells) — 4/29 call',
        'tracker_target': '2026-06-01',
    },

    # === Melissa's territory ===
    {
        'tracker': 'Bridgeport_MDU_Creekside Apartments', 'sf_id': None, 'sf_name_filter': "Name='Creekside Apartments'",
        'next_action': 'Melissa to call — chasing PAL addendum (already have bulk agreement)',
        'next_action_date': None,
        'note_topic': 'Creekside Apts — 4/29 call',
        'tracker_target': '2026-05-15',
    },
    {
        'tracker': 'Killeen_MDU_Patriot Place', 'sf_id': None, 'sf_name_filter': "Name='Patriot Place'",
        'next_action': 'Melissa to solidify bulk vs EMA decision by end of 4/30; owner ready to send EMA contracts',
        'next_action_date': '2026-04-30',
        'note_topic': 'Patriot Place — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Newark_MDU_Heritage of Newark (Newark Beach Estates)', 'sf_id': None, 'sf_name_filter': "Name='Heritage of Newark (FKA Newark Beach Estates)'",
        'next_action': 'Going bulk; bulk language change needed — wait for Taylor back Monday 5/4',
        'next_action_date': '2026-05-04',
        'note_topic': 'Heritage of Newark — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Omaha_MDU_1001 Apartments', 'sf_id': None, 'sf_name_filter': "Name='The 1001 Apartments'",
        'next_action': 'Owner Bob sitting on decision; Melissa to reach out again',
        'next_action_date': None,
        'note_topic': '1001 Apts — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Omaha_MDU_Bristol Square Apts', 'sf_id': None, 'sf_name_filter': "Name='Bristol Square Apartments'",
        'next_action': 'Melissa to schedule mtg w/ Brett + Niraj; equipment-in-closet/no-power confusion to resolve in person',
        'next_action_date': None,
        'note_topic': 'Bristol Square (184u) — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Omaha_MDU_Northampton Court Condos', 'sf_id': None, 'sf_name_filter': "Name='Northampton Court Condominiums'",
        'next_action': 'PAL signed; verbal on bulk by end of week — Melissa to follow up today',
        'next_action_date': '2026-04-30',
        'note_topic': 'Northampton Courts — 4/29 call',
        'tracker_target': '2026-05-15',
    },
    {
        'tracker': 'Killeen_MDU_The Bungalows', 'sf_id': None, 'sf_name_filter': "Name='Killeen_MDU_The Bungalows'",
        'next_action': 'On hold — owner Lisa Jean unreachable + doing construction; awaiting NID placement decision',
        'next_action_date': None,
        'note_topic': 'The Bungalows — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Jarrell_MDU_Sonterra Apartment Homes', 'sf_id': None, 'sf_name_filter': "Name='Sonterra Apartment Homes'",
        'next_action': 'EMA out for signature; owner Manny + daughters agreed; 48hr review — Melissa to follow up today',
        'next_action_date': '2026-04-30',
        'note_topic': 'Sonterra Apts — 4/29 call',
        'tracker_target': '2026-04-30',
    },
    {
        'tracker': 'Encinitas_MDU_Sandpiper Point', 'sf_id': None, 'sf_name_filter': "Name='Sandpiper Pointe'",
        'next_action': 'Decision: send ROE today (not PAL); HOA willing EMA, not bulk (50% only); SFU homes',
        'next_action_date': '2026-04-30',
        'note_topic': 'Sandpiper Pointe — 4/29 call',
        'tracker_target': '2026-06-15',
    },
    {
        'tracker': 'Solana Beach_MDU_Seascape Sur', 'sf_id': None, 'sf_name_filter': "Name='Seascape Sur'",
        'next_action': 'Pankaj working w/ Pam Walker on PAL questions; PAL expected 45-60d; bulk needed for feasibility',
        'next_action_date': None,
        'note_topic': 'Seascape Sur — 4/29 call',
        'tracker_target': '2026-05-30',
    },
    {
        'tracker': 'Solana Beach_MDU_Santa Helena Park Condominiums', 'sf_id': None, 'sf_name_filter': "Name='Santa Helena Park Condominiums'",
        'next_action': 'Pankaj working with telecom consultant questions; PAL revisions sent',
        'next_action_date': None,
        'note_topic': 'Santa Helena — 4/29 call',
        'tracker_target': '2026-05-15',
    },
]


# Resolve sf_id from name filter
print(f"Resolving SF Opp Ids for {len(PLAN)} tracker properties...\n")
for p in PLAN:
    if p['sf_id']: continue
    q = sf.query(f"SELECT Id, Name, StageName, Projected_Close_Date__c, Next_Action__c, Next_Action_Date__c, Owner.Name FROM Opportunity WHERE {p['sf_name_filter']} AND IsClosed=false")
    if q['totalSize'] == 1:
        r = q['records'][0]
        p['sf_id'] = r['Id']
        p['sf_name'] = r['Name']
        p['sf_stage'] = r['StageName']
        p['sf_owner'] = r['Owner']['Name']
        p['sf_proj_close_current'] = r.get('Projected_Close_Date__c') or ''
        p['sf_next_action_current'] = r.get('Next_Action__c') or ''
        p['sf_next_action_date_current'] = r.get('Next_Action_Date__c') or ''
    elif q['totalSize'] == 0:
        p['sf_id'] = 'NOT FOUND'
    else:
        p['sf_id'] = f"AMBIGUOUS ({q['totalSize']} matches)"

# Print proposal table
print(f"{'Tracker':45s}  {'SF Name':40s}  {'Stage':22s}  {'Curr PC':12s}  {'Tracker Target':14s}")
print("-" * 160)
for p in sorted(PLAN, key=lambda x: x.get('sf_owner', 'zzz')):
    if 'sf_name' in p:
        print(f"{p['tracker'][:45]:45s}  {p['sf_name'][:40]:40s}  {p['sf_stage'][:22]:22s}  {p['sf_proj_close_current'] or '-':12s}  {p.get('tracker_target') or '-':14s}")
    else:
        print(f"{p['tracker'][:45]:45s}  ** {p['sf_id']} **  filter={p['sf_name_filter']}")

# Save proposal CSV
with open('meeting_update_proposal.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Tracker_Site', 'SF_Id', 'SF_Name', 'SF_Owner', 'SF_Stage',
                'Current_Proj_Close', 'Proposed_Proj_Close', 'PC_Change',
                'Current_Next_Action', 'Proposed_Next_Action',
                'Current_Next_Action_Date', 'Proposed_Next_Action_Date',
                'Note_Topic', 'Ambiguous_Note'])
    for p in PLAN:
        cur_pc = p.get('sf_proj_close_current', '')
        new_pc = p.get('tracker_target') or ''
        pc_change = 'YES' if (new_pc and new_pc != cur_pc) else ''
        w.writerow([
            p['tracker'], p.get('sf_id',''), p.get('sf_name',''), p.get('sf_owner',''), p.get('sf_stage',''),
            cur_pc, new_pc, pc_change,
            p.get('sf_next_action_current',''), p['next_action'],
            p.get('sf_next_action_date_current',''), p.get('next_action_date') or '',
            p['note_topic'], p.get('AMBIGUOUS_MATCH', ''),
        ])

print(f"\nWrote meeting_update_proposal.csv with {len(PLAN)} rows")
