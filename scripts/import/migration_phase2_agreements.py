"""
Migration Phase 2 — Import Agreements from Monday.com
=======================================================
Extracts Agreement__c records from PAL Stage, MA Stage, Bulk Stage columns
and signed date columns on each Monday.com item.
"""

import json
import time
from datetime import datetime
from collections import Counter
from simple_salesforce import Salesforce

USERNAME = "cass1@ubiquitygp.com"
PASSWORD = "Karate88!"
SECURITY_TOKEN = "Ktc1n9mLmD9vwEcVcl45q0iAD"

# Stage value -> IronClad Status mapping
STAGE_TO_STATUS = {
    "Signed": "Completed",
    "Signed - 3rd Party / Tenant": "Completed",
    "Owner-Signed PAL": "Completed",
    "ROE Signed": "Completed",
    "Out for Signature": "Sign",
    "Under Client Review": "Review",
    "Pending - 3rd Party / Tenant": "Review",
    "On Hold": "Paused",
    "Dead/Lost": "Cancelled",
    "Terminated": "Cancelled",
    "Existing EMA": "Archive",
    "No Agreement Desired": "Cancelled",
}
SKIP_VALUES = {"", "N/A - Bulk", "N/A - Retail MA"}


def get_col(item, col_id):
    for cv in item.get("column_values", []):
        if cv["id"] == col_id:
            return (cv.get("text") or "").strip()
    return ""


def parse_date(d):
    if not d:
        return None
    try:
        return datetime.strptime(d.strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def main():
    print("Migration Phase 2 - Import Agreements")
    print("=" * 60)

    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    print("Connected to Salesforce")

    with open(r"C:/Users/cass/Work_Projects/Monday.com/full_archive/opportunities_full_archive.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]
    print(f"Loaded {len(items)} items")

    # Get Opp IDs by Monday Item ID
    opps = sf.query_all("SELECT Id, Monday_Item_ID__c FROM Opportunity WHERE Monday_Item_ID__c != null")
    opp_map = {rec["Monday_Item_ID__c"]: rec["Id"] for rec in opps["records"]}
    print(f"MDU Opps with Monday ID: {len(opp_map)}")

    agreements = []

    for item in items:
        monday_id = str(item["id"])
        opp_id = opp_map.get(monday_id)
        if not opp_id:
            continue

        # PAL agreement
        pal_stage = get_col(item, "status_19")
        pal_signed = parse_date(get_col(item, "date0"))
        if pal_stage and pal_stage not in SKIP_VALUES:
            status = STAGE_TO_STATUS.get(pal_stage, "Create")
            agr = {
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "PAL",
                "Status__c": status,
            }
            if pal_signed:
                agr["Signed_Date__c"] = pal_signed
                if status not in ("Completed", "Archive"):
                    agr["Status__c"] = "Completed"
            agreements.append(agr)
        elif not pal_stage and pal_signed:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "PAL",
                "Status__c": "Completed",
                "Signed_Date__c": pal_signed,
            })

        # MA/EMA agreement
        ma_stage = get_col(item, "status_18")
        ma_signed = parse_date(get_col(item, "date3"))
        if ma_stage and ma_stage not in SKIP_VALUES:
            status = STAGE_TO_STATUS.get(ma_stage, "Create")
            agr = {
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "EMA",
                "Status__c": status,
            }
            if ma_signed:
                agr["Signed_Date__c"] = ma_signed
                if status not in ("Completed", "Archive"):
                    agr["Status__c"] = "Completed"
            agreements.append(agr)
        elif not ma_stage and ma_signed:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "EMA",
                "Status__c": "Completed",
                "Signed_Date__c": ma_signed,
            })

        # Bulk agreement
        bulk_stage = get_col(item, "color5")
        if bulk_stage and bulk_stage not in SKIP_VALUES:
            status = STAGE_TO_STATUS.get(bulk_stage, "Create")
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "Bulk",
                "Status__c": status,
            })

        # PAL Addendum (from signed date)
        pal_add_date = parse_date(get_col(item, "date7"))
        if pal_add_date:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "PAL Addendum",
                "Status__c": "Completed",
                "Signed_Date__c": pal_add_date,
            })

        # MSA Addendum (from signed date)
        msa_add_date = parse_date(get_col(item, "date07"))
        if msa_add_date:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "MSA Addendum",
                "Status__c": "Completed",
                "Signed_Date__c": msa_add_date,
            })

        # 2nd ISP NEMA (from signed date)
        isp2_ma_date = parse_date(get_col(item, "date_mktzmpzk"))
        if isp2_ma_date:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "2nd ISP NEMA",
                "Status__c": "Completed",
                "Signed_Date__c": isp2_ma_date,
            })

        # 2nd ISP MSA Addendum (from signed date)
        isp2_msa_date = parse_date(get_col(item, "date_mkrsd2n"))
        if isp2_msa_date:
            agreements.append({
                "Opportunity__c": opp_id,
                "Agreement_Type__c": "2nd ISP MSA Addendum",
                "Status__c": "Completed",
                "Signed_Date__c": isp2_msa_date,
            })

    # Stats
    type_counts = Counter(a["Agreement_Type__c"] for a in agreements)
    status_counts = Counter(a["Status__c"] for a in agreements)
    print(f"\nTotal agreements to create: {len(agreements)}")
    print("\nBy type:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")
    print("\nBy status:")
    for s, c in status_counts.most_common():
        print(f"  {s}: {c}")

    # Import
    BATCH_SIZE = 200
    total_created = 0
    total_failed = 0
    errors = []
    start = time.time()

    print(f"\nImporting {len(agreements)} agreements...")
    for i in range(0, len(agreements), BATCH_SIZE):
        batch = agreements[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(agreements) + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            results = sf.bulk.Agreement__c.insert(batch, batch_size=BATCH_SIZE)
            for j, r in enumerate(results):
                if r.get("success"):
                    total_created += 1
                else:
                    total_failed += 1
                    errors.append(str(r.get("errors", "?")))
        except Exception as e:
            print(f"  Batch {batch_num} bulk failed: {e}, falling back...")
            for rec in batch:
                try:
                    result = sf.Agreement__c.create(rec)
                    if result.get("success"):
                        total_created += 1
                    else:
                        total_failed += 1
                        errors.append(str(result))
                except Exception as e2:
                    total_failed += 1
                    errors.append(str(e2))

        elapsed = time.time() - start
        print(f"  Batch {batch_num}/{total_batches}: {total_created} created, {total_failed} failed ({elapsed:.0f}s)")

    print(f"\nDone: {total_created} created, {total_failed} failed in {time.time() - start:.0f}s")
    if errors[:5]:
        print("Sample errors:")
        for e in errors[:5]:
            print(f"  {e}")

    r = sf.query("SELECT COUNT() FROM Agreement__c")
    print(f"Total Agreement__c records: {r['totalSize']}")


if __name__ == "__main__":
    main()
