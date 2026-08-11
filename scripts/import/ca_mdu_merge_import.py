"""
CA MDU Agreement Status + Opportunities_Market -> Salesforce (LIVE IMPORT)

Usage:
  python ca_mdu_merge_import.py --dry-run   # Simulate (no writes)
  python ca_mdu_merge_import.py             # Live push

What it does:
  1. Dedup 3 known duplicate pairs (copy loser -> keeper, delete loser)
  2. Create 3 new Opps (Fox Point, Sand Piper Point, Ito San)
  3. Update 104 existing Opps:
       - Pipeline_Bucket__c (new field)
       - StageName per bucket mapping (PAL exception: keep Under Contract)
       - Property_Classification__c (MDU / SFU / MHP from CA MDU file)
       - OwnerId = Justin Barry
       - Combined ContentNote attached
       - Agreement__c child created if ROE/PAL present or bucket says signed
       - Never overwrites Name (name-cleanup protection)

Safe: --dry-run walks every record and logs exactly what WOULD happen without writing.
"""

import sys
import os
import json
import re
from datetime import datetime, date
from collections import Counter
import pandas as pd
from simple_salesforce import Salesforce

# Reuse helpers from the preview script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ca_mdu_merge_preview import (
    CA_MDU_XLSX, RE_XLSX,
    JUSTIN_BARRY_ID, MDU_RECORD_TYPE_ID, SFU_RECORD_TYPE_ID,
    BUCKET_TO_STAGE, ALL_BUCKETS,
    norm, norm_name, norm_addr, first_token, excel_date, clean,
    load_ca_mdu, load_market, match_ca_to_market, match_to_sf,
)

# Salesforce config -- read from the gitignored SalesForce/api/ creds file.
# Never hardcode the password here: this file is tracked in git.
def _sf_creds():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "..", "api", "Salesforce_Credentials.txt")
    _c = {}
    with open(_p) as _f:
        for _line in _f:
            if ":" in _line:
                _k, _v = _line.split(":", 1)
                _c[_k.strip()] = _v.strip()
    return _c


_SF = _sf_creds()
SF_USERNAME = _SF["Username"]
SF_PASSWORD = _SF["Password"]
SF_TOKEN = _SF["Security Token"]

DRY_RUN = "--dry-run" in sys.argv

LOG_DIR = r"C:\Users\cass\Work_Projects\SalesForce\CA_MDU_Merge"
os.makedirs(LOG_DIR, exist_ok=True)

# Dedup plan: keep first Id, delete second Id (copy non-null fields from loser onto keeper first)
DEDUP_PAIRS = [
    {"label": "Beach Street Encinitas",
     "keeper": "006WR00000yuqW4YAI",
     "loser":  "006WR00000ywI25YAE"},
    {"label": "Beacons Beach Village",
     "keeper": "006WR00000yw09zYAA",
     "loser":  "006WR00000wkCknYAE"},
    {"label": "Park Encinitas Mobile Homes",
     "keeper": "006WR00000wkCmJYAU",
     "loser":  "006WR00000yv4h6YAA"},
]

# Fields to copy loser -> keeper if keeper is null
DEDUP_COPY_FIELDS = [
    "Property_Type__c", "Property_Classification__c",
    "Agreement_Name__c", "Property_Address__c",
    "Property_City__c", "Property_Zip__c", "Property_State__c",
    "Units__c", "Management_Company__c",
]

# Normalize legacy/invalid picklist values before writing
PROPERTY_TYPE_FIXUPS = {
    "Condo": "Condos",
    "Condominium": "Condos",
    "Manufactured Home Park": "Manufactured Homes / Mobile Homes",
    "Mobile Home Park": "Manufactured Homes / Mobile Homes",
    "MDU": None,  # not a valid Property_Type value — skip
    "SFU": None,  # same
    "MHP": None,
    "HOA": None,
}


# ── CA MDU Property Type -> SF Property_Classification__c ───────────────────
def classify_prop(pt):
    pt = (pt or "").strip().upper()
    if pt == "MDU": return "MDU"
    if pt == "SFU": return "SFU"
    if pt == "HOA": return "SFU"  # HOA are SFU-equivalent per Koa 2026-04-21
    if "MOBILE" in pt or pt == "MHP": return "MHP"
    return None


# ── ROE/PAL parsing ─────────────────────────────────────────────────────────
def parse_agreement(ca):
    """Return (agreement_type, is_pal_only). PAL-only rows get stage exception."""
    rp = (ca.get("ROE_PAL") or "").upper()
    if not rp:
        # Infer from bucket for Access Agreement Complete
        if "Access Agreement Complete" in (ca.get("Bucket") or ""):
            return "ROE", False
        if ca["Source"] == "On Air":
            return "ROE", False
        return None, False
    if "PAL" in rp and "ROE" not in rp:
        return "PAL", True
    if "ROE" in rp:
        return "ROE", False
    if "PAL" in rp:
        return "PAL", False
    return None, False


# ── Note builder ────────────────────────────────────────────────────────────
def build_note_body(ca, mkt):
    parts = []
    parts.append(f"Source: CA MDU Agreement Status ({ca['Source']}) + Opportunities_Market — imported 2026-04-21")
    parts.append(f"CA Pipeline Bucket: {ca.get('Bucket') or '(none)'}")
    if ca.get("OnNet"): parts.append(f"On Net: {ca['OnNet']}")
    if ca.get("ISPTenant"): parts.append(f"ISP Tenant: {ca['ISPTenant']}")
    if ca.get("ROE_PAL"): parts.append(f"Agreement (CA MDU col): {ca['ROE_PAL']}")
    if ca.get("Program"): parts.append(f"Program/City: {ca['Program']}")
    if ca.get("PropertyType"): parts.append(f"Property Type (CA MDU): {ca['PropertyType']}")
    if mkt:
        parts.append("")
        parts.append("— From Opportunities Market —")
        if mkt.get("UniqueID"):       parts.append(f"Market UniqueID: {mkt['UniqueID']}")
        if mkt.get("Status"):         parts.append(f"Market Status: {mkt['Status']}")
        if mkt.get("RE_Assigned"):    parts.append(f"RE Assigned: {mkt['RE_Assigned']}")
        if mkt.get("Contacts"):       parts.append(f"Contacts: {mkt['Contacts']}")
        if mkt.get("PALSignedDate"):  parts.append(f"PAL Signed Date: {mkt['PALSignedDate']}")
        if mkt.get("SiteWalk"):       parts.append(f"Site Walk: {mkt['SiteWalk']}")
        if mkt.get("SiteTrackerLink"):parts.append(f"SiteTracker: {mkt['SiteTrackerLink']}")
        if mkt.get("EstimateLink"):   parts.append(f"Estimate Link: {mkt['EstimateLink']}")
        if mkt.get("CXEstimate"):     parts.append(f"CX Estimate: {mkt['CXEstimate']}")
        if mkt.get("CXNotes"):        parts.append(f"CX Notes: {mkt['CXNotes']}")
        if mkt.get("FDHActivated"):   parts.append(f"FDH Activated: {mkt['FDHActivated']}")
        if mkt.get("VetroStatus"):    parts.append(f"Vetro Status: {mkt['VetroStatus']}")
        if mkt.get("Comments"):
            parts.append("")
            parts.append("Comments:")
            parts.append(mkt["Comments"])
    return "\n".join(parts)


# ── ContentNote attach helper ───────────────────────────────────────────────
def attach_note(sf, opp_id, title, body, dry_run=False):
    """Create a ContentNote and link it to the Opportunity."""
    import base64
    if dry_run:
        return f"DRY: would attach note '{title}' ({len(body)} chars)"
    # ContentNote.Content must be base64-encoded HTML
    html_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    encoded = base64.b64encode(html_body.encode("utf-8")).decode("utf-8")
    note = sf.ContentNote.create({
        "Title": title[:200],
        "Content": encoded,
    })
    sf.ContentDocumentLink.create({
        "ContentDocumentId": note["id"],
        "LinkedEntityId": opp_id,
        "ShareType": "V",
        "Visibility": "AllUsers",
    })
    return f"attached note {note['id']}"


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print("=" * 70)
    print(f"CA MDU + Market Merge -> Salesforce  [{mode}]")
    print("=" * 70)

    # Load input data
    print("\n1. Loading input files...")
    ca_rows = load_ca_mdu()
    market_rows = load_market()
    print(f"   CA MDU: {len(ca_rows)} rows, Market: {len(market_rows)} rows")

    print("\n2. Matching CA MDU -> market...")
    ca_to_market = match_ca_to_market(ca_rows, market_rows)

    print("\n3. Connecting to Salesforce...")
    sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)

    # Verify Pipeline_Bucket__c exists
    desc = sf.Opportunity.describe()
    if not any(f["name"] == "Pipeline_Bucket__c" for f in desc["fields"]):
        print("[FATAL] Pipeline_Bucket__c not found on Opportunity. Run create_pipeline_bucket_field.py first.")
        sys.exit(1)

    # Pull existing CA-area Opps
    print("\n4. Pulling existing CA-area Opps...")
    q = sf.query_all("""
        SELECT Id, Name, StageName, Property_Address__c, Property_City__c,
               Property_State__c, Property_Classification__c, Property_Type__c,
               Agreement_Name__c, OwnerId, RecordType.DeveloperName, Pipeline_Bucket__c
        FROM Opportunity
        WHERE RecordType.DeveloperName IN ('MDU','SFU')
          AND (Property_State__c = 'CA'
               OR Property_City__c IN ('Carlsbad','Encinitas','Oceanside','Solana Beach'))
    """)
    sf_opps = q["records"]
    print(f"   {len(sf_opps)} existing Opps loaded")

    # ── STEP A: DEDUP ───────────────────────────────────────────────────────
    print(f"\n5. Dedup {len(DEDUP_PAIRS)} duplicate pairs...")
    dedup_log = []
    for pair in DEDUP_PAIRS:
        print(f"   [{pair['label']}]")

        # Keeper must exist
        try:
            keeper = sf.Opportunity.get(pair["keeper"])
        except Exception as e:
            print(f"     [SKIP] Keeper {pair['keeper']} not found: {e}")
            continue

        # Loser may already be gone from a prior partial run
        try:
            loser = sf.Opportunity.get(pair["loser"])
        except Exception:
            print(f"     [SKIP] Loser {pair['loser']} not found — already deduped.")
            dedup_log.append({"pair": pair["label"], "keeper": keeper["Id"], "loser_deleted": pair["loser"], "fields_copied": {}, "status": "already_done"})
            continue

        print(f"     Keeper: {keeper['Name']!r} ({keeper['Id']}) Stage={keeper['StageName']}")
        print(f"     Loser:  {loser['Name']!r} ({loser['Id']}) Stage={loser['StageName']}")

        # Decide what to copy loser -> keeper
        updates = {}
        for fname in DEDUP_COPY_FIELDS:
            if keeper.get(fname) in (None, "") and loser.get(fname) not in (None, ""):
                val = loser[fname]
                if fname == "Property_Type__c" and val in PROPERTY_TYPE_FIXUPS:
                    val = PROPERTY_TYPE_FIXUPS[val]
                    if val is None:
                        print(f"     SKIP invalid Property_Type__c: {loser[fname]!r}")
                        continue
                updates[fname] = val

        # Reparent Agreement__c children from loser to keeper
        agreements = sf.query(f"SELECT Id, Name FROM Agreement__c WHERE Opportunity__c='{loser['Id']}'")
        if agreements["totalSize"] > 0:
            print(f"     Reparenting {agreements['totalSize']} Agreement__c children")
            for ag in agreements["records"]:
                if not DRY_RUN:
                    sf.Agreement__c.update(ag["Id"], {"Opportunity__c": keeper["Id"]})

        # Relink ContentDocumentLinks
        notes = sf.query(f"SELECT Id, ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId='{loser['Id']}'")
        if notes["totalSize"] > 0:
            print(f"     {notes['totalSize']} ContentDocumentLinks on loser (relinking to keeper)")
            for n in notes["records"]:
                if not DRY_RUN:
                    try:
                        sf.ContentDocumentLink.create({
                            "ContentDocumentId": n["ContentDocumentId"],
                            "LinkedEntityId": keeper["Id"],
                            "ShareType": "V", "Visibility": "AllUsers",
                        })
                    except Exception as e:
                        msg = str(e)
                        if "DUPLICATE" in msg.upper():
                            pass  # already linked, fine
                        else:
                            print(f"       (relink skip) {e}")

        # DELETE LOSER FIRST — frees unique fields like Agreement_Name__c
        print(f"     Deleting loser {loser['Id']}")
        if not DRY_RUN:
            sf.Opportunity.delete(loser["Id"])

        # NOW copy fields onto keeper
        if updates:
            print(f"     Copying fields onto keeper: {updates}")
            if not DRY_RUN:
                sf.Opportunity.update(keeper["Id"], updates)

        dedup_log.append({"pair": pair["label"], "keeper": keeper["Id"], "loser_deleted": loser["Id"], "fields_copied": updates})

    # Reload SF Opps after dedup so matching uses current state
    if not DRY_RUN and DEDUP_PAIRS:
        print("\n6. Reloading SF Opps after dedup...")
        q = sf.query_all("""
            SELECT Id, Name, StageName, Property_Address__c, Property_City__c,
                   Property_State__c, Property_Classification__c, Property_Type__c,
                   Agreement_Name__c, OwnerId, RecordType.DeveloperName, Pipeline_Bucket__c
            FROM Opportunity
            WHERE RecordType.DeveloperName IN ('MDU','SFU')
              AND (Property_State__c = 'CA'
                   OR Property_City__c IN ('Carlsbad','Encinitas','Oceanside','Solana Beach'))
        """)
        sf_opps = q["records"]

    # ── STEP B: MATCH ───────────────────────────────────────────────────────
    print(f"\n7. Matching CA MDU rows to SF Opps...")
    sf_matches = match_to_sf(ca_rows, market_rows, ca_to_market, sf_opps)
    upd_cnt = sum(1 for m in sf_matches if m is not None)
    new_cnt = len(ca_rows) - upd_cnt
    print(f"   UPDATE: {upd_cnt}   CREATE: {new_cnt}")

    # ── STEP C: APPLY CHANGES ──────────────────────────────────────────────
    print(f"\n8. Applying updates ({mode})...")
    stats = Counter()
    actions_log = []

    for i, ca in enumerate(ca_rows):
        mkt = market_rows[ca_to_market[i]] if ca_to_market[i] is not None else None
        sf_opp = sf_matches[i]

        bucket = ca.get("Bucket") or ""
        mapped_stage = BUCKET_TO_STAGE.get(bucket, "")
        if not mapped_stage and ca["Source"] == "On Air":
            mapped_stage = "ROE Secured"

        agreement_type, is_pal_only = parse_agreement(ca)
        classification = classify_prop(ca.get("PropertyType"))

        # PAL exception: keep SF's current stage on existing records
        use_pal_exception = is_pal_only and sf_opp and sf_opp.get("StageName")
        final_stage = sf_opp["StageName"] if use_pal_exception else mapped_stage

        # Signed date
        signed_date = mkt.get("PALSignedDate") if mkt else None

        if sf_opp:
            # UPDATE path
            opp_updates = {
                "OwnerId": JUSTIN_BARRY_ID,
                "Pipeline_Bucket__c": bucket,
            }
            if final_stage and final_stage != sf_opp.get("StageName"):
                opp_updates["StageName"] = final_stage
            if classification and classification != sf_opp.get("Property_Classification__c"):
                opp_updates["Property_Classification__c"] = classification

            label = f"[UPD] {ca['Name'][:40]:40}"
            if DRY_RUN:
                print(f"   {label}  -> {opp_updates}")
            else:
                try:
                    sf.Opportunity.update(sf_opp["Id"], opp_updates)
                    stats["updated"] += 1
                except Exception as e:
                    print(f"   [FAIL UPD] {ca['Name']}: {e}")
                    stats["update_errors"] += 1
                    actions_log.append({"action":"update_error","ca_name":ca["Name"],"error":str(e)})
                    continue

            # Agreement__c: create if not exists
            if agreement_type:
                existing_agrees = sf.query(
                    f"SELECT Id FROM Agreement__c WHERE Opportunity__c='{sf_opp['Id']}' "
                    f"AND Agreement_Type__c='{agreement_type}'"
                )
                if existing_agrees["totalSize"] == 0:
                    ag_data = {
                        "Opportunity__c": sf_opp["Id"],
                        "Agreement_Type__c": agreement_type,
                        "Status__c": "Completed" if signed_date or ca["Source"] == "On Air" else "Sign",
                    }
                    if signed_date:
                        ag_data["Signed_Date__c"] = signed_date
                    if DRY_RUN:
                        print(f"     AGREEMENT: would create {agreement_type}  signed={signed_date}")
                    else:
                        try:
                            sf.Agreement__c.create(ag_data)
                            stats["agreements_created"] += 1
                        except Exception as e:
                            print(f"   [FAIL AGREE] {ca['Name']}: {e}")
                            stats["agreement_errors"] += 1

            # Combined Note
            note_body = build_note_body(ca, mkt)
            note_title = f"CA MDU Merge Import 2026-04-21 - {ca['Name'][:100]}"
            if DRY_RUN:
                print(f"     NOTE: would attach '{note_title[:60]}...' ({len(note_body)} chars)")
            else:
                try:
                    attach_note(sf, sf_opp["Id"], note_title, note_body)
                    stats["notes_attached"] += 1
                except Exception as e:
                    print(f"   [FAIL NOTE] {ca['Name']}: {e}")
                    stats["note_errors"] += 1

            actions_log.append({
                "action": "update", "sf_id": sf_opp["Id"],
                "ca_name": ca["Name"], "updates": opp_updates,
                "agreement": agreement_type, "signed_date": signed_date,
            })

        else:
            # CREATE path — new Opp
            name = ca["Name"][:120]
            new_opp = {
                "Name": name,
                "RecordTypeId": MDU_RECORD_TYPE_ID,  # default; SFU classification lives in Property_Classification__c
                "StageName": mapped_stage or "Prospecting",
                "OwnerId": JUSTIN_BARRY_ID,
                "Pipeline_Bucket__c": bucket,
                "Property_Address__c": ca["Address"][:255],
                "Property_City__c": (ca.get("Program") or "")[:40],
                "Property_State__c": "CA",
                "CloseDate": f"{date.today().year}-12-31",
            }
            if classification:
                new_opp["Property_Classification__c"] = classification
            try:
                units_val = ca.get("Units")
                if units_val not in (None, ""):
                    new_opp["Units__c"] = int(float(units_val))
            except (ValueError, TypeError):
                pass

            label = f"[NEW] {ca['Name'][:40]:40}"
            if DRY_RUN:
                print(f"   {label}  -> {new_opp}")
                new_id = "DRY-RUN-ID"
            else:
                try:
                    result = sf.Opportunity.create(new_opp)
                    new_id = result["id"]
                    stats["created"] += 1
                except Exception as e:
                    print(f"   [FAIL NEW] {ca['Name']}: {e}")
                    stats["create_errors"] += 1
                    actions_log.append({"action":"create_error","ca_name":ca["Name"],"error":str(e)})
                    continue

            if agreement_type:
                ag_data = {
                    "Opportunity__c": new_id,
                    "Agreement_Type__c": agreement_type,
                    "Status__c": "Completed" if signed_date or ca["Source"] == "On Air" else "Sign",
                }
                if signed_date:
                    ag_data["Signed_Date__c"] = signed_date
                if DRY_RUN:
                    print(f"     AGREEMENT: would create {agreement_type}")
                else:
                    try:
                        sf.Agreement__c.create(ag_data)
                        stats["agreements_created"] += 1
                    except Exception as e:
                        print(f"   [FAIL AGREE] {ca['Name']}: {e}")

            note_body = build_note_body(ca, mkt)
            note_title = f"CA MDU Merge Import 2026-04-21 - {name}"
            if DRY_RUN:
                print(f"     NOTE: would attach '{note_title[:60]}...' ({len(note_body)} chars)")
            else:
                try:
                    attach_note(sf, new_id, note_title, note_body)
                    stats["notes_attached"] += 1
                except Exception as e:
                    print(f"   [FAIL NOTE] {ca['Name']}: {e}")

            actions_log.append({
                "action": "create", "sf_id": new_id,
                "ca_name": ca["Name"], "opp": new_opp,
                "agreement": agreement_type, "signed_date": signed_date,
            })

    # Save log
    log_path = os.path.join(LOG_DIR, f"import_log_{'dry' if DRY_RUN else 'live'}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({"dedup": dedup_log, "actions": actions_log, "stats": dict(stats), "mode": mode, "ts": datetime.now().isoformat()}, f, indent=2, default=str)
    print(f"\n[OK] Log written to: {log_path}")

    print("\n" + "=" * 70)
    print(f"DONE [{mode}]")
    print("=" * 70)
    for k, v in stats.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
