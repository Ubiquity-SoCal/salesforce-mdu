"""Fill Sales_Status__c + apply Phase 1 name cleanup for the 14 blocked Opps.

Status mapping is derived from notes (reviewed with Koa).
Rollback CSV includes Id, old_name, new_name, old_status, new_status.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from simple_salesforce import Salesforce

CREDS = {
    "username": "cass1@ubiquitygp.com",
    "password": "Hawaiian1984",
    "security_token": "IBSKT6CFUpSUJWxq1CMm0HkFC",
}

REACHED = "Reached Out - Pending Response"
PENDING = "Contact Pending"

# (Id, new_name, new_status)
PLAN = [
    ("006WR00000wjdkrYAA", "Skandia Mobile Country Club",                     PENDING),
    ("006WR00000wkA7CYAU", "Aurora Meadows Apartments (Lumen CO)",            REACHED),
    ("006WR00000wkA7EYAU", "Ivy Crossing Apartment Homes (Lumen CO)",         REACHED),
    ("006WR00000wkA7JYAU", "Noahs Landing (Lumen FL_Starwood)",               REACHED),
    ("006WR00000wkA7KYAU", "Whistler's Cove Apartments (Lumen FL_Starwood)",  REACHED),
    ("006WR00000wkA7NYAU", "Buena Vista Point Apartments (Lumen FL_Starwood)",REACHED),
    ("006WR00000wkACYYA2", "The Townes at PV Landing Condo (The Vistas)",     PENDING),
    ("006WR00000wkAk1YAE", "The Bluffs at Carlsbad",                          REACHED),
    ("006WR00000wkDstYAE", "Southern Palms Mobile Home & RV Park",            REACHED),
    ("006WR00000wkDszYAE", "Arbor on Broadway (Now Called) Buenas on Broadway", REACHED),
    ("006WR00000wkDtGYAU", "HARKER_HEIGHTS_MDU_207-217 W Beeline MHP",        REACHED),
    ("006WR00000wkDtMYAU", "Fort_Hood MHP",                                   PENDING),
    ("006WR00000wkDtNYAU", "Omaha_MDU_Cherry Tree Apartments",                PENDING),
    ("006WR00000wkDtOYAU", "OMAHA_MDU_58TH_Plaza_CIR",                        PENDING),
]

HERE = Path(__file__).parent
BACKUP = HERE / "rollback"
BACKUP.mkdir(exist_ok=True)


def main() -> None:
    sf = Salesforce(**CREDS)

    ids = [p[0] for p in PLAN]
    q = (
        "SELECT Id, Name, Sales_Status__c FROM Opportunity WHERE Id IN ('{}')"
        .format("','".join(ids))
    )
    current = {r["Id"]: r for r in sf.query_all(q)["records"]}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback = BACKUP / f"phase1b_rollback_{stamp}.csv"
    applied = []
    errors = []

    for oid, new_name, new_status in PLAN:
        c = current.get(oid)
        if c is None:
            errors.append((oid, "record not found"))
            continue
        payload = {"Name": new_name, "Sales_Status__c": new_status}
        try:
            sf.Opportunity.update(oid, payload)
            applied.append(
                {
                    "Id": oid,
                    "old_name": c["Name"],
                    "new_name": new_name,
                    "old_status": c.get("Sales_Status__c"),
                    "new_status": new_status,
                }
            )
            print(f"  [OK] {oid}  status={new_status}")
        except Exception as e:
            errors.append((oid, str(e)))
            print(f"  [ERR] {oid}  {e}")

    with rollback.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Id", "old_name", "new_name", "old_status", "new_status"])
        w.writeheader()
        w.writerows(applied)

    print(f"\nApplied {len(applied)}/{len(PLAN)}.  Rollback: {rollback}")
    if errors:
        print("\nErrors:")
        for oid, msg in errors:
            print(f"  {oid}: {msg}")


if __name__ == "__main__":
    main()
