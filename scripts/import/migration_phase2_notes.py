"""
Migration Phase 2 — Import Notes from Monday.com
===================================================
Step 1: Pull all updates from Monday.com API -> local JSON file
Step 2: Create ContentNotes in Salesforce from local file

Run with: python migration_phase2_notes.py pull    (Step 1 only)
          python migration_phase2_notes.py import  (Step 2 only)
          python migration_phase2_notes.py         (both steps)
"""

import requests
import json
import base64
import time
import sys
import os
import csv
from datetime import datetime
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"

API_KEY = open(r"C:\Users\cass\Work_Projects\Monday.com\Monday.com_Key.txt").read().strip()
MONDAY_URL = "https://api.monday.com/v2"
MONDAY_HEADERS = {"Authorization": API_KEY, "Content-Type": "application/json"}

UPDATES_FILE = r"C:/Users/cass/Work_Projects/Monday.com/full_archive/all_updates.json"
PROGRESS_FILE = "migration_notes_progress.json"
IMPORT_LOG_FILE = "migration_notes_log.json"  # Permanent record: which Monday update IDs were imported


def pull_updates():
    """Step 1: Pull all updates from Monday.com and save locally."""
    print("STEP 1: Pull updates from Monday.com")
    print("=" * 60)

    with open(r"C:/Users/cass/Work_Projects/Monday.com/full_archive/opportunities_full_archive.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    item_ids = [str(item["id"]) for item in items]
    item_names = {str(item["id"]): item["name"] for item in items}
    print(f"Total items to pull updates for: {len(item_ids)}")

    # Load existing progress if resuming
    all_updates = {}
    if os.path.exists(UPDATES_FILE):
        with open(UPDATES_FILE, "r", encoding="utf-8") as f:
            all_updates = json.load(f)
        print(f"Resuming: {len(all_updates)} items already pulled")

    remaining = [iid for iid in item_ids if iid not in all_updates]
    print(f"Remaining to pull: {len(remaining)}")

    # Pull in batches of 25 items
    BATCH_SIZE = 25
    total_updates = sum(len(v.get("updates", [])) for v in all_updates.values())
    start = time.time()

    for batch_start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[batch_start : batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE

        ids_str = ", ".join(batch)
        query = f"""{{
          items(ids: [{ids_str}]) {{
            id
            updates {{
              id
              text_body
              created_at
              creator {{
                name
              }}
            }}
          }}
        }}"""

        try:
            resp = requests.post(MONDAY_URL, headers=MONDAY_HEADERS, json={"query": query})
            resp_data = resp.json()

            if "errors" in resp_data:
                print(f"  API error batch {batch_num}: {resp_data['errors']}")
                # Rate limit - wait and retry
                if any("rate" in str(e).lower() or "limit" in str(e).lower() for e in resp_data["errors"]):
                    print("  Rate limited, waiting 60s...")
                    time.sleep(60)
                    continue
                time.sleep(5)
                continue

            fetched_items = resp_data.get("data", {}).get("items", [])
            batch_updates = 0
            for item in fetched_items:
                iid = str(item["id"])
                updates = item.get("updates", [])
                # Sort oldest first
                updates.sort(key=lambda u: u.get("created_at", ""))
                all_updates[iid] = {
                    "name": item_names.get(iid, "?"),
                    "updates": updates,
                }
                batch_updates += len(updates)
                total_updates += len(updates)

            # Items with no updates won't appear in response - mark them
            for iid in batch:
                if iid not in all_updates:
                    all_updates[iid] = {
                        "name": item_names.get(iid, "?"),
                        "updates": [],
                    }

            elapsed = time.time() - start
            print(
                f"  Batch {batch_num}/{total_batches}: "
                f"+{batch_updates} updates, {total_updates} total "
                f"({elapsed:.0f}s)"
            )

        except Exception as e:
            print(f"  Exception batch {batch_num}: {e}")
            time.sleep(10)
            continue

        # Save progress every 10 batches
        if batch_num % 10 == 0 or batch_start + BATCH_SIZE >= len(remaining):
            with open(UPDATES_FILE, "w", encoding="utf-8") as f:
                json.dump(all_updates, f, ensure_ascii=False)

        # Small delay between batches
        time.sleep(0.5)

    # Final save
    with open(UPDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(all_updates, f, ensure_ascii=False)

    items_with_updates = sum(1 for v in all_updates.values() if v.get("updates"))
    print(f"\nPull complete: {total_updates} updates across {items_with_updates} items")
    print(f"Saved to {UPDATES_FILE}")
    return all_updates


def import_notes(all_updates=None):
    """Step 2: Create ContentNotes in Salesforce from local file."""
    print("\nSTEP 2: Import notes to Salesforce")
    print("=" * 60)

    if all_updates is None:
        with open(UPDATES_FILE, "r", encoding="utf-8") as f:
            all_updates = json.load(f)

    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("Connected to Salesforce")

    # Get Opp IDs by Monday Item ID
    opps = sf.query_all("SELECT Id, Monday_Item_ID__c FROM Opportunity WHERE Monday_Item_ID__c != null")
    opp_map = {rec["Monday_Item_ID__c"]: rec["Id"] for rec in opps["records"]}
    print(f"Opps with Monday ID: {len(opp_map)}")

    # Load import progress (for resume)
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
    already_done = set(progress.get("completed_items", []))
    print(f"Already imported: {len(already_done)} items")

    # Count total work
    items_to_process = []
    total_notes = 0
    for monday_id, item_data in all_updates.items():
        if monday_id in already_done:
            continue
        if monday_id not in opp_map:
            continue
        updates = item_data.get("updates", [])
        if not updates:
            continue
        items_to_process.append((monday_id, item_data))
        total_notes += len(updates)

    print(f"Items to process: {len(items_to_process)}, Notes to create: {total_notes}")

    # Permanent import log — tracks every Monday update ID we've imported to SF
    # This is the key for future "sync new notes" runs
    import_log = {}
    if os.path.exists(IMPORT_LOG_FILE):
        with open(IMPORT_LOG_FILE, "r", encoding="utf-8") as f:
            import_log = json.load(f)
    imported_update_ids = set(import_log.get("imported_update_ids", []))
    print(f"Previously imported update IDs in log: {len(imported_update_ids)}")

    created = 0
    failed = 0
    skipped_existing = 0
    errors = []
    start = time.time()
    notes_count_updates = {}  # opp_id -> count
    newly_imported_ids = []

    for idx, (monday_id, item_data) in enumerate(items_to_process):
        opp_id = opp_map[monday_id]
        opp_name = item_data["name"]
        updates = item_data["updates"]
        item_created = 0

        for u in updates:
            update_id = str(u.get("id", ""))

            # Skip if already in permanent log (handles re-runs cleanly)
            if update_id and update_id in imported_update_ids:
                skipped_existing += 1
                continue

            author = u["creator"]["name"] if u.get("creator") else "Unknown"
            created_at = u.get("created_at", "")
            date_str = created_at[:10]
            text_body = u.get("text_body") or "(no text)"

            title = f"{author} - {date_str}"
            body_text = f"{author} | {created_at[:19].replace('T', ' ')}\n\n{text_body}"
            content_b64 = base64.b64encode(body_text.encode("utf-8")).decode("utf-8")

            try:
                note = sf.ContentNote.create({
                    "Title": title[:255],
                    "Content": content_b64,
                })
                note_id = note["id"]

                sf.ContentDocumentLink.create({
                    "ContentDocumentId": note_id,
                    "LinkedEntityId": opp_id,
                    "ShareType": "V",
                    "Visibility": "AllUsers",
                })

                created += 1
                item_created += 1
                if update_id:
                    imported_update_ids.add(update_id)
                    newly_imported_ids.append(update_id)

            except Exception as e:
                failed += 1
                errors.append((opp_name, title, str(e)))

            time.sleep(0.05)

        # Track notes count for this opp
        notes_count_updates[opp_id] = item_created

        # Mark item complete
        already_done.add(monday_id)

        # Progress update every 25 items
        if (idx + 1) % 25 == 0 or idx == len(items_to_process) - 1:
            elapsed = time.time() - start
            rate = created / elapsed if elapsed > 0 else 0
            remaining_notes = total_notes - created - failed - skipped_existing
            eta = remaining_notes / rate if rate > 0 else 0
            print(
                f"  [{idx+1}/{len(items_to_process)}] "
                f"{created} created, {failed} failed, {skipped_existing} skipped "
                f"({elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s)"
            )
            # Save progress
            progress["completed_items"] = list(already_done)
            progress["created"] = created
            progress["failed"] = failed
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(progress, f)
            # Save import log incrementally
            import_log["imported_update_ids"] = list(imported_update_ids)
            import_log["last_import_date"] = datetime.now().isoformat()
            import_log["total_imported"] = len(imported_update_ids)
            with open(IMPORT_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(import_log, f)

    # Update Notes_Count__c on each Opp
    print(f"\nUpdating Notes_Count__c on {len(notes_count_updates)} Opportunities...")
    count_updated = 0
    for opp_id, count in notes_count_updates.items():
        try:
            sf.Opportunity.update(opp_id, {"Notes_Count__c": count})
            count_updated += 1
        except Exception as e:
            print(f"  Count update failed for {opp_id}: {e}")
    print(f"  Updated {count_updated} Opportunities")

    # Save final import log
    import_log["imported_update_ids"] = list(imported_update_ids)
    import_log["last_import_date"] = datetime.now().isoformat()
    import_log["total_imported"] = len(imported_update_ids)
    with open(IMPORT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(import_log, f)

    # Final summary
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"NOTES IMPORT COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Created:  {created}")
    print(f"  Skipped:  {skipped_existing} (already in log)")
    print(f"  Failed:   {failed}")
    print(f"  Time:     {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"  Log file: {IMPORT_LOG_FILE} ({len(imported_update_ids)} total update IDs tracked)")
    print(f"\n  To sync new notes later, re-run: python migration_phase2_notes.py")
    print(f"  It will pull fresh updates from Monday.com and skip any already in the log.")

    if errors[:10]:
        print(f"\n  Sample errors:")
        for opp, title, err in errors[:10]:
            print(f"    {opp} / {title}: {err[:100]}")

    # Write error log
    if errors:
        with open("migration_notes_errors.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Opportunity", "Title", "Error"])
            for opp, title, err in errors:
                writer.writerow([opp, title, err])

    # Cleanup progress file on success
    if failed == 0 and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"

    if mode == "pull":
        pull_updates()
    elif mode == "import":
        import_notes()
    else:
        updates = pull_updates()
        import_notes(updates)


if __name__ == "__main__":
    main()
