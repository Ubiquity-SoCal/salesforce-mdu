"""
Re-attempt the ContentNote attachments for the 4/29 meeting updates.
The earlier apply script failed all 33 because of UNSAFE_HTML_CONTENT.
Fix: html.escape() the body before substituting <br/> for newlines.
"""
import argparse, base64, csv, html, sys
from datetime import datetime
from pathlib import Path
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if not args.apply and not args.dry_run:
    print("Specify --dry-run or --apply"); sys.exit(1)

sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"],
)

NOTE_TITLE = '2026-04-29 MDU Pipeline Meeting'

# Same plan list as the apply script, just the (sf_id_lookup, note_body) pairs
NOTES = [
    ("Name='Eastgate Village Apartments'",
     "Eastgate update from 4/29 call.\n\nWent radio silent after PAL signed; owner Sean Darden wanted only $5,000 payment then stopped responding when W-9 was requested. Niraj had marked it frozen due to no contact.\n\nDecision: revive. Bill to coordinate with Angie (had original contact with owner) to reach back out. 3 buildings. Fiber + lid on side approach is viable. Texas deployment call tomorrow will surface this."),
    ("Name='Howard Street'",
     "Howard Street update from 4/29 call.\n\nOwner Kelly also owns Terrace Garden (both ~90 units in Omaha). She showed strong interest in Omaha market and wants a meeting this week. Worth a trip up. Only a couple-hour drive for Bill.\n\nMelissa to set up face-to-face. AJ flagged this and the Westmount cluster as the main multi-property owners worth in-person."),
    ("Name='Terrace Garden Apartments'",
     "Terrace Garden update from 4/29 call.\n\nOwner Kelly also owns Howard Street (both ~90 units in Omaha). Showed strong interest in Omaha market and wants a meeting this week.\n\nMelissa to set up face-to-face per Pankaj direction."),
    ("Name='Gardens of Taylor'",
     "Gardens of Taylor update from 4/29 call.\n\nOwner Linda provided legal description and required info for PAL request. Existing bulk agreement expires August. PAL request to be submitted today by Melissa, routed to Caitlin (Taylor on break) with Brett copied.\n\nGood call Monday with Linda; she's engaged."),
    ("Name='Capri on Camelback'",
     "Capri on Camelback update from 4/29 call.\n\nOwner repeatedly asking when construction starts. Niraj confirmed: this is a hut build, must have bulk. Brett's initial conversation: owner not interested in bulk. Brett to push that bulk is the only way forward.\n\nNote: stage was 'EMA/Bulk Complete' but the Bulk agreement record (AGR-1040) has Status='Completed' with no signed_date and no IronClad ID. That's likely Monday.com migration noise. Bulk was never actually signed. Stage moved back to Contract Negotiations to reflect reality."),
    ("Name='The Traditions Apartments'",
     "Traditions update from 4/29 call.\n\nAll 4 agreements signed in 2025 (PAL, EMA, PAL Addendum, MSA Addendum). Project was for AT&T/Lumen which has since changed. Pankaj direction: 'if we can't hold on to it anymore because of delays, let's be professional and inform them we are not moving forward.'\n\n160 units. Not in current footprint. Per Pankaj: cost of a hut for 160 units bulk deal. Probably not viable.\n\nMSA Addendum still needs to be canceled by AT&T side (hasn't happened). Niraj to coordinate with Caitlin on legal language for owner communication. Holding the PAL. May revisit as FiberFirst if a bulk emerges."),
    ("Name='Coyote Creek'",
     "Coyote Creek update from 4/29 call.\n\nAgreements (PAL + EMA) signed in 2025. Brett owns the follow-up with leadership and owner per tracker. Owner reassigned from Chuck McNeely (inactive) to Brett Spivey.\n\n116 units, Washington UT."),
    ("Name='Falcon Glen Apartments'",
     "Falcon Glen update from 4/29 call.\n\nOwner Linda Inabe lives in California. Pankaj suggested a CA visit if it would help advance the deal. Brett pitching to owner shortly."),
    ("Name='The Laredo Apartments'",
     "Laredo update from 4/29 call.\n\nJoe Anderson (former Fiberforce rep) is now pushing NextLink to our leads. He had the relationship with Laredo. Initial pitch was NextLink-only; team got them to accept our proposal.\n\nMelissa to schedule meeting with Brett and Amy. Strategy: aggressive bulk offer. Need their current pricing. Melissa to send to Brett offline.\n\nLocation: Decatur TX (~25 min from Melissa, North TX). 2-gig service is on the table. ~50% of April new adds in SFU were 2-gig."),
    ("Name='Woodglen Square ll'",
     "Wood Glen Square ll update from 4/29 call.\n\nPAL signed. Niraj waiting on data to start engineering. Taylor sent maps, floor plans, property maps on 4/29 (before going on break). Brett forwarding to Niraj. Address list still being compiled."),
    ("Name='La Mesa Village Apartments'",
     "La Mesa Village update from 4/29 call.\n\nMDU On Net status. Targeting Access Agreement in next 30 days."),
    ("Name='Garden Place Apartments'",
     "Garden Place update from 4/29 call.\n\nMDU On Net status. Targeting Access Agreement in next 30 days."),
    ("Name='Westmount at The District Apartments'",
     "Westmount at the District update from 4/29 call.\n\nWalker (primary contact) on paternity leave starting beginning of May. No out-of-office yet. Team is racing to get PAL signed before he disappears. Kyle reaching out to backup contact.\n\n154 units, Mesa."),
    ("Name='Westmount at Urban Trails'",
     "Westmount at Urban Trails update from 4/29 call.\n\nSame Walker contact as Westmount at the District (on paternity leave starting May). Trying to get PAL signed before he goes out. Kyle pursuing backup.\n\n159 units, Mesa."),
    ("Name='Amberwood Manor'",
     "Amberwood Manor update from 4/29 call.\n\nConfirmed on HOA agenda for May. Bill's team requested participation in May HOA meeting; awaiting response."),
    ("Name='Bridgewood Townhomes'",
     "Bridgewood Townhomes update from 4/29 call.\n\nSame HOA cluster as Amberwood Manor. Confirmed on HOA agenda for May. Awaiting response on participation request."),
    ("Name='4813-4823 Boyd St Apartments'",
     "4813-4823 Boyd St update from 4/29 call.\n\nDr. Kumar and partner have signed for us before. Hard to reach but reliable once they engage. Bill confident in close. Continuing outreach."),
    ("Name='6314 Boyd Street'",
     "Boyd Street Apartments update from 4/29 call.\n\nSame Dr. Kumar relationship as 4813-4823 Boyd. Hard to reach, reliable once engaged.\n\nNOTE: tracker says 'Boyd Street Apartments 26 units' which most likely matches this 6314 Boyd Street record. Verify if needed."),
    (None, "Liberty Manor update from 4/29 call.\n\nGood initial call, then radio silent. Stopped answering SITAC and Bill's calls. Bill flagged to Melissa to take over outreach (she was out for surgery last week, picking back up this week).\n\n36 units, Killeen TX.", '006WR00000wkABpYAM'),
    ("Name='Williamsburg Townhomes and Apartments'",
     "Williamsburg update from 4/29 call.\n\nGood text exchange with owner. Showing interest. PAL is in proposal review."),
    ("Name='Bedford Square [fmr Maplewood Court]'",
     "Bedford Square update from 4/29 call.\n\nFormerly Maplewood Court. Owner Belinda is interested. Taylor sent PAL directly to Belinda on 4/28 before going on break. Owner reviewing."),
    ("Name='Parkwood Apartments'",
     "Parkwood Apartments (Mineral Wells) update from 4/29 call.\n\nStill under discussion with owner. No new movement reported."),
    ("Name='Creekside Apartments'",
     "Creekside Apartments update from 4/29 call.\n\nGoing bulk; agreement already in place. Waiting on PAL addendum. Melissa to call owner. Unclear what's holding it up."),
    ("Name='Patriot Place'",
     "Patriot Place update from 4/29 call.\n\nMelissa's last conversation: going bulk. Owner ready to send EMA contracts if EMA. Decision needed before build. Melissa to solidify bulk vs EMA by EOD 4/30.\n\nNiraj noted this is a PAL property. In-unit work, more involved engineering than typical ROE. Wants to keep momentum while owner is engaged."),
    ("Name='Heritage of Newark (FKA Newark Beach Estates)'",
     "Heritage of Newark update from 4/29 call.\n\nMelissa explained to Chris that we're not paying attorney fees. That conversation went well. They are going bulk. Some bulk agreement language needs to be changed (Chris had been talking directly to Taylor). Waiting for Taylor back from break Monday 5/4."),
    ("Name='The 1001 Apartments'",
     "1001 Apartments update from 4/29 call.\n\nOwner Bob is sitting on the decision. No movement. Melissa to reach back out.\n\n111 units, Omaha."),
    ("Name='Bristol Square Apartments'",
     "Bristol Square update from 4/29 call.\n\n184 units. High priority per Pankaj. Owner wants equipment in closet but there's no power. Team agreed to install fiber jack without equipment if marketing rights are secured. Email back-and-forth with Chuck caused confusion. Owner uncertain.\n\nFix: Melissa to set up meeting with Brett (and possibly Niraj) to walk through the approach in person. Bringing power into the closet is too costly for the owner."),
    ("Name='Northampton Court Condominiums'",
     "Northampton Courts update from 4/29 call.\n\nMelissa got owner to sign PAL. Owner called last week with a few questions about bulk; said he'd have it signed by end of this week. That's a verbal on bulk. Melissa to reach out today to confirm."),
    ("Name='Killeen_MDU_The Bungalows'",
     "The Bungalows update from 4/29 call.\n\nOwner Lisa Jean is unreachable. Project on hold pending her construction activities. Niraj waiting to confirm whether NID can go on the side of the property. Feet-on-ground stop-bys haven't reached anyone."),
    ("Name='Sonterra Apartment Homes'",
     "Sonterra Apartment Homes update from 4/29 call.\n\nEMA sent for signature last week. Owner Manny and both daughters are in agreement; they asked for only 48 hours to review the EMA verbiage. Melissa was out last week for surgery, will follow up today.\n\nOwner reassigned from Brett Spivey to Melissa Baker per tracker."),
    ("Name='Sandpiper Pointe'",
     "Sandpiper Pointe update from 4/29 call.\n\nPrivate road, single-family / townhome-style homes selling for $3M+/unit. No wireless coverage. Desperately need fiber.\n\nBoard had two attorneys, expected a PAL (one was sent ~2 years ago by Jeff Chao, since expired). Pankaj direction: ROE is fine since they're SFU and we don't go in-unit. ROE shorter, faster.\n\nBulk: only 50% of board agreed; preference is EMA until deployment proves successful, then revisit bulk. We have a verbal on EMA.\n\nMelissa sending ROE today with all addresses in the addendum.\n\nOwner reassigned from Jeff Chao (inactive) to Melissa Baker per tracker."),
    ("Name='Seascape Sur'",
     "Seascape Sur update from 4/29 call.\n\nPam Walker reached out 4/28 with PAL questions. Pankaj sent revised PAL with insurance and ISP boundaries. Telecom consultant on owner's side asking ISP questions. Answered.\n\nPAL expected to land in 45-60 days. Difficult and expensive build (multiple sections, custom per part). Without bulk, build not feasible. Pankaj will slow-track if bulk doesn't materialize.\n\nMelissa offered marketing help; Pankaj said hold until PAL signed."),
    ("Name='Santa Helena Park Condominiums'",
     "Santa Helena Park update from 4/29 call.\n\nSister property to Seascape Sur (both Solana Beach, Pam Walker contact, same telecom consultant). PAL under revision; questions being answered."),
]

# Resolve sf_ids
resolved = []
for entry in NOTES:
    if len(entry) == 3:
        name_lookup, body, fixed_id = entry
        resolved.append((fixed_id, body, fixed_id))
        continue
    name_lookup, body = entry
    q = sf.query(f"SELECT Id, Name FROM Opportunity WHERE {name_lookup}")
    if q['totalSize'] != 1:
        print(f"  ! {name_lookup} -> {q['totalSize']} matches, skipping")
        continue
    resolved.append((q['records'][0]['Id'], body, q['records'][0]['Name']))

print(f"Resolved {len(resolved)} notes to attach.")

if args.dry_run:
    print("\nFirst 3 escaped HTML previews:")
    for oid, body, name in resolved[:3]:
        escaped = html.escape(body).replace('\n', '<br/>')
        print(f"\n--- {name} ({oid}) ---")
        print(escaped[:300])
    sys.exit(0)

ts = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
audit_dir = Path('audit_logs')
audit_dir.mkdir(exist_ok=True)
audit_path = audit_dir / f'meeting_notes_2026-04-29_{ts}.csv'

success = 0
failed = []
with audit_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['SF_Opp_Id', 'Opp_Name', 'ContentNote_Title', 'ContentNote_Id', 'Source', 'Timestamp', 'Action'])
    for oid, body, name in resolved:
        try:
            # ContentNote.Content expects base64 of HTML; <br> is permitted (no slash)
            html_body = html.escape(body).replace('\n', '<br>')
            content_b64 = base64.b64encode(html_body.encode('utf-8')).decode('utf-8')
            note = sf.ContentNote.create({
                'Title': NOTE_TITLE,
                'Content': content_b64,
            })
            note_id = note['id']
            sf.ContentDocumentLink.create({
                'ContentDocumentId': note_id,
                'LinkedEntityId': oid,
                'ShareType': 'V',
                'Visibility': 'AllUsers',
            })
            w.writerow([oid, name, NOTE_TITLE, note_id, 'attach_meeting_notes_2026-04-29.py', ts, 'NOTE_CREATED'])
            success += 1
        except Exception as e:
            failed.append((oid, name, str(e)))
            print(f"  FAIL {name}: {str(e)[:200]}")

print(f"\nNotes attached: {success}")
print(f"Failed: {len(failed)}")
print(f"Audit log: {audit_path}")
