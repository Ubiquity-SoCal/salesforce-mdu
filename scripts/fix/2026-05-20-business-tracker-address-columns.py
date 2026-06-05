"""
Repoint the Business_Sales tracker view Address/City/State columns from the
Property_Unit -> Property_Location chain (null for Business ROE Opps, which have
no Property Unit) to the new coalescing display formula fields on Opportunity.

Why: Business ROE Opps link straight to Property_Location (no Property_Unit), so
the unit-chain columns rendered blank for them. The *_Display__c formula fields
coalesce the Opp's direct Property_City/State/Address with the unit-chain values,
so a single column works for both Business Sales (tenant) and Business ROE.

Snapshots every Business_Sales Tracker_View__c.Config__c to data/output before
mutating (rollback point). Safe to re-run: it is idempotent.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request
import urllib.error

API = "v60.0"

REMAP = {
    "Property_Unit__r.Property_Location__r.Business_Base_Address__c": "Property_Address_Display__c",
    "Property_Unit__r.Property_Location__r.City__c": "Property_City_Display__c",
    "Property_Unit__r.Property_Location__r.State__c": "Property_State_Display__c",
}


def sf_org():
    out = subprocess.run("sf org display --json", shell=True, capture_output=True, text=True)
    txt = out.stdout
    txt = txt[txt.index("{"):]  # strip any CLI warning preamble
    d = json.loads(txt)
    return d["result"]["instanceUrl"], d["result"]["accessToken"]


def rest(instance, token, method, path, body=None):
    url = instance + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    instance, token = sf_org()
    soql = "SELECT Id, Name, Config__c FROM Tracker_View__c WHERE App_Context__c='Business_Sales'"
    status, res = rest(instance, token, "GET",
                       "/services/data/%s/query/?q=%s" % (API, urllib.parse.quote(soql)))
    recs = res["records"]

    out_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "output"))
    os.makedirs(out_dir, exist_ok=True)
    backup = os.path.join(out_dir, "tracker-view-config-backup-2026-05-20.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump([{"Id": r["Id"], "Name": r["Name"], "Config__c": r["Config__c"]} for r in recs],
                  f, indent=2)
    print("Backed up %d Business_Sales configs -> %s" % (len(recs), backup))

    for r in recs:
        cfg = json.loads(r["Config__c"])
        changed = 0
        for col in cfg.get("columns", []):
            if col.get("field") in REMAP:
                col["field"] = REMAP[col["field"]]
                changed += 1
        if changed:
            st, resp = rest(instance, token, "PATCH",
                            "/services/data/%s/sobjects/Tracker_View__c/%s" % (API, r["Id"]),
                            {"Config__c": json.dumps(cfg)})
            ok = "OK" if st in (200, 204) else "FAIL %s" % resp
            print("  %-28s %d col(s) -> %s" % (r["Name"], changed, ok))
        else:
            print("  %-28s no matching columns (already updated?)" % r["Name"])


if __name__ == "__main__":
    main()
