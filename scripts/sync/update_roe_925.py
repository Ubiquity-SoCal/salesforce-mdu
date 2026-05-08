"""
Apply approved 9-25 Excel drift updates to Salesforce.

Reads roe_925_diff.json produced by diff_roe_925.py and applies updates, but
SKIPS any change that would regress a deal (SF in a sales-led stage, Excel
behind). Those cases represent the sales team moving the deal after ROE —
the 9-25 tracker is no longer authoritative for them.

Usage:
  python update_roe_925.py --dry-run   # preview
  python update_roe_925.py             # push
"""

import sys
import json
from simple_salesforce import Salesforce

DIFF_JSON = r"C:\Users\cass\Work_Projects\SalesForce\scripts\analysis\roe_925_diff.json"
DRY_RUN = "--dry-run" in sys.argv

# Regression guard: if SF is already in any of these stages, the 9-25 Excel
# is not authoritative — sales has taken the deal past ROE.
SALES_LED_STAGES = {
    "Contract Negotiations", "Under Contract", "Under Construction",
    "Ready for Eng", "Activation", "Closed Won",
}


def is_safe_update(row):
    """Reject updates that regress sales-led deals."""
    changes = row["changes"]
    stage_change = changes.get("StageName")
    if stage_change:
        sf_stage = stage_change["sf"]
        excel_stage = stage_change["excel"]
        # SF advanced past ROE by sales; skip regardless of what Excel says
        if sf_stage in SALES_LED_STAGES and excel_stage not in SALES_LED_STAGES:
            return False
        # SF already Closed Lost; Excel "reopening" is stale Excel, not drift
        if sf_stage == "Closed Lost" and excel_stage == "Prospecting":
            return False
    return True


def build_patch(row):
    """Turn a drift row into a dict of fields to PATCH."""
    patch = {}
    ch = row["changes"]
    if "StageName" in ch:
        patch["StageName"] = ch["StageName"]["excel"]
    if "Loss_Reason__c" in ch:
        patch["Loss_Reason__c"] = ch["Loss_Reason__c"]["excel"]
    if "Units__c" in ch:
        patch["Units__c"] = ch["Units__c"]["excel"]
    if "RE_Assigned__c" in ch:
        # excel side is initials; need to map back to User Id via import map
        from importlib import import_module
        # re-use initials map from the diff script
        RE_MAP = {
            "RS": "005WR0000030R9lYAE",
            "TF": "005WR0000030R1hYAE",
            "JB": "005WR0000030RCzYAM",
        }
        initials = ch["RE_Assigned__c"]["excel"]
        if initials in RE_MAP:
            patch["RE_Assigned__c"] = RE_MAP[initials]
    return patch


def main():
    print("=" * 70)
    print(f"ROE 9-25 Updates -> Salesforce  ({'DRY RUN' if DRY_RUN else 'LIVE'})")
    print("=" * 70)

    with open(DIFF_JSON, encoding="utf-8") as f:
        diff = json.load(f)

    safe = []
    skipped = []
    for row in diff["drift"]:
        if is_safe_update(row):
            safe.append(row)
        else:
            skipped.append(row)

    print(f"\nDrift rows: {len(diff['drift'])}")
    print(f"  Safe (will apply): {len(safe)}")
    print(f"  Skipped (sales-led, SF authoritative): {len(skipped)}")

    if skipped:
        print("\nSkipped:")
        for r in skipped:
            stage = r["changes"].get("StageName", {})
            print(f"  {r['agreement_name']:60} SF={stage.get('sf'):25} Excel-expected={stage.get('excel')}")

    if not safe:
        print("\nNothing to apply. Done.")
        return

    print("\nPlanned updates:")
    for r in safe:
        patch = build_patch(r)
        print(f"  {r['sf_id']}  {r['agreement_name'][:55]:55}  -> {patch}")

    if DRY_RUN:
        print("\nDRY RUN — not pushing. Re-run without --dry-run to apply.")
        return

    print("\nConnecting to Salesforce...")
    sf = Salesforce(
        username="cass1@ubiquitygp.com",
        password="Hawaiian1984",
        security_token="IBSKT6CFUpSUJWxq1CMm0HkFC",
    )

    ok, err = 0, []
    for r in safe:
        patch = build_patch(r)
        try:
            sf.Opportunity.update(r["sf_id"], patch)
            ok += 1
            print(f"  OK  {r['agreement_name'][:60]}")
        except Exception as e:
            err.append({"id": r["sf_id"], "name": r["agreement_name"], "error": str(e)})
            print(f"  FAIL {r['agreement_name'][:60]}: {e}")

    print(f"\nUpdated: {ok}")
    print(f"Errors: {len(err)}")


if __name__ == "__main__":
    main()
