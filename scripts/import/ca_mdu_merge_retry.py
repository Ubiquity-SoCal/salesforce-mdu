"""
CA MDU Merge — Retry failed + HOA__c + Sales_Status__c backfill

Run AFTER ca_mdu_merge_import.py. This script:
  1. Retries the 22 records that failed due to Sales_Status__c validation rule
     (adds Sales_Status__c='Contact Pending' + HOA__c as appropriate)
  2. Backfills HOA__c=True on the 85 successful records where source was HOA
  3. Creates notes + agreements ONLY for the previously-failed records
     (successful records already have them)

Usage:
  python ca_mdu_merge_retry.py --dry-run
  python ca_mdu_merge_retry.py
"""

import sys
import os
import json
from datetime import date
from collections import Counter
from simple_salesforce import Salesforce

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ca_mdu_merge_preview import (
    load_ca_mdu, load_market, match_ca_to_market, match_to_sf,
    norm_name,
)
from ca_mdu_merge_import import (
    SF_USERNAME, SF_PASSWORD, SF_TOKEN,
    JUSTIN_BARRY_ID, MDU_RECORD_TYPE_ID,
    BUCKET_TO_STAGE, parse_agreement, classify_prop,
    build_note_body, attach_note,
)

DRY_RUN = "--dry-run" in sys.argv
LIVE_LOG = r"C:\Users\cass\Work_Projects\SalesForce\CA_MDU_Merge\import_log_live.json"
OUT_LOG  = r"C:\Users\cass\Work_Projects\SalesForce\CA_MDU_Merge\retry_log.json"
DEFAULT_SALES_STATUS = "Contact Pending"


def is_hoa(mkt, ca):
    """Identify HOA properties: market sheet Property Type was HOA, or name contains HOA."""
    if mkt:
        pt = str(mkt.get("PropertyType") or "").strip().upper()
        if pt == "HOA":
            return True
        if "HOA" in (mkt.get("Name") or "").upper():
            return True
    # CA MDU file: rare, but check name too
    if "HOA" in (ca.get("Name") or "").upper():
        return True
    return False


def main():
    mode = "DRY RUN" if DRY_RUN else "LIVE"
    print("=" * 70)
    print(f"CA MDU Merge — Retry + HOA Backfill  [{mode}]")
    print("=" * 70)

    # Load failed log
    with open(LIVE_LOG, "r", encoding="utf-8") as f:
        live_log = json.load(f)

    failed_names = {a["ca_name"] for a in live_log["actions"] if a["action"] in ("update_error", "create_error")}
    succeeded = {a["ca_name"] for a in live_log["actions"] if a["action"] in ("update", "create")}
    print(f"\nFailed rows: {len(failed_names)}")
    print(f"Succeeded rows: {len(succeeded)}")

    # Reload input + matches
    print("\n1. Re-matching source data...")
    ca_rows = load_ca_mdu()
    market_rows = load_market()
    ca_to_market = match_ca_to_market(ca_rows, market_rows)

    print("\n2. Connecting to Salesforce...")
    sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)

    print("\n3. Pulling current SF state (post-import)...")
    q = sf.query_all("""
        SELECT Id, Name, StageName, Property_Address__c, Property_City__c,
               Property_State__c, Property_Classification__c,
               Agreement_Name__c, OwnerId, RecordType.DeveloperName,
               Pipeline_Bucket__c, Sales_Status__c, HOA__c
        FROM Opportunity
        WHERE RecordType.DeveloperName IN ('MDU','SFU')
          AND (Property_State__c='CA'
               OR Property_City__c IN ('Carlsbad','Encinitas','Oceanside','Solana Beach'))
    """)
    sf_opps = q["records"]
    sf_matches = match_to_sf(ca_rows, market_rows, ca_to_market, sf_opps)

    print("\n4. Processing rows...")
    stats = Counter()
    log_entries = []

    for i, ca in enumerate(ca_rows):
        mkt = market_rows[ca_to_market[i]] if ca_to_market[i] is not None else None
        sf_opp = sf_matches[i]
        hoa_flag = is_hoa(mkt, ca)
        is_failed = ca["Name"] in failed_names

        if not is_failed and not hoa_flag:
            continue  # Already done, not HOA — skip

        if is_failed:
            # Full retry with fixed fields
            bucket = ca.get("Bucket") or ""
            mapped_stage = BUCKET_TO_STAGE.get(bucket, "")
            if not mapped_stage and ca["Source"] == "On Air":
                mapped_stage = "ROE Secured"
            agreement_type, is_pal_only = parse_agreement(ca)
            classification = classify_prop(ca.get("PropertyType"))
            use_pal_exception = is_pal_only and sf_opp and sf_opp.get("StageName")
            final_stage = sf_opp["StageName"] if use_pal_exception else mapped_stage
            signed_date = mkt.get("PALSignedDate") if mkt else None

            if sf_opp:
                # UPDATE retry
                updates = {
                    "OwnerId": JUSTIN_BARRY_ID,
                    "Pipeline_Bucket__c": bucket,
                    "HOA__c": hoa_flag,
                }
                if final_stage and final_stage != sf_opp.get("StageName"):
                    updates["StageName"] = final_stage
                if classification and classification != sf_opp.get("Property_Classification__c"):
                    updates["Property_Classification__c"] = classification
                # Add Sales_Status__c if going to Prospecting
                if updates.get("StageName") == "Prospecting" and not sf_opp.get("Sales_Status__c"):
                    updates["Sales_Status__c"] = DEFAULT_SALES_STATUS

                print(f"   [RETRY UPD] {ca['Name'][:40]:40}  -> {updates}")
                if not DRY_RUN:
                    try:
                        sf.Opportunity.update(sf_opp["Id"], updates)
                        stats["retry_updated"] += 1
                    except Exception as e:
                        print(f"     [FAIL] {e}")
                        stats["retry_update_errors"] += 1
                        log_entries.append({"action":"retry_update_error","ca_name":ca["Name"],"error":str(e)})
                        continue

                # Agreement
                if agreement_type:
                    existing = sf.query(f"SELECT Id FROM Agreement__c WHERE Opportunity__c='{sf_opp['Id']}' AND Agreement_Type__c='{agreement_type}'")
                    if existing["totalSize"] == 0:
                        ag = {"Opportunity__c": sf_opp["Id"], "Agreement_Type__c": agreement_type,
                              "Status__c": "Completed" if (signed_date or ca["Source"]=="On Air") else "Sign"}
                        if signed_date: ag["Signed_Date__c"] = signed_date
                        print(f"     AGREEMENT: create {agreement_type}")
                        if not DRY_RUN:
                            try:
                                sf.Agreement__c.create(ag); stats["agreements_created"] += 1
                            except Exception as e:
                                print(f"     [FAIL AGREE] {e}")

                # Note
                note_body = build_note_body(ca, mkt)
                note_title = f"CA MDU Merge Import 2026-04-21 - {ca['Name'][:100]}"
                print(f"     NOTE: attach ({len(note_body)} chars)")
                if not DRY_RUN:
                    try:
                        attach_note(sf, sf_opp["Id"], note_title, note_body); stats["notes_attached"] += 1
                    except Exception as e:
                        print(f"     [FAIL NOTE] {e}")

                log_entries.append({"action":"retry_update","ca_name":ca["Name"],"sf_id":sf_opp["Id"],"updates":updates,"hoa":hoa_flag})

            else:
                # CREATE retry
                new_opp = {
                    "Name": ca["Name"][:120],
                    "RecordTypeId": MDU_RECORD_TYPE_ID,
                    "StageName": mapped_stage or "Prospecting",
                    "OwnerId": JUSTIN_BARRY_ID,
                    "Pipeline_Bucket__c": bucket,
                    "Property_Address__c": ca["Address"][:255],
                    "Property_City__c": (ca.get("Program") or "")[:40],
                    "Property_State__c": "CA",
                    "CloseDate": f"{date.today().year}-12-31",
                    "HOA__c": hoa_flag,
                }
                if new_opp["StageName"] == "Prospecting":
                    new_opp["Sales_Status__c"] = DEFAULT_SALES_STATUS
                if classification:
                    new_opp["Property_Classification__c"] = classification
                try:
                    units = ca.get("Units")
                    if units not in (None, ""):
                        new_opp["Units__c"] = int(float(units))
                except (ValueError, TypeError):
                    pass

                print(f"   [RETRY NEW] {ca['Name'][:40]:40}  -> {new_opp}")
                if DRY_RUN:
                    new_id = "DRY-RUN-ID"
                else:
                    try:
                        result = sf.Opportunity.create(new_opp)
                        new_id = result["id"]; stats["retry_created"] += 1
                    except Exception as e:
                        print(f"     [FAIL] {e}")
                        stats["retry_create_errors"] += 1
                        log_entries.append({"action":"retry_create_error","ca_name":ca["Name"],"error":str(e)})
                        continue

                if agreement_type:
                    ag = {"Opportunity__c": new_id, "Agreement_Type__c": agreement_type,
                          "Status__c": "Completed" if (signed_date or ca["Source"]=="On Air") else "Sign"}
                    if signed_date: ag["Signed_Date__c"] = signed_date
                    if not DRY_RUN:
                        try: sf.Agreement__c.create(ag); stats["agreements_created"] += 1
                        except Exception as e: print(f"     [FAIL AGREE] {e}")

                note_body = build_note_body(ca, mkt)
                note_title = f"CA MDU Merge Import 2026-04-21 - {ca['Name'][:100]}"
                if not DRY_RUN:
                    try: attach_note(sf, new_id, note_title, note_body); stats["notes_attached"] += 1
                    except Exception as e: print(f"     [FAIL NOTE] {e}")

                log_entries.append({"action":"retry_create","ca_name":ca["Name"],"sf_id":new_id,"opp":new_opp,"hoa":hoa_flag})

        elif hoa_flag and sf_opp:
            # HOA backfill only
            if sf_opp.get("HOA__c") == True:
                stats["hoa_already_set"] += 1
                continue
            print(f"   [HOA ON]    {ca['Name'][:40]:40}  -> HOA__c=True")
            if not DRY_RUN:
                try:
                    sf.Opportunity.update(sf_opp["Id"], {"HOA__c": True})
                    stats["hoa_updated"] += 1
                except Exception as e:
                    print(f"     [FAIL HOA] {e}")
                    stats["hoa_errors"] += 1
                    log_entries.append({"action":"hoa_error","ca_name":ca["Name"],"error":str(e)})
                    continue
            log_entries.append({"action":"hoa_update","ca_name":ca["Name"],"sf_id":sf_opp["Id"]})

    # Write log
    with open(OUT_LOG, "w", encoding="utf-8") as f:
        json.dump({"mode": mode, "entries": log_entries, "stats": dict(stats)}, f, indent=2, default=str)
    print(f"\n[OK] Retry log: {OUT_LOG}")
    print("\n" + "=" * 70)
    print(f"DONE [{mode}]")
    print("=" * 70)
    for k, v in stats.most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
