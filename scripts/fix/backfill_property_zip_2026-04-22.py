"""Backfill Property_Zip__c on MDU Opps with blank zip.

Strategy:
  1. Regex-extract zip from Property_Address__c when anchored to state abbr or end-of-string
     and the first 2 digits are consistent with Property_State__c.
  2. For residuals, batch-geocode (address, city, state) via US Census Geocoder and
     parse zip from matched_address.

Flags:
  --dry-run            Preview only. No writes.
  --apply-regex        Apply the high-confidence regex extractions.
  --geocode            Run Census geocoder for residuals, write proposed_zip_geocoded.csv.
  --apply-geocoded     Read proposed_zip_geocoded.csv and apply the matched rows.

Outputs in this folder:
  blank_state_audit_2026-04-22.json      (audit data, reusable)
  rollback_regex_zip_2026-04-22.csv      (Id, prior_value=null, new_zip)
  proposed_zip_geocoded.csv              (geocoder output, review before apply)
  rollback_geocoded_zip_2026-04-22.csv   (Id, prior_value=null, new_zip)
"""
from __future__ import annotations
import csv
import io
import re
import sys
import time
from pathlib import Path

import requests
from simple_salesforce import Salesforce

SF_USERNAME = "cass1@ubiquitygp.com"
SF_PASSWORD = "Hawaiian1984"
SF_TOKEN    = "IBSKT6CFUpSUJWxq1CMm0HkFC"

FOLDER = Path(__file__).parent
ROLLBACK_REGEX = FOLDER / "rollback_regex_zip_2026-04-22.csv"
PROPOSED_GEO = FOLDER / "proposed_zip_geocoded.csv"
ROLLBACK_GEO = FOLDER / "rollback_geocoded_zip_2026-04-22.csv"

DRY = "--dry-run" in sys.argv
DO_REGEX = "--apply-regex" in sys.argv
DO_GEOCODE = "--geocode" in sys.argv
DO_APPLY_GEO = "--apply-geocoded" in sys.argv

STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI "
          "MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT "
          "VT VA WA WV WI WY DC").split()
STATE_GROUP = "|".join(STATES)

ZIP_AFTER_STATE = re.compile(rf'\b({STATE_GROUP})[,\s]+(\d{{5}})(?:-\d{{4}})?\b', re.IGNORECASE)
ZIP_TRAILING = re.compile(r'(\d{5})(?:-\d{4})?(?:[,\s]*(?:USA|US))?[\s,.]*$', re.IGNORECASE)

STATE_ZIP_PREFIX = {
    "AL":("35","36"),"AK":("99",),"AZ":("85","86"),"AR":("71","72"),
    "CA":("90","91","92","93","94","95","96"),"CO":("80","81"),"CT":("06",),
    "DE":("19",),"FL":("32","33","34"),"GA":("30","31","39"),"HI":("96",),
    "ID":("83",),"IL":("60","61","62"),"IN":("46","47"),"IA":("50","51","52"),
    "KS":("66","67"),"KY":("40","41","42"),"LA":("70","71"),"ME":("03","04"),
    "MD":("20","21"),"MA":("01","02"),"MI":("48","49"),"MN":("55","56"),
    "MS":("38","39"),"MO":("63","64","65"),"MT":("59",),"NE":("68","69"),
    "NV":("89",),"NH":("03",),"NJ":("07","08"),"NM":("87","88"),
    "NY":("00","10","11","12","13","14"),"NC":("27","28"),"ND":("58",),
    "OH":("43","44","45"),"OK":("73","74"),"OR":("97",),"PA":("15","16","17","18","19"),
    "RI":("02",),"SC":("29",),"SD":("57",),"TN":("37","38"),
    "TX":("75","76","77","78","79"),"UT":("84",),"VT":("05",),
    "VA":("20","22","23","24"),"WA":("98","99"),"WV":("24","25","26"),
    "WI":("53","54"),"WY":("82","83"),"DC":("20",)
}


def extract_zip(addr: str) -> str | None:
    if not addr:
        return None
    s = addr.strip()
    m = ZIP_AFTER_STATE.search(s)
    if m:
        return m.group(2)
    m = ZIP_TRAILING.search(s)
    if m:
        return m.group(1)
    return None


def strip_zip_from_address(addr: str) -> str:
    """Remove trailing zip / USA noise so geocoder doesn't choke."""
    s = addr.strip()
    s = re.sub(r',?\s*(USA|US)[\s,.]*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[\s,]+\d{5}(?:-\d{4})?\s*$', '', s)
    return s.strip(" ,")


def pull_blank_zip_rows(sf: Salesforce) -> list[dict]:
    soql = """
    SELECT Id, Name, Property_Address__c, Property_City__c, Property_State__c
    FROM Opportunity
    WHERE RecordType.DeveloperName = 'MDU'
      AND Property_Zip__c = null
    """
    return sf.query_all(soql)["records"]


def phase_regex(sf: Salesforce) -> list[dict]:
    rows = pull_blank_zip_rows(sf)
    hits: list[dict] = []
    conflicts: list[dict] = []
    for r in rows:
        z = extract_zip(r.get("Property_Address__c") or "")
        if not z:
            continue
        state = (r.get("Property_State__c") or "").upper()
        prefixes = STATE_ZIP_PREFIX.get(state, ())
        if prefixes and not z.startswith(prefixes):
            conflicts.append({"Id": r["Id"], "Name": r["Name"],
                              "state": state, "extracted_zip": z,
                              "address": r.get("Property_Address__c")})
            continue
        hits.append({"Id": r["Id"], "Name": r["Name"], "Property_Zip__c": z,
                     "address": r.get("Property_Address__c"),
                     "state": state})

    print(f"[regex] {len(rows)} blank-zip rows scanned")
    print(f"[regex] {len(hits)} high-confidence extractions (state-consistent)")
    print(f"[regex] {len(conflicts)} state/zip conflicts flagged (manual review):")
    for c in conflicts:
        print(f"   - {c['Name']}  SF state={c['state']}  addr={c['address']!r}  extracted={c['extracted_zip']}")

    if DO_REGEX and not DRY:
        with ROLLBACK_REGEX.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Id", "Name", "prior_value", "new_Property_Zip__c", "source"])
            for h in hits:
                w.writerow([h["Id"], h["Name"], "", h["Property_Zip__c"], "regex_from_Property_Address"])
        print(f"[regex] wrote rollback to {ROLLBACK_REGEX.name}")

        # Batch update via simple_salesforce
        BATCH = 200
        updated = 0
        for i in range(0, len(hits), BATCH):
            chunk = hits[i:i+BATCH]
            payload = [{"Id": h["Id"], "Property_Zip__c": h["Property_Zip__c"]} for h in chunk]
            results = sf.bulk.Opportunity.update(payload)
            ok = sum(1 for r in results if r.get("success"))
            updated += ok
            failed = [r for r in results if not r.get("success")]
            if failed:
                print(f"  [regex] batch {i//BATCH+1}: {ok} ok, {len(failed)} FAILED")
                for fr, h in zip(results, chunk):
                    if not fr.get("success"):
                        print(f"     FAIL {h['Id']} ({h['Name']}): {fr.get('errors')}")
            else:
                print(f"  [regex] batch {i//BATCH+1}: {ok} ok")
        print(f"[regex] APPLIED: {updated}/{len(hits)}")
    elif DO_REGEX and DRY:
        print(f"[regex] DRY: would apply {len(hits)} updates")

    return hits


def phase_geocode(sf: Salesforce):
    rows = pull_blank_zip_rows(sf)
    # Build candidates: have address AND city AND state, AND regex didn't match
    candidates = []
    for r in rows:
        addr = r.get("Property_Address__c") or ""
        if extract_zip(addr):
            continue
        clean_addr = strip_zip_from_address(addr)
        city = r.get("Property_City__c") or ""
        state = r.get("Property_State__c") or ""
        if not clean_addr or not city or not state:
            continue
        candidates.append({"Id": r["Id"], "Name": r["Name"], "street": clean_addr,
                           "city": city, "state": state})

    print(f"[geocode] candidates: {len(candidates)} of {len(rows)} residuals")
    skipped = len(rows) - len(candidates) - sum(1 for r in rows if extract_zip(r.get("Property_Address__c") or ""))
    print(f"[geocode] skipped (missing address/city/state): {skipped}")

    # US Census batch geocoder accepts CSV without header:
    #   Unique ID, Street address, City, State, ZIP
    # Up to 10,000 per request.
    csv_buf = io.StringIO()
    w = csv.writer(csv_buf, quoting=csv.QUOTE_MINIMAL)
    for c in candidates:
        w.writerow([c["Id"], c["street"], c["city"], c["state"], ""])
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    url = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
    print(f"[geocode] POSTing {len(candidates)} rows to Census batch geocoder ...")
    t0 = time.time()
    resp = requests.post(
        url,
        files={"addressFile": ("addresses.csv", csv_bytes, "text/csv")},
        data={"benchmark": "Public_AR_Current"},
        timeout=600,
    )
    print(f"[geocode] response: {resp.status_code} in {time.time()-t0:.1f}s, {len(resp.content)} bytes")
    resp.raise_for_status()

    # Response CSV columns:
    #   id, input_address, match_indicator, match_type, matched_address, coordinates, tigerline_id, side
    reader = csv.reader(io.StringIO(resp.text))
    matches = []
    no_match = []
    zip_re = re.compile(r'\b(\d{5})(?:-\d{4})?\b')
    by_id = {c["Id"]: c for c in candidates}
    for row in reader:
        if len(row) < 5:
            continue
        opp_id, input_addr, indicator, *rest = row
        matched_addr = rest[1] if len(rest) > 1 else ""
        if indicator != "Match":
            no_match.append({"Id": opp_id, "Name": by_id.get(opp_id, {}).get("Name"),
                             "input": input_addr, "indicator": indicator})
            continue
        # zip is usually the last 5-digit group in matched_address
        zips = zip_re.findall(matched_addr)
        if not zips:
            no_match.append({"Id": opp_id, "Name": by_id.get(opp_id, {}).get("Name"),
                             "input": input_addr, "indicator": "Match but no zip parsed",
                             "matched": matched_addr})
            continue
        z = zips[-1]
        cand = by_id.get(opp_id, {})
        prefixes = STATE_ZIP_PREFIX.get((cand.get("state") or "").upper(), ())
        consistent = not prefixes or z.startswith(prefixes)
        matches.append({"Id": opp_id, "Name": cand.get("Name"),
                        "input": input_addr, "matched": matched_addr,
                        "new_zip": z, "state": cand.get("state"),
                        "state_consistent": consistent})

    print(f"[geocode] matches:      {len(matches)}")
    print(f"[geocode] no_match:     {len(no_match)}")
    inconsistent = [m for m in matches if not m["state_consistent"]]
    print(f"[geocode] matches but state/zip mismatch: {len(inconsistent)} (will skip apply)")

    # Write review CSV
    with PROPOSED_GEO.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "state", "new_zip", "state_consistent", "input_address", "matched_address"])
        for m in matches:
            w.writerow([m["Id"], m["Name"], m["state"], m["new_zip"], m["state_consistent"],
                        m["input"], m["matched"]])
    print(f"[geocode] wrote proposals to {PROPOSED_GEO.name}")

    # Sample
    print("\nSample matches:")
    for m in matches[:8]:
        print(f"  {(m['Name'] or '')[:35]:<35} {m['state']:<3} zip={m['new_zip']} matched={m['matched']!r}")
    print("\nSample no-match:")
    for m in no_match[:8]:
        print(f"  {(m['Name'] or '')[:35]:<35} indicator={m['indicator']!r}  input={m['input']!r}")


def phase_apply_geocoded(sf: Salesforce):
    if not PROPOSED_GEO.exists():
        print(f"[apply-geo] missing {PROPOSED_GEO.name} -- run --geocode first")
        return
    to_apply = []
    with PROPOSED_GEO.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("state_consistent") != "True":
                continue
            to_apply.append({"Id": row["Id"], "Property_Zip__c": row["new_zip"],
                             "Name": row.get("Name")})
    print(f"[apply-geo] {len(to_apply)} state-consistent matches to apply")
    if DRY:
        print("[apply-geo] DRY: not applying")
        return
    with ROLLBACK_GEO.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Id", "Name", "prior_value", "new_Property_Zip__c", "source"])
        for h in to_apply:
            w.writerow([h["Id"], h.get("Name") or "", "", h["Property_Zip__c"], "census_geocoder"])
    print(f"[apply-geo] wrote rollback to {ROLLBACK_GEO.name}")
    BATCH = 200
    updated = 0
    for i in range(0, len(to_apply), BATCH):
        chunk = to_apply[i:i+BATCH]
        payload = [{"Id": h["Id"], "Property_Zip__c": h["Property_Zip__c"]} for h in chunk]
        results = sf.bulk.Opportunity.update(payload)
        ok = sum(1 for rr in results if rr.get("success"))
        updated += ok
        print(f"  [apply-geo] batch {i//BATCH+1}: {ok}/{len(chunk)} ok")
    print(f"[apply-geo] APPLIED: {updated}/{len(to_apply)}")


def main():
    if not any([DO_REGEX, DO_GEOCODE, DO_APPLY_GEO, DRY]):
        print("Specify at least one: --dry-run, --apply-regex, --geocode, --apply-geocoded")
        sys.exit(2)

    mode = "DRY RUN" if DRY else "LIVE"
    print(f"=== Property_Zip backfill [{mode}] ===\n")
    sf = Salesforce(username=SF_USERNAME, password=SF_PASSWORD, security_token=SF_TOKEN)

    if DO_REGEX or DRY:
        phase_regex(sf)
    if DO_GEOCODE:
        print()
        phase_geocode(sf)
    if DO_APPLY_GEO:
        print()
        phase_apply_geocoded(sf)


if __name__ == "__main__":
    main()
