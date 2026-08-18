"""Correct the misparsed address on Case 00001300 (AVR-138).

The AVR web form was submitted with a phone number in the House Number box:
    House Number: 2542906217
    Street:       3200 IDA
So Requested_Address__c rendered "2542906217 3200 IDA DR KILLEEN TX 76549".

The flow parsed the form faithfully; the source entry is wrong. The AVR
system's own canonical "Name:" line in Case.Description is the authority:
    Name:  3200 IDA DR KILLEEN TX 76549
which gives house=3200, street=IDA, suffix=DR.

Verification: after the write, Requested_Address__c must equal the address on
the Name: line. The script fails loudly if it does not.

One-off. 0 of 261 other AVR cases show this pattern, so no batch is needed.
"""
import json
import re
import subprocess
import urllib.request

CASE_ID = "500WR00001myJlOYAU"
API = "v63.0"
CORRECTION = {"House_Number__c": "3200", "Street_Name__c": "IDA"}

o = subprocess.run("sf org display -o cass1@ubiquitygp.com --json",
                   capture_output=True, text=True, shell=True).stdout
org = json.loads(o[o.index("{"):])["result"]


def rest(method, path, body=None):
    req = urllib.request.Request(
        f"{org['instanceUrl']}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {org['accessToken']}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


before = rest("GET", f"/services/data/{API}/sobjects/Case/{CASE_ID}")

# The AVR email's "Name:" line, minus the trailing submission timestamp.
name_line = before["Description"].split("\n")[0]
expected = re.sub(r"^Name:\s*", "", name_line)
expected = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{4}.*$", "", expected).strip()

print(f"Authority (Description 'Name:' line): {expected!r}\n")
print("BEFORE")
for f in (*CORRECTION, "Requested_Address__c"):
    print(f"  {f:24} {before.get(f)!r}")

rest("PATCH", f"/services/data/{API}/sobjects/Case/{CASE_ID}", CORRECTION)

after = rest("GET", f"/services/data/{API}/sobjects/Case/{CASE_ID}")
print("\nAFTER")
for f in (*CORRECTION, "Requested_Address__c"):
    print(f"  {f:24} {after.get(f)!r}")

got = " ".join((after.get("Requested_Address__c") or "").split())
if got != " ".join(expected.split()):
    raise SystemExit(f"\nFAIL: Requested_Address__c {got!r} != {expected!r}")
print(f"\nOK: Requested_Address__c now matches the AVR 'Name:' line.")
