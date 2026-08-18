"""Backfill Case 00001300 (AVR-138) after the Requestor_Email_Extract flow failed.

The flow died on STRING_TOO_LONG (Requestor__c was Text(20), "Pablo Gallegos
Sanchez" is 22). Its record update is all-or-nothing, so all 16 AVR fields were
left null. Field widened to Text(80) by deploys/2026-08-18-avr-field-lengths/.

The flow is recordTriggerType=Create, so re-saving the Case will NOT re-fire it.
This re-applies the flow's own MID/FIND/TRIM formulas to Case.Description and
PATCHes the result, so the row matches what the flow would have produced.
"""
import json
import re
import subprocess
import urllib.request

CASE_ID = "500WR00001myJlOYAU"
ORG = "cass1@ubiquitygp.com"
API = "v63.0"

# (field, start label, end label) mirroring the flow's ExtractX formulas
BOUNDS = [
    ("AVR_Number__c",          "AVR Number:",            "Requestor:"),
    ("Requestor__c",           "Requestor:",             "Requestor Email:"),
    ("Request_Description__c", "Please Describe Issue:", "House Number:"),
    ("House_Number__c",        "House Number:",          "PreDirectional:"),
    ("PreDirectional__c",      "PreDirectional:",        "Street:"),
    ("Street_Name__c",         "Street:",                "Street Suffix:"),
    ("Street_Suffix__c",       "Street Suffix:",         "Post Directional:"),
    ("Post_Directional__c",    "Post Directional:",      "Apartment:"),
    ("Unit_Number__c",         "Apartment:",             "City:"),
    ("City__c",                "City:",                  "State:"),
    ("State__c",               "State:",                 "Postal Code:"),
    ("Zip_Code__c",            "Postal Code:",           "Priority:"),
    ("Latitude__c",            "Latitude:",              "Longitude:"),
    ("Longitude__c",           "Longitude:",             "Location Type:"),
    ("Address_Type__c",        "Location Type:",         "Region:"),
]


def sf_json(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True).stdout
    return json.loads(out[out.index("{"):])


def extract(desc, start, end):
    i, j = desc.find(start), desc.find(end)
    if i < 0 or j <= i:
        return None
    return desc[i + len(start):j].strip() or None


org = sf_json(f"sf org display -o {ORG} --json")["result"]
base, token = org["instanceUrl"], org["accessToken"]


def rest(method, path, body=None):
    req = urllib.request.Request(
        f"{base}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


desc = rest("GET", f"/services/data/{API}/sobjects/Case/{CASE_ID}")["Description"]

payload = {f: v for f, s, e in BOUNDS if (v := extract(desc, s, e))}
payload["Requestor_Email__c"] = re.search(r"Requestor Email:\s*(\S+?)<", desc).group(1)

print(f"Backfilling Case {CASE_ID} with {len(payload)} fields:")
for field, value in sorted(payload.items()):
    print(f"  {field:26} ({len(value):3}) {value!r}")

rest("PATCH", f"/services/data/{API}/sobjects/Case/{CASE_ID}", payload)

check = rest("GET", f"/services/data/{API}/sobjects/Case/{CASE_ID}")
print("\nVerified from org:")
for field in sorted(payload):
    print(f"  {field:26} {check.get(field)!r}")
