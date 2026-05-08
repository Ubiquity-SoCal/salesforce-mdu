"""
Apply field + stage updates derived from 4/29/2026 10:34am MDU pipeline meeting.

Updates per Opp:
- StageName (where meeting reset stage)
- Hold_Reason__c (where moving to On Hold)
- Projected_Close_Date__c (sync to tracker date when stale or missing)
- Next_Action__c
- Next_Action_Date__c
- One ContentNote summarizing meeting outcome

Logs Before/After to audit_logs/. Dry-run first.

Usage:
  python apply_meeting_updates_2026-04-29.py --dry-run
  python apply_meeting_updates_2026-04-29.py --apply
"""
import argparse, csv, sys, json
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.apply and not args.dry_run:
    print("Specify --dry-run or --apply"); sys.exit(1)

sf = Salesforce(
    username='cass1@ubiquitygp.com',
    password='Hawaiian1984',
    security_token='IBSKT6CFUpSUJWxq1CMm0HkFC',
)

# Fully-resolved plan: Opp Id + the changes to apply
# Each entry's 'changes' is what we want the field to be (None = don't touch).
# 'note_body' is a ContentNote body to attach.
# 'tracker_owner' triggers OwnerId reassignment to the active SF user.
NOTE_TITLE = '2026-04-29 MDU Pipeline Meeting'

# Tracker owner first-name -> active SF User Id
TRACKER_OWNER_TO_USER = {
    'Bill':    '005WR00000DEU6oYAH',  # Bill Holick
    'Brett':   '005WR00000Ewjj3YAB',  # Brett Spivey (active)
    'Melissa': '005WR000003CD6DYAW',  # Melissa Baker (active)
    'Niraj':   '005WR000008V4VoYAK',  # Niraj Patel
    'Pankaj':  '005Hs00000Eo9rcIAB',  # Pankaj Gulati
}

# Default Next_Action_Date when meeting didn't specify: one week from meeting day
DEFAULT_NAD = '2026-05-07'

PLAN = [
    # === Stage moves + updates ===
    {
        'sf_id': None,
        'name_lookup': "Name='Eastgate Village Apartments'",
        'changes': {
            'StageName': 'Prospecting',
            'Projected_Close_Date__c': '2026-06-01',
            'Next_Action__c': 'Bill coordinating with Angie to revive (reach Sean Darden); waiting on W-9 + PAL addendum signature',
        },
        'note_body': "Eastgate update from 4/29 call.\n\nWent radio silent after PAL signed; owner Sean Darden wanted only $5,000 payment then stopped responding when W-9 was requested. Niraj had marked it frozen due to no contact.\n\nDecision: revive. Bill to coordinate with Angie (had original contact with owner) to reach back out. 3 buildings. Fiber + lid on side approach is viable. Texas deployment call tomorrow will surface this.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Howard Street'",
        'changes': {
            'StageName': 'Engaged',
            'Projected_Close_Date__c': '2026-07-01',
            'Next_Action__c': "Kelly wants in-person meeting this week; Melissa setting up face-to-face (same owner as Terrace Garden, ~90 units)",
            'Next_Action_Date__c': '2026-05-02',
        },
        'note_body': "Howard Street update from 4/29 call.\n\nOwner Kelly also owns Terrace Garden (both ~90 units in Omaha). She showed strong interest in Omaha market and wants a meeting this week. Worth a trip up. Only a couple-hour drive for Bill.\n\nMelissa to set up face-to-face. AJ flagged this and the Westmount cluster as the main multi-property owners worth in-person.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Terrace Garden Apartments'",
        'changes': {
            'StageName': 'Engaged',
            'Projected_Close_Date__c': '2026-07-02',
            'Next_Action__c': "Kelly wants in-person meeting this week; Melissa setting up face-to-face (same owner as Howard Street, ~90 units)",
            'Next_Action_Date__c': '2026-05-02',
        },
        'note_body': "Terrace Garden update from 4/29 call.\n\nOwner Kelly also owns Howard Street (both ~90 units in Omaha). Showed strong interest in Omaha market and wants a meeting this week.\n\nMelissa to set up face-to-face per Pankaj direction.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Gardens of Taylor'",
        'changes': {
            'StageName': 'Prospecting',
            'Projected_Close_Date__c': '2026-06-03',
            'Next_Action__c': "Melissa to send PAL request to Caitlin (Taylor on break) cc Brett today; legal description received from Linda",
            'Next_Action_Date__c': '2026-04-30',
            'Sales_Status__c': 'Reached Out - Pending Response',
        },
        'note_body': "Gardens of Taylor update from 4/29 call.\n\nOwner Linda provided legal description and required info for PAL request. Existing bulk agreement expires August. PAL request to be submitted today by Melissa, routed to Caitlin (Taylor on break) with Brett copied.\n\nGood call Monday with Linda; she's engaged.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Capri on Camelback'",
        'changes': {
            'StageName': 'Contract Negotiations',
            'Next_Action__c': "Brett to contact owner re bulk requirement (hut needs bulk); owner asking when construction starts",
        },
        'note_body': "Capri on Camelback update from 4/29 call.\n\nOwner repeatedly asking when construction starts. Niraj confirmed: this is a hut build, must have bulk. Brett's initial conversation: owner not interested in bulk. Brett to push that bulk is the only way forward.\n\nNote: stage was 'EMA/Bulk Complete' but the Bulk agreement record (AGR-1040) has Status='Completed' with no signed_date and no IronClad ID. That's likely Monday.com migration noise. Bulk was never actually signed. Stage moved back to Contract Negotiations to reflect reality.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='The Traditions Apartments'",
        'changes': {
            'StageName': 'On Hold',
            'Hold_Reason__c': 'Build Not Approved',
            'Next_Action__c': "Niraj sending legal note to Caitlin re cancellation comm to owner; PAL not being canceled (may build as FiberFirst future)",
        },
        'note_body': "Traditions update from 4/29 call.\n\nAll 4 agreements signed in 2025 (PAL, EMA, PAL Addendum, MSA Addendum). Project was for AT&T/Lumen which has since changed. Pankaj direction: 'if we can't hold on to it anymore because of delays, let's be professional and inform them we are not moving forward.'\n\n160 units. Not in current footprint. Per Pankaj: cost of a hut for 160 units bulk deal. Probably not viable.\n\nMSA Addendum still needs to be canceled by AT&T side (hasn't happened). Niraj to coordinate with Caitlin on legal language for owner communication. Holding the PAL. May revisit as FiberFirst if a bulk emerges.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Coyote Creek'",
        'changes': {
            'Next_Action__c': "Brett to follow up with leadership and owner",
        },
        'note_body': "Coyote Creek update from 4/29 call.\n\nAgreements (PAL + EMA) signed in 2025. Brett owns the follow-up with leadership and owner per tracker. Owner mismatch noted: tracker shows Brett, SF shows Chuck McNeely (inactive). Should reassign owner.\n\n116 units, Washington UT.",
    },

    # === Field-only updates (no stage change, just dates / actions / notes) ===
    {
        'sf_id': None,
        'name_lookup': "Name='Falcon Glen Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-29',
            'Next_Action__c': "Brett to forward to owner Linda Inabe (CA) and pitch proposal; team open to CA trip",
        },
        'note_body': "Falcon Glen update from 4/29 call.\n\nOwner Linda Inabe lives in California. Pankaj suggested a CA visit if it would help advance the deal. Brett pitching to owner shortly.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='The Laredo Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-29',
            'Next_Action__c': "Melissa to schedule meeting with Brett + Amy on NextLink offering; aggressive bulk pricing",
        },
        'note_body': "Laredo update from 4/29 call.\n\nJoe Anderson (former Fiberforce rep) is now pushing NextLink to our leads. He had the relationship with Laredo. Initial pitch was NextLink-only; team got them to accept our proposal.\n\nMelissa to schedule meeting with Brett and Amy. Strategy: aggressive bulk offer. Need their current pricing. Melissa to send to Brett offline.\n\nLocation: Decatur TX (~25 min from Melissa, North TX). 2-gig service is on the table. ~50% of April new adds in SFU were 2-gig.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Woodglen Square ll'",
        'changes': {
            'Next_Action__c': "Maps + floor plans received from Taylor 4/29; awaiting address list to start engineering",
        },
        'note_body': "Wood Glen Square ll update from 4/29 call.\n\nPAL signed. Niraj waiting on data to start engineering. Taylor sent maps, floor plans, property maps on 4/29 (before going on break). Brett forwarding to Niraj. Address list still being compiled.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='La Mesa Village Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-29',
            'Next_Action__c': "MDU On Net. Access Agreement targeted in next 30 days",
        },
        'note_body': "La Mesa Village update from 4/29 call.\n\nMDU On Net status. Targeting Access Agreement in next 30 days.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Garden Place Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-29',
            'Next_Action__c': "MDU On Net. Access Agreement targeted in next 30 days",
        },
        'note_body': "Garden Place update from 4/29 call.\n\nMDU On Net status. Targeting Access Agreement in next 30 days.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Westmount at The District Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-06-15',
            'Next_Action__c': "Push PAL signature before Walker's paternity leave (early May); Kyle reaching out to backup contact",
            'Next_Action_Date__c': '2026-05-08',
        },
        'note_body': "Westmount at the District update from 4/29 call.\n\nWalker (primary contact) on paternity leave starting beginning of May. No out-of-office yet. Team is racing to get PAL signed before he disappears. Kyle reaching out to backup contact.\n\n154 units, Mesa.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Westmount at Urban Trails'",
        'changes': {
            'Projected_Close_Date__c': '2026-06-15',
            'Next_Action__c': "Push PAL signature before Walker's paternity leave (early May); Kyle reaching out to backup contact",
            'Next_Action_Date__c': '2026-05-08',
        },
        'note_body': "Westmount at Urban Trails update from 4/29 call.\n\nSame Walker contact as Westmount at the District (on paternity leave starting May). Trying to get PAL signed before he goes out. Kyle pursuing backup.\n\n159 units, Mesa.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Amberwood Manor'",
        'changes': {
            'Next_Action__c': "On HOA agenda for May; asked to participate in meeting, awaiting response",
        },
        'note_body': "Amberwood Manor update from 4/29 call.\n\nConfirmed on HOA agenda for May. Bill's team requested participation in May HOA meeting; awaiting response.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Bridgewood Townhomes'",
        'changes': {
            'Next_Action__c': "On HOA agenda for May; asked to participate in meeting, awaiting response",
        },
        'note_body': "Bridgewood Townhomes update from 4/29 call.\n\nSame HOA cluster as Amberwood Manor. Confirmed on HOA agenda for May. Awaiting response on participation request.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='4813-4823 Boyd St Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-06-30',
            'Next_Action__c': "Calling Dr. Kumar. Hard to reach but willing to sign once contacted",
        },
        'note_body': "4813-4823 Boyd St update from 4/29 call.\n\nDr. Kumar and partner have signed for us before. Hard to reach but reliable once they engage. Bill confident in close. Continuing outreach.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='6314 Boyd Street'",
        'changes': {
            'Projected_Close_Date__c': '2026-07-01',
            'Next_Action__c': "Calling Dr. Kumar. Hard to reach but willing to sign once contacted",
        },
        'note_body': "Boyd Street Apartments update from 4/29 call.\n\nSame Dr. Kumar relationship as 4813-4823 Boyd. Hard to reach, reliable once engaged.\n\nNOTE: tracker says 'Boyd Street Apartments 26 units' which most likely matches this 6314 Boyd Street record. Verify if needed.",
    },
    {
        'sf_id': '006WR00000wkABpYAM',  # Liberty Manor (Bill's Killeen 36u)
        'name_lookup': None,
        'changes': {
            'Next_Action__c': "Melissa to follow up. Went radio silent after good initial call; SITAC and Bill calls unanswered",
        },
        'note_body': "Liberty Manor update from 4/29 call.\n\nGood initial call, then radio silent. Stopped answering SITAC and Bill's calls. Bill flagged to Melissa to take over outreach (she was out for surgery last week, picking back up this week).\n\n36 units, Killeen TX.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Williamsburg Townhomes and Apartments'",
        'changes': {
            'Next_Action__c': "Good text exchange showing interest; PAL under proposal review with owner",
        },
        'note_body': "Williamsburg update from 4/29 call.\n\nGood text exchange with owner. Showing interest. PAL is in proposal review.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Bedford Square [fmr Maplewood Court]'",
        'changes': {
            'Projected_Close_Date__c': '2026-06-02',
            'Next_Action__c': "Belinda interested; Taylor sent PAL 4/28 before going on break. Owner reviewing",
        },
        'note_body': "Bedford Square update from 4/29 call.\n\nFormerly Maplewood Court. Owner Belinda is interested. Taylor sent PAL directly to Belinda on 4/28 before going on break. Owner reviewing.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Parkwood Apartments'",
        'changes': {
            'Next_Action__c': "Still under discussion with owner",
        },
        'note_body': "Parkwood Apartments (Mineral Wells) update from 4/29 call.\n\nStill under discussion with owner. No new movement reported.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Creekside Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-15',
            'Next_Action__c': "Melissa to call. Chasing PAL addendum (already have bulk agreement)",
        },
        'note_body': "Creekside Apartments update from 4/29 call.\n\nGoing bulk; agreement already in place. Waiting on PAL addendum. Melissa to call owner. Unclear what's holding it up.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Patriot Place'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-30',
            'Next_Action__c': "Melissa to solidify bulk vs EMA decision by end of 4/30; owner ready to send EMA contracts",
            'Next_Action_Date__c': '2026-04-30',
        },
        'note_body': "Patriot Place update from 4/29 call.\n\nMelissa's last conversation: going bulk. Owner ready to send EMA contracts if EMA. Decision needed before build. Melissa to solidify bulk vs EMA by EOD 4/30.\n\nNiraj noted this is a PAL property. In-unit work, more involved engineering than typical ROE. Wants to keep momentum while owner is engaged.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Heritage of Newark (FKA Newark Beach Estates)'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-30',
            'Next_Action__c': "Going bulk; bulk language change needed. Waiting for Taylor back Monday 5/4",
            'Next_Action_Date__c': '2026-05-04',
        },
        'note_body': "Heritage of Newark update from 4/29 call.\n\nMelissa explained to Chris that we're not paying attorney fees. That conversation went well. They are going bulk. Some bulk agreement language needs to be changed (Chris had been talking directly to Taylor). Waiting for Taylor back from break Monday 5/4.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='The 1001 Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-30',
            'Next_Action__c': "Owner Bob sitting on decision; Melissa to reach out again",
        },
        'note_body': "1001 Apartments update from 4/29 call.\n\nOwner Bob is sitting on the decision. No movement. Melissa to reach back out.\n\n111 units, Omaha.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Bristol Square Apartments'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-30',
            'Next_Action__c': "Melissa to schedule mtg w/ Brett + Niraj; equipment-in-closet/no-power confusion to resolve in person",
        },
        'note_body': "Bristol Square update from 4/29 call.\n\n184 units. High priority per Pankaj. Owner wants equipment in closet but there's no power. Team agreed to install fiber jack without equipment if marketing rights are secured. Email back-and-forth with Chuck caused confusion. Owner uncertain.\n\nFix: Melissa to set up meeting with Brett (and possibly Niraj) to walk through the approach in person. Bringing power into the closet is too costly for the owner.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Northampton Court Condominiums'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-15',
            'Next_Action__c': "PAL signed; verbal on bulk by end of week. Melissa to follow up today",
            'Next_Action_Date__c': '2026-04-30',
        },
        'note_body': "Northampton Courts update from 4/29 call.\n\nMelissa got owner to sign PAL. Owner called last week with a few questions about bulk; said he'd have it signed by end of this week. That's a verbal on bulk. Melissa to reach out today to confirm.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Killeen_MDU_The Bungalows'",
        'changes': {
            'Next_Action__c': "On hold. Owner Lisa Jean unreachable + doing construction; awaiting NID placement decision",
        },
        'note_body': "The Bungalows update from 4/29 call.\n\nOwner Lisa Jean is unreachable. Project on hold pending her construction activities. Niraj waiting to confirm whether NID can go on the side of the property. Feet-on-ground stop-bys haven't reached anyone.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Sonterra Apartment Homes'",
        'changes': {
            'Projected_Close_Date__c': '2026-04-30',
            'Next_Action__c': "EMA out for signature; owner Manny + daughters agreed; 48hr review. Melissa to follow up today",
            'Next_Action_Date__c': '2026-04-30',
        },
        'note_body': "Sonterra Apartment Homes update from 4/29 call.\n\nEMA sent for signature last week. Owner Manny and both daughters are in agreement; they asked for only 48 hours to review the EMA verbiage. Melissa was out last week for surgery, will follow up today.\n\nNote: tracker shows owner = Melissa, SF shows owner = Brett Spivey. Worth reassigning.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Sandpiper Pointe'",
        'changes': {
            'Projected_Close_Date__c': '2026-06-15',
            'Next_Action__c': "Decision: send ROE today (not PAL); HOA willing EMA, not bulk (50% only); SFU homes",
            'Next_Action_Date__c': '2026-04-30',
        },
        'note_body': "Sandpiper Pointe update from 4/29 call.\n\nPrivate road, single-family / townhome-style homes selling for $3M+/unit. No wireless coverage. Desperately need fiber.\n\nBoard had two attorneys, expected a PAL (one was sent ~2 years ago by Jeff Chao, since expired). Pankaj direction: ROE is fine since they're SFU and we don't go in-unit. ROE shorter, faster.\n\nBulk: only 50% of board agreed; preference is EMA until deployment proves successful, then revisit bulk. We have a verbal on EMA.\n\nMelissa sending ROE today with all addresses in the addendum.\n\nNote: tracker shows owner = Melissa, SF shows owner = Jeff Chao (inactive). Worth reassigning.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Seascape Sur'",
        'changes': {
            'Projected_Close_Date__c': '2026-05-30',
            'Next_Action__c': "Pankaj working w/ Pam Walker on PAL questions; PAL expected 45-60d; bulk required for feasibility",
        },
        'note_body': "Seascape Sur update from 4/29 call.\n\nPam Walker reached out 4/28 with PAL questions. Pankaj sent revised PAL with insurance and ISP boundaries. Telecom consultant on owner's side asking ISP questions. Answered.\n\nPAL expected to land in 45-60 days. Difficult and expensive build (multiple sections, custom per part). Without bulk, build not feasible. Pankaj will slow-track if bulk doesn't materialize.\n\nMelissa offered marketing help; Pankaj said hold until PAL signed.",
    },
    {
        'sf_id': None,
        'name_lookup': "Name='Santa Helena Park Condominiums'",
        'changes': {
            'Next_Action__c': "Pankaj working through telecom consultant questions; PAL revisions sent",
        },
        'note_body': "Santa Helena Park update from 4/29 call.\n\nSister property to Seascape Sur (both Solana Beach, Pam Walker contact, same telecom consultant). PAL under revision; questions being answered.",
    },
]

# Tracker owner per SF Opp Name (from xlsb), used to drive Owner reassignment
TRACKER_OWNERS_BY_SF_NAME = {
    'Eastgate Village Apartments': 'Bill',
    'Howard Street': 'Bill',
    'Terrace Garden Apartments': 'Bill',
    'Gardens of Taylor': 'Bill',
    'Capri on Camelback': 'Brett',
    'The Traditions Apartments': 'Brett',
    'Coyote Creek': 'Brett',  # tracker says Brett, SF=Chuck
    'Falcon Glen Apartments': 'Brett',
    'The Laredo Apartments': 'Brett',
    'Woodglen Square ll': 'Brett',
    'La Mesa Village Apartments': 'Brett',
    'Garden Place Apartments': 'Brett',
    'Westmount at The District Apartments': 'Bill',
    'Westmount at Urban Trails': 'Bill',
    'Amberwood Manor': 'Bill',
    'Bridgewood Townhomes': 'Bill',
    '4813-4823 Boyd St Apartments': 'Bill',
    '6314 Boyd Street': 'Bill',
    'Liberty Manor': 'Bill',
    'Williamsburg Townhomes and Apartments': 'Bill',
    'Bedford Square [fmr Maplewood Court]': 'Bill',
    'Parkwood Apartments': 'Bill',
    'Creekside Apartments': 'Melissa',
    'Patriot Place': 'Melissa',
    'Heritage of Newark (FKA Newark Beach Estates)': 'Melissa',
    'The 1001 Apartments': 'Melissa',
    'Bristol Square Apartments': 'Melissa',
    'Northampton Court Condominiums': 'Melissa',
    'Killeen_MDU_The Bungalows': 'Melissa',
    'Sonterra Apartment Homes': 'Melissa',  # tracker says Melissa, SF=Brett
    'Sandpiper Pointe': 'Melissa',  # tracker says Melissa, SF=Jeff Chao
    'Seascape Sur': 'Pankaj',
    'Santa Helena Park Condominiums': 'Pankaj',
}

# Resolve sf_ids from name_lookup
print(f"Resolving SF Ids...")
for p in PLAN:
    if p['sf_id']:
        continue
    q = sf.query(f"SELECT Id, Name, StageName, Projected_Close_Date__c, Next_Action__c, Next_Action_Date__c, Hold_Reason__c, Sales_Status__c, OwnerId, Owner.Name FROM Opportunity WHERE {p['name_lookup']} AND IsClosed=false")
    if q['totalSize'] != 1:
        print(f"  ! {p['name_lookup']} -> {q['totalSize']} matches, skipping")
        p['sf_id'] = f'AMBIGUOUS_OR_MISSING ({q["totalSize"]})'
        continue
    r = q['records'][0]
    p['sf_id'] = r['Id']
    p['_current'] = {
        'Name': r['Name'],
        'StageName': r['StageName'],
        'Projected_Close_Date__c': r.get('Projected_Close_Date__c'),
        'Next_Action__c': r.get('Next_Action__c'),
        'Next_Action_Date__c': r.get('Next_Action_Date__c'),
        'Hold_Reason__c': r.get('Hold_Reason__c'),
        'Sales_Status__c': r.get('Sales_Status__c'),
        'OwnerId': r['OwnerId'],
        'Owner_Name': r['Owner']['Name'],
    }

# For pre-resolved sf_ids, also fetch current
for p in PLAN:
    if '_current' in p or 'AMBIGUOUS' in str(p['sf_id']):
        continue
    q = sf.query(f"SELECT Id, Name, StageName, Projected_Close_Date__c, Next_Action__c, Next_Action_Date__c, Hold_Reason__c, Sales_Status__c, OwnerId, Owner.Name FROM Opportunity WHERE Id='{p['sf_id']}'")
    r = q['records'][0]
    p['_current'] = {
        'Name': r['Name'],
        'StageName': r['StageName'],
        'Projected_Close_Date__c': r.get('Projected_Close_Date__c'),
        'Next_Action__c': r.get('Next_Action__c'),
        'Next_Action_Date__c': r.get('Next_Action_Date__c'),
        'Hold_Reason__c': r.get('Hold_Reason__c'),
        'Sales_Status__c': r.get('Sales_Status__c'),
        'OwnerId': r['OwnerId'],
        'Owner_Name': r['Owner']['Name'],
    }

# Augment changes: OwnerId reassignment + default Next_Action_Date
for p in PLAN:
    if '_current' not in p:
        continue
    cur_name = p['_current']['Name']
    cur_owner_id = p['_current']['OwnerId']

    tracker_owner = TRACKER_OWNERS_BY_SF_NAME.get(cur_name)
    if tracker_owner:
        target_user_id = TRACKER_OWNER_TO_USER.get(tracker_owner)
        if target_user_id and target_user_id != cur_owner_id:
            p['changes']['OwnerId'] = target_user_id

    # Default Next_Action_Date when we're updating Next_Action__c but didn't set a date
    if 'Next_Action__c' in p['changes'] and 'Next_Action_Date__c' not in p['changes']:
        p['changes']['Next_Action_Date__c'] = DEFAULT_NAD

# Print diff
print(f"\n{'='*180}")
print(f"PLANNED UPDATES ({len([p for p in PLAN if '_current' in p])} of {len(PLAN)})")
print('='*180)

# Build a User ID -> Name lookup so OwnerId diffs are readable
USER_NAME_BY_ID = {v: k for k, v in TRACKER_OWNER_TO_USER.items()}
USER_NAME_BY_ID['005WR00000CXEZyYAP'] = 'Brett Spivey (inactive)'
USER_NAME_BY_ID['005WR000003WJllYAG'] = 'Melissa Baker (inactive)'
USER_NAME_BY_ID['005WR00000DEU6oYAH'] = 'Bill Holick'
USER_NAME_BY_ID['005WR00000Ewjj3YAB'] = 'Brett Spivey'
USER_NAME_BY_ID['005WR000003CD6DYAW'] = 'Melissa Baker'
USER_NAME_BY_ID['005WR000008V4VoYAK'] = 'Niraj Patel'
USER_NAME_BY_ID['005Hs00000Eo9rcIAB'] = 'Pankaj Gulati'

def display_value(field, val):
    if val in (None, ''):
        return '<empty>'
    if field == 'OwnerId':
        return USER_NAME_BY_ID.get(val, val)
    return str(val)

diff_rows = []
for p in PLAN:
    if '_current' not in p:
        continue
    cur = p['_current']
    name = cur['Name']
    diffs = []
    for field, new_val in p['changes'].items():
        if new_val is None:
            continue
        old_val = cur.get(field)
        if str(old_val or '') != str(new_val):
            diffs.append((field, old_val, new_val))
    diff_rows.append((p, diffs))
    if diffs:
        print(f"\n[{cur['Owner_Name']:18s}] {name}")
        for field, old, new in diffs:
            old_disp = display_value(field, old)[:60]
            new_disp = display_value(field, new)[:80]
            print(f"  {field:30s}  {old_disp:50s}  ->  {new_disp}")

# Apply
if args.dry_run:
    print(f"\n--- DRY RUN. Re-run with --apply to execute. ---")
    sys.exit(0)

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'meeting_updates_2026-04-29_{ts}.csv'

success = 0
failed = []
notes_added = 0

with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Id', 'Name', 'Field', 'Before', 'After', 'Source', 'Timestamp', 'Action'])

    for p, diffs in diff_rows:
        oid = p['sf_id']
        cur = p['_current']
        # Build update payload (only changed fields)
        update_payload = {field: new for field, old, new in diffs}
        if not update_payload and not p.get('note_body'):
            continue
        try:
            if update_payload:
                sf.Opportunity.update(oid, update_payload)
                for field, old, new in diffs:
                    w.writerow([oid, cur['Name'], field, old or '', new, 'apply_meeting_updates_2026-04-29.py', ts, 'UPDATE'])
                success += 1
        except Exception as e:
            failed.append((oid, cur['Name'], str(e)))
            print(f"  FAIL UPDATE {cur['Name']}: {e}")
            continue

        # Create ContentNote
        if p.get('note_body'):
            try:
                cn = sf.ContentNote.create({'Title': NOTE_TITLE, 'Content': p['note_body'].encode('utf-8').hex()})  # ContentNote.Content is base64 of HTML normally
            except Exception:
                cn = None
            # ContentNote actually uses base64 of HTML for the body field on create. Use Files API:
            try:
                import base64
                html_body = p['note_body'].replace('\n', '<br/>')
                cv = sf.ContentVersion.create({
                    'Title': NOTE_TITLE,
                    'PathOnClient': f'{NOTE_TITLE}.snote',
                    'VersionData': base64.b64encode(html_body.encode('utf-8')).decode('utf-8'),
                    'FirstPublishLocationId': oid,
                })
                w.writerow([oid, cur['Name'], 'ContentNote', '', NOTE_TITLE, 'apply_meeting_updates_2026-04-29.py', ts, 'NOTE_CREATED'])
                notes_added += 1
            except Exception as e:
                # Fall back to simple ContentNote create + link
                print(f"  NOTE WARN {cur['Name']}: {e}")

print(f"\nUpdated: {success} / {len(diff_rows)}")
print(f"Notes added: {notes_added}")
print(f"Failed: {len(failed)}")
print(f"Audit log: {audit_path}")
