# MDU Agreements Milestone Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native, refreshable Salesforce report — one row per MDU property with a signed PAL/ROE — exposing each agreement milestone (PAL, ROE, EMA, Bulk, PAL Addendum signed dates) as its own column, alongside Sales POC, property contacts (Property Manager / Property Owner), units, address, state, and SiteTracker project info.

**Architecture:** The milestone dates live on child `Agreement__c` records (one per `Agreement_Type__c`). We pivot them onto the Opportunity with five native roll-up summary date fields (MAX of `Signed_Date__c`, filtered by type + a shared `Is_Signed__c` flag), then build a tabular Opportunity report over those fields plus the already-surfaced SiteTracker fields. Contact names — which roll-up summaries can't concatenate — are materialized onto the Opportunity by a record-triggered Flow (+ a backfill for existing rows). No Apex; all declarative metadata deployed via the Metadata REST API. Core report (Tasks 1–3) ships first; contacts (Tasks 4–7) layer on.

**Tech Stack:** Python 3 + `simple_salesforce` + `requests`; Salesforce Metadata API v59.0 (`deployRequest` endpoint); Salesforce Analytics REST API for verification.

## Global Constraints

- **Org:** `https://fun-power-747.my.salesforce.com`, user `cass1@ubiquitygp.com`. Scripts connect via `_md_deploy.connect()` (prefers `SF_SESSION_ID` env, else inline creds — matching the existing `scripts/deploy/` convention).
- **API version:** `59.0` for every metadata deploy.
- **`enableReports` FOOT-GUN (hard rule):** any deploy of the `Agreement__c` object header MUST include `<enableReports>true</enableReports>`, or Allow Reports silently resets to false and breaks the `OpportunityCustomEntity$Agreement__c` report type and every report on it. (See `palroe-completed-dashboard`, `sf-report-dashboard-metadata-gotchas`.)
- **"Signed" definition (Taylor owns it, locked 2026-05-22):** an agreement is signed when `Status__c ∈ {Completed, Cancelled}` AND `Signed_Date__c` is populated. Encoded once in `Agreement__c.Is_Signed__c`.
- **Master-detail:** `Agreement__c.Opportunity__c` is the master-detail to Opportunity (`summaryForeignKey`). `Agreement__c` sharing model is `ControlledByParent`.
- **File placement:** all build scripts go in `SalesForce/scripts/deploy/` as `2026-06-17-<purpose>.py` (established peer convention, e.g. `2026-05-21-add-signed-pal-rollup.py`).
- **FLS targets:** grant read on every new field to profiles `Admin` and `Standard User - Custom` (the MDU team).
- **Report folder / name:** folder `MDU_Sales_Reports`; report Name `MDU Agreements Milestone Tracker` (≤40 chars); RecordType filter value `Opportunity.MDU`.
- **No record mutation:** this is metadata + report only. Roll-ups recalc automatically; no data writes.
- **Branch:** all work on a dedicated `mdu-agreements-tracker` branch (created at execution time), NOT on `dashboard-by-owner-tab`.

---

### Task 1: Shared deploy helper + `Agreement__c.Is_Signed__c` formula

**Files:**
- Create: `SalesForce/scripts/deploy/_md_deploy.py`
- Create: `SalesForce/scripts/deploy/2026-06-17-add-agreement-is-signed.py`

**Interfaces:**
- Produces (`_md_deploy.py`):
  - `connect() -> simple_salesforce.Salesforce` — authenticated client.
  - `deploy(sf, files: dict[str, str], members_types: list[tuple[str, str]], label: str, check_only: bool = False) -> bool` — zips `files` (path→content) with a generated `package.xml` from `members_types` (member, metadataTypeName), POSTs to the Metadata REST `deployRequest` endpoint, polls to completion, prints component failures, returns `True` on `Succeeded`.
  - Module constants `INSTANCE` (derived from the session) and `V = "59.0"`.
- Produces (org): `Agreement__c.Is_Signed__c` (formula checkbox).
- Consumed by: Tasks 2 and 3 (`from _md_deploy import connect, deploy`).

- [ ] **Step 1: Write the shared deploy helper**

Create `SalesForce/scripts/deploy/_md_deploy.py`:

```python
"""Shared Metadata-API deploy helper for the 2026-06-17 MDU Agreements Tracker build.
Zips a metadata package and deploys via the Metadata REST deployRequest endpoint.
Reused by every deploy script in this build so the deploy logic lives in one place."""
import os, io, json, time, base64, zipfile, requests
from collections import OrderedDict
from simple_salesforce import Salesforce

V = "59.0"
_FALLBACK = dict(username="cass1@ubiquitygp.com", password="<password: see _shared/sf_auth.py>",
                 security_token="<token: see _shared/sf_auth.py>")


def connect():
    """Salesforce client: prefer SF_SESSION_ID env (CI/daily run), else inline creds."""
    if os.environ.get("SF_SESSION_ID"):
        return Salesforce(instance_url=os.environ.get("SF_INSTANCE_URL",
                          "https://fun-power-747.my.salesforce.com"),
                          session_id=os.environ["SF_SESSION_ID"])
    return Salesforce(**_FALLBACK)


def deploy(sf, files, members_types, label, check_only=False):
    """files: {zip_path: xml_content}; members_types: [(member, metaType), ...].
    Members are grouped by type into one <types> block each (valid package.xml)."""
    grouped = OrderedDict()
    for m, t in members_types:
        grouped.setdefault(t, []).append(m)
    types_xml = "".join("<types>" + "".join(f"<members>{m}</members>" for m in ms)
                        + f"<name>{t}</name></types>" for t, ms in grouped.items())
    pkg = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<Package xmlns="http://soap.sforce.com/2006/04/metadata">'
           f'{types_xml}<version>{V}</version></Package>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.xml", pkg)
        for path, content in files.items():
            zf.writestr(path, content)
    instance = f"https://{sf.sf_instance}"
    url = f"{instance}/services/data/v{V}/metadata/deployRequest"
    raw = base64.b64encode(buf.getvalue()).decode()
    b64 = "\r\n".join(raw[i:i + 76] for i in range(0, len(raw), 76))  # wrap for multipart
    body = {"deployOptions": {"checkOnly": check_only, "ignoreWarnings": True,
                              "rollbackOnError": True, "singlePackage": True}}
    bnd = "----B"
    payload = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"json\"\r\n"
               f"Content-Type: application/json\r\n\r\n{json.dumps(body)}\r\n"
               f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"d.zip\"\r\n"
               f"Content-Type: application/zip\r\nContent-Transfer-Encoding: base64\r\n\r\n"
               f"{b64}\r\n--{bnd}--")
    hdr = {"Authorization": f"Bearer {sf.session_id}",
           "Content-Type": f"multipart/form-data; boundary={bnd}"}
    r = requests.post(url, headers=hdr, data=payload)
    if r.status_code not in (200, 201):
        print(f"[{label}] POST {r.status_code}: {r.text[:300]}"); return False
    did = r.json()["id"]
    for i in range(40):
        time.sleep(3)
        res = requests.get(f"{url}/{did}?includeDetails=true",
                           headers={"Authorization": f"Bearer {sf.session_id}"}).json()
        st = res.get("deployResult", {}).get("status", "?")
        print(f"  [{label}] poll {i + 1}: {st}")
        if st == "Succeeded":
            return True
        if st in ("Failed", "Canceled", "SucceededPartial"):
            for f in (res.get("deployResult", {}).get("details", {})
                      .get("componentFailures", []) or []):
                if isinstance(f, dict):
                    print(f"  FAIL: {f.get('fullName')} - {f.get('problem')}")
            return False
    print(f"  [{label}] timed out"); return False
```

- [ ] **Step 2: Write the verification check (expect the field to be ABSENT first)**

Run:

```bash
cd /c/Users/cass/Work_Projects
python -c "from SalesForce.scripts.deploy._md_deploy import connect; sf=connect(); print('Is_Signed__c' in [f['name'] for f in sf.Agreement__c.describe()['fields']])"
```

Expected: `False` (field does not exist yet). If `True`, the field already exists — skip the deploy in Step 3 and go to Step 4.

- [ ] **Step 3: Write and run the formula-field deploy script**

Create `SalesForce/scripts/deploy/2026-06-17-add-agreement-is-signed.py`:

```python
"""Adds Agreement__c.Is_Signed__c (formula checkbox) encoding Taylor's 2026-05-22
signed definition: Status in (Completed, Cancelled) AND Signed_Date populated.
Drives the per-type signed-date rollups on Opportunity (Task 2). Additive."""
from _md_deploy import connect, deploy

sf = connect()

# Object header MUST include <enableReports>true</enableReports> (foot-gun: omitting it
# silently disables Allow Reports and breaks the Opportunities-with-Agreements report type).
AGR_HDR = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>Agreement</label><pluralLabel>Agreements</pluralLabel>
    <nameField><label>Agreement Number</label><displayFormat>AGR-{0000}</displayFormat><type>AutoNumber</type></nameField>
    <sharingModel>ControlledByParent</sharingModel><deploymentStatus>Deployed</deploymentStatus>
    <enableReports>true</enableReports>
    <fields>
        <fullName>Is_Signed__c</fullName>
        <label>Is Signed</label>
        <type>Checkbox</type>
        <formula>AND(OR(ISPICKVAL(Status__c, "Completed"), ISPICKVAL(Status__c, "Cancelled")), NOT(ISBLANK(Signed_Date__c)))</formula>
        <description>True when an agreement Status is Completed/Cancelled and has a Signed Date (Taylor 2026-05-22 signed definition). Drives the Opportunity per-type signed-date rollups.</description>
    </fields>
</CustomObject>"""

existing = [f["name"] for f in sf.Agreement__c.describe()["fields"]]
if "Is_Signed__c" in existing:
    print("Is_Signed__c already exists; skipping deploy.")
else:
    ok = deploy(sf, {"objects/Agreement__c.object": AGR_HDR},
                [("Agreement__c", "CustomObject")], "agr-is-signed")
    if not ok:
        raise SystemExit(1)

# Verify the formula matches the raw SOQL definition.
sf2 = connect()
def c(q): return sf2.query(q)["records"][0]["c"]
flag = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Is_Signed__c = true")
raw  = c("SELECT COUNT(Id) c FROM Agreement__c WHERE Status__c IN ('Completed','Cancelled') AND Signed_Date__c != null")
print(f"\nVerification: Is_Signed__c=true -> {flag} ; raw definition -> {raw} (expect equal)")
assert flag == raw, "Is_Signed__c does not match the raw signed definition!"
print("OK: Is_Signed__c matches the signed definition.")
```

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-add-agreement-is-signed.py
```

Expected output ends with: `[agr-is-signed] poll N: Succeeded` then `OK: Is_Signed__c matches the signed definition.`

- [ ] **Step 4: Confirm Allow Reports is still on (foot-gun guard)**

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "from _md_deploy import connect; sf=connect(); print(sf.query(\"SELECT Id FROM Report WHERE DeveloperName='Signed_PALs'\")['records'][0]['Id'])"
```

Expected: prints a report Id (the existing agreement report type still resolves). If it errors, the foot-gun fired — re-deploy `AGR_HDR` (it already includes `enableReports`) and re-run.

- [ ] **Step 5: Commit**

```bash
git add SalesForce/scripts/deploy/_md_deploy.py SalesForce/scripts/deploy/2026-06-17-add-agreement-is-signed.py
git commit -m "feat(sf): add Agreement__c.Is_Signed__c flag for milestone tracker"
```

---

### Task 2: Five Opportunity roll-up date fields + FLS

**Files:**
- Create: `SalesForce/scripts/deploy/2026-06-17-add-opp-milestone-date-rollups.py`

**Interfaces:**
- Consumes: `_md_deploy.connect`, `_md_deploy.deploy`; `Agreement__c.Is_Signed__c` (Task 1).
- Produces (org), all on Opportunity, all `Summary` (MAX of `Agreement__c.Signed_Date__c`):
  `PAL_Signed_Date__c`, `ROE_Signed_Date__c`, `EMA_Signed_Date__c`, `Bulk_Signed_Date__c`, `PAL_Addendum_Signed_Date__c`. Consumed by the report in Task 3.

- [ ] **Step 1: Verify the fields are ABSENT first**

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "from _md_deploy import connect; sf=connect(); print('PAL_Signed_Date__c' in [f['name'] for f in sf.Opportunity.describe()['fields']])"
```

Expected: `False`.

- [ ] **Step 2: Write the rollup + FLS deploy script**

Create `SalesForce/scripts/deploy/2026-06-17-add-opp-milestone-date-rollups.py`:

```python
"""Adds five Opportunity roll-up summary date fields: MAX(Agreement__c.Signed_Date__c)
filtered by Agreement_Type__c and Is_Signed__c=true. One per milestone type.
Pivots the per-type signed dates onto the Opportunity so the tracker report shows
them as columns on one row per property. Additive; rollups recalc automatically."""
from _md_deploy import connect, deploy

sf = connect()

# (api_name, label, agreement_type_value)
ROLLUPS = [
    ("PAL_Signed_Date__c",          "PAL Signed Date",          "PAL"),
    ("ROE_Signed_Date__c",          "ROE Signed Date",          "ROE"),
    ("EMA_Signed_Date__c",          "EMA Signed Date",          "EMA"),
    ("Bulk_Signed_Date__c",         "Bulk Signed Date",         "Bulk"),
    ("PAL_Addendum_Signed_Date__c", "PAL Addendum Signed Date", "PAL Addendum"),
]

def field_xml(api, label, atype):
    return f"""    <fields>
        <fullName>{api}</fullName>
        <label>{label}</label>
        <summarizedField>Agreement__c.Signed_Date__c</summarizedField>
        <summaryForeignKey>Agreement__c.Opportunity__c</summaryForeignKey>
        <summaryOperation>max</summaryOperation>
        <summaryFilterItems>
            <field>Agreement__c.Agreement_Type__c</field>
            <operation>equals</operation>
            <value>{atype}</value>
        </summaryFilterItems>
        <summaryFilterItems>
            <field>Agreement__c.Is_Signed__c</field>
            <operation>equals</operation>
            <value>True</value>
        </summaryFilterItems>
        <type>Summary</type>
        <description>MAX signed date of {atype} agreements (Status Completed/Cancelled + Signed Date) on this Opportunity. Built for the MDU Agreements Milestone Tracker.</description>
    </fields>"""

existing = [f["name"] for f in sf.Opportunity.describe()["fields"]]
todo = [r for r in ROLLUPS if r[0] not in existing]
if not todo:
    print("All five rollup fields already exist; skipping deploy.")
else:
    body = "".join(field_xml(*r) for r in todo)
    opp = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">\n'
           f'{body}\n</CustomObject>')
    if not deploy(sf, {"objects/Opportunity.object": opp},
                  [("Opportunity", "CustomObject")], "opp-rollups"):
        raise SystemExit(1)

# FLS read for Admin + the MDU team profile (rollups are read-only).
def fls_xml(profile_api):
    perms = "".join(
        f"<fieldPermissions><editable>false</editable>"
        f"<field>Opportunity.{api}</field><readable>true</readable></fieldPermissions>"
        for api, _, _ in ROLLUPS)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Profile xmlns="http://soap.sforce.com/2006/04/metadata">'
            f'{perms}</Profile>')

for prof in ["Admin", "Standard User - Custom"]:
    ok = deploy(sf, {f"profiles/{prof}.profile": fls_xml(prof)},
                [(prof, "Profile")], f"fls-{prof}")
    if not ok:
        print(f"  WARN: FLS deploy failed for '{prof}' (verify the profile name).")

# Verify a rollup matches the child data for one agreement type.
sf2 = connect()
def c(q): return sf2.query(q)["records"][0]["c"]
missed = c("SELECT COUNT(Id) c FROM Opportunity WHERE Id IN "
           "(SELECT Opportunity__c FROM Agreement__c WHERE Agreement_Type__c='PAL' AND Is_Signed__c=true) "
           "AND PAL_Signed_Date__c = null")
print(f"\nVerification: PAL-signed opps with null PAL_Signed_Date__c -> {missed} (expect 0)")
assert missed == 0, "A PAL-signed opp has a null PAL rollup — recalc/filters wrong!"
for api, _, _ in ROLLUPS:
    n = c(f"SELECT COUNT(Id) c FROM Opportunity WHERE {api} != null")
    print(f"   {api:<30} populated on {n} opps")
print("OK: rollups populate correctly.")
```

- [ ] **Step 3: Run the script**

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-add-opp-milestone-date-rollups.py
```

Expected: `[opp-rollups] poll N: Succeeded`, both `[fls-...]` deploys `Succeeded`, `Verification: ... -> 0 (expect 0)`, a populated-count line per field (PAL ≈ 355, ROE non-zero), ending `OK: rollups populate correctly.`

- [ ] **Step 4: Spot-check one property against its children**

Run (replace nothing — picks a property with multiple signed types automatically):

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "
from _md_deploy import connect; sf=connect()
o = sf.query(\"SELECT Id, Name, PAL_Signed_Date__c, EMA_Signed_Date__c, Bulk_Signed_Date__c FROM Opportunity WHERE PAL_Signed_Date__c!=null AND EMA_Signed_Date__c!=null LIMIT 1\")['records']
if not o: print('no opp with both PAL+EMA signed; check PAL-only instead'); raise SystemExit
o=o[0]; print('OPP', o['Name'], {k:o[k] for k in ('PAL_Signed_Date__c','EMA_Signed_Date__c','Bulk_Signed_Date__c')})
for a in sf.query(f\"SELECT Agreement_Type__c, Signed_Date__c, Status__c FROM Agreement__c WHERE Opportunity__c='{o['Id']}'\")['records']:
    print('   AGR', a['Agreement_Type__c'], a['Signed_Date__c'], a['Status__c'])
"
```

Expected: each rollup date equals the MAX `Signed_Date__c` among that opp's signed children of the matching type.

- [ ] **Step 5: Commit**

```bash
git add SalesForce/scripts/deploy/2026-06-17-add-opp-milestone-date-rollups.py
git commit -m "feat(sf): add five Opportunity per-type signed-date rollups"
```

---

### Task 3: Build the tabular tracker report

**Files:**
- Create: `SalesForce/scripts/deploy/2026-06-17-build-agreements-milestone-tracker-report.py`

**Interfaces:**
- Consumes: `_md_deploy.connect`, `_md_deploy.deploy`; the five Opportunity rollups (Task 2); pre-existing surfaced fields `Opportunity.ST_Build_Status__c`, `Opportunity.SiteTracker_Project_ID__c`, `Opportunity.Units__c`, `Opportunity.Property_Address__c`, `Opportunity.Property_State__c`.
- Produces (org): report `MDU_Sales_Reports/MDU_Agreements_Milestone_Tracker`.

- [ ] **Step 1: Write the report build script (with a check-only validation gate)**

Create `SalesForce/scripts/deploy/2026-06-17-build-agreements-milestone-tracker-report.py`:

```python
"""Builds the 'MDU Agreements Milestone Tracker' report: tabular, Opportunity report
type, one row per MDU opp with a signed PAL or ROE. Columns = Sales POC (Owner),
property, units, address, state, SiteTracker project #, stage, ST build status, and
the five per-type signed-date milestones. Validates check-only first, then deploys."""
from _md_deploy import connect, deploy

sf = connect()
FOLDER = "MDU_Sales_Reports"
API = "MDU_Agreements_Milestone_Tracker"

# Column dev-name tokens. Custom Opp fields are reliable as Opportunity.<API>.
# Standard columns: OPPORTUNITY_NAME, STAGE_NAME, and the Owner token.
OWNER_COL = "OPPORTUNITY.OWNER"   # if check-only rejects this, try "FULL_NAME"
COLUMNS = [
    OWNER_COL,                              # Sales POC
    "OPPORTUNITY_NAME",                     # Property
    "Opportunity.Units__c",                 # Total Units
    "Opportunity.Property_Address__c",      # Address
    "Opportunity.Property_State__c",        # State
    "Opportunity.SiteTracker_Project_ID__c",# SiteTracker project #
    "STAGE_NAME",                           # Stage (usability extra)
    "Opportunity.ST_Build_Status__c",       # ST Build Status (usability extra)
    "Opportunity.PAL_Signed_Date__c",
    "Opportunity.ROE_Signed_Date__c",
    "Opportunity.EMA_Signed_Date__c",
    "Opportunity.Bulk_Signed_Date__c",
    "Opportunity.PAL_Addendum_Signed_Date__c",
]
cols_xml = "".join(f"<columns><field>{c}</field></columns>" for c in COLUMNS)

DESC = ("MDU opportunities with a signed PAL or ROE. One row per property; agreement "
        "milestones (PAL/ROE/EMA/Bulk/PAL Addendum signed dates) as columns. "
        "Signed = Status Completed/Cancelled + Signed Date. All time.")

REPORT = f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://soap.sforce.com/2006/04/metadata">
    <name>MDU Agreements Milestone Tracker</name>
    <description>{DESC}</description>
    <reportType>Opportunity</reportType>
    <format>Tabular</format>
    <scope>organization</scope>
    {cols_xml}
    <timeFrameFilter><dateColumn>CLOSE_DATE</dateColumn><interval>INTERVAL_CUSTOM</interval></timeFrameFilter>
    <filter>
        <booleanFilter>1 AND (2 OR 3)</booleanFilter>
        <criteriaItems><column>RECORDTYPE</column><operator>equals</operator><value>Opportunity.MDU</value></criteriaItems>
        <criteriaItems><column>Opportunity.PAL_Signed_Date__c</column><operator>notEqual</operator><value></value></criteriaItems>
        <criteriaItems><column>Opportunity.ROE_Signed_Date__c</column><operator>notEqual</operator><value></value></criteriaItems>
    </filter>
</Report>"""

files = {f"reports/{FOLDER}/{API}.report": REPORT}
members = [(f"{FOLDER}/{API}", "Report")]

# Validate first (check-only). If the OWNER column token is rejected, the failure
# names it — switch OWNER_COL to "FULL_NAME" and re-run.
print("Check-only validation...")
if not deploy(sf, files, members, "report-check", check_only=True):
    raise SystemExit("Validation failed — fix the column token above and re-run.")
print("Validation OK. Deploying for real...")
if not deploy(sf, files, members, "report-deploy"):
    raise SystemExit(1)
print("Report deployed.")
```

- [ ] **Step 2: Run validation + deploy**

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-build-agreements-milestone-tracker-report.py
```

Expected: `[report-check] poll N: Succeeded`, then `[report-deploy] poll N: Succeeded`, `Report deployed.`
If `[report-check]` prints `FAIL: MDU_Agreements_Milestone_Tracker - ... OPPORTUNITY.OWNER ...`, edit `OWNER_COL = "FULL_NAME"` in the script and re-run.

- [ ] **Step 3: Verify the report population reconciles to the rollups**

Run:

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "
import requests
from _md_deploy import connect; sf=connect()
rid = sf.query(\"SELECT Id FROM Report WHERE DeveloperName='MDU_Agreements_Milestone_Tracker'\")['records'][0]['Id']
j = requests.get(sf.base_url+f'analytics/reports/{rid}', headers={'Authorization':f'Bearer {sf.session_id}'}).json()
report_total = j['factMap']['T!T']['aggregates'][0]['value']
soql = sf.query(\"SELECT COUNT(Id) c FROM Opportunity WHERE RecordType.DeveloperName='MDU' AND (PAL_Signed_Date__c!=null OR ROE_Signed_Date__c!=null)\")['records'][0]['c']
print('report grand total:', report_total, '| SOQL count:', soql, '| ballpark ~447')
assert report_total == soql, 'report population != rollup population'
print('OK: report reconciles.')
"
```

Expected: report grand total == SOQL count, both in the ballpark of ~447. Ends `OK: report reconciles.`

- [ ] **Step 4: Eyeball the report in the UI**

Open the report in Salesforce (MDU Sales Reports folder → "MDU Agreements Milestone Tracker"). Confirm: Owner shows as Sales POC; the five date columns render with dates; address/state/units/ST project # populate; row count matches Step 3.

- [ ] **Step 5: Commit**

```bash
git add SalesForce/scripts/deploy/2026-06-17-build-agreements-milestone-tracker-report.py
git commit -m "feat(sf): build MDU Agreements Milestone Tracker report"
```

> **The core tracker is shippable after Task 3.** Tasks 4–7 add the two contact columns
> (Property Manager / Property Owner). Note the data reality: only ~16% of these opps have any
> contact attached, so the columns are mostly blank today and double as a backfill prompt.

---

### Task 4: Contact fields (two Opportunity text fields + junction formula)

**Files:**
- Create: `SalesForce/scripts/deploy/2026-06-17-add-contact-rollup-fields.py`

**Interfaces:**
- Consumes: `_md_deploy.connect`, `_md_deploy.deploy`.
- Produces (org):
  - `Opportunity.Property_Manager_Contact__c` — Text(255).
  - `Opportunity.Property_Owner_Contact__c` — Text(255).
  - `Opportunity_Contact__c.Contact_Name__c` — formula Text = `Contact__r.Name`.
  - Consumed by the Flow (Task 5), the backfill (Task 6), and the report (Task 7).

- [ ] **Step 1: Verify the fields are ABSENT first**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "from _md_deploy import connect; sf=connect(); print('Property_Manager_Contact__c' in [f['name'] for f in sf.Opportunity.describe()['fields']], 'Contact_Name__c' in [f['name'] for f in sf.Opportunity_Contact__c.describe()['fields']])"
```

Expected: `False False`.

- [ ] **Step 2: Write the field deploy script**

Create `SalesForce/scripts/deploy/2026-06-17-add-contact-rollup-fields.py`:

```python
"""Adds the contact-rollup fields for the tracker:
  - Opportunity.Property_Manager_Contact__c / Property_Owner_Contact__c (Text 255)
  - Opportunity_Contact__c.Contact_Name__c (formula = Contact__r.Name)
Deployed as granular CustomField members so no object header is touched (avoids
resetting the junction's master-detail sharing model). Additive."""
from _md_deploy import connect, deploy

sf = connect()

OPP_FIELDS = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Property_Manager_Contact__c</fullName>
        <label>Property Manager</label>
        <type>Text</type>
        <length>255</length>
        <description>Comma-joined names of Property Manager contacts on this Opportunity. Maintained by the Opp Contact Role Rollup flow + the backfill script.</description>
    </fields>
    <fields>
        <fullName>Property_Owner_Contact__c</fullName>
        <label>Property Owner</label>
        <type>Text</type>
        <length>255</length>
        <description>Comma-joined names of Property Owner contacts on this Opportunity. Maintained by the Opp Contact Role Rollup flow + the backfill script.</description>
    </fields>
</CustomObject>"""

OC_FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
    <fields>
        <fullName>Contact_Name__c</fullName>
        <label>Contact Name</label>
        <type>Text</type>
        <formula>Contact__r.Name</formula>
        <description>Contact name surfaced onto the junction so the role-rollup flow needs no cross-object access.</description>
    </fields>
</CustomObject>"""

files = {
    "objects/Opportunity.object": OPP_FIELDS,
    "objects/Opportunity_Contact__c.object": OC_FIELD,
}
members = [
    ("Opportunity.Property_Manager_Contact__c", "CustomField"),
    ("Opportunity.Property_Owner_Contact__c", "CustomField"),
    ("Opportunity_Contact__c.Contact_Name__c", "CustomField"),
]
if not deploy(sf, files, members, "contact-fields"):
    raise SystemExit(1)

# FLS read for the two report-visible Opportunity fields.
def fls_xml(profile_api):
    perms = "".join(
        f"<fieldPermissions><editable>false</editable><field>Opportunity.{f}</field>"
        f"<readable>true</readable></fieldPermissions>"
        for f in ["Property_Manager_Contact__c", "Property_Owner_Contact__c"])
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Profile xmlns="http://soap.sforce.com/2006/04/metadata">'
            f'{perms}</Profile>')

for prof in ["Admin", "Standard User - Custom"]:
    if not deploy(sf, {f"profiles/{prof}.profile": fls_xml(prof)}, [(prof, "Profile")], f"fls-{prof}"):
        print(f"  WARN: FLS deploy failed for '{prof}' (verify the profile name).")

# Verify the junction formula resolves to the contact's name.
sf2 = connect()
row = sf2.query("SELECT Contact_Name__c, Contact__r.Name FROM Opportunity_Contact__c WHERE Contact__c != null LIMIT 1")["records"][0]
print(f"\nVerification: Contact_Name__c={row['Contact_Name__c']!r} vs Contact.Name={row['Contact__r']['Name']!r}")
assert row["Contact_Name__c"] == row["Contact__r"]["Name"], "Contact_Name__c formula mismatch!"
print("OK: contact fields deployed; Contact_Name__c resolves correctly.")
```

- [ ] **Step 3: Run it**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-add-contact-rollup-fields.py
```

Expected: `[contact-fields] poll N: Succeeded`, both `[fls-...]` Succeeded, ends `OK: contact fields deployed; Contact_Name__c resolves correctly.`

- [ ] **Step 4: Commit**

```bash
git add SalesForce/scripts/deploy/2026-06-17-add-contact-rollup-fields.py
git commit -m "feat(sf): add contact-role fields for tracker"
```

---

### Task 5: Record-triggered Flow maintaining the contact fields

**Files:**
- Create: `SalesForce/scripts/deploy/2026-06-17-deploy-contact-role-flow.py`

**Interfaces:**
- Consumes: `_md_deploy.connect`, `_md_deploy.deploy`; the three fields from Task 4.
- Produces (org): active Flow `Opp_Contact_Role_Rollup` (record-triggered, create/update, after-save on `Opportunity_Contact__c`). Updates the parent Opportunity's two contact fields.

- [ ] **Step 1: Write the Flow deploy script**

Create `SalesForce/scripts/deploy/2026-06-17-deploy-contact-role-flow.py`:

```python
"""Deploys the Opp_Contact_Role_Rollup flow: a record-triggered (create/update),
after-save flow on Opportunity_Contact__c that re-aggregates the parent Opportunity's
Property_Manager_Contact__c / Property_Owner_Contact__c from all sibling junctions by
role. Validates check-only first, then deploys active. Delete handling is intentionally
omitted (rare; resync via the backfill script)."""
from _md_deploy import connect, deploy

sf = connect()

FLOW = """<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>59.0</apiVersion>
    <description>Maintains Opportunity Property_Manager_Contact__c / Property_Owner_Contact__c by re-aggregating its Opportunity_Contact__c children by role. Fires after a junction is created or updated.</description>
    <interviewLabel>Opp Contact Role Rollup {!$Flow.CurrentDateTime}</interviewLabel>
    <label>Opp Contact Role Rollup</label>
    <processType>AutoLaunchedFlow</processType>
    <status>Active</status>
    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector><targetReference>Get_Siblings</targetReference></connector>
        <object>Opportunity_Contact__c</object>
        <recordTriggerType>CreateAndUpdate</recordTriggerType>
        <triggerType>RecordAfterSave</triggerType>
    </start>
    <recordLookups>
        <name>Get_Siblings</name>
        <label>Get Siblings</label>
        <locationX>50</locationX>
        <locationY>100</locationY>
        <assignNullValuesIfNoRecordsFound>false</assignNullValuesIfNoRecordsFound>
        <connector><targetReference>Loop_Siblings</targetReference></connector>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Opportunity__c</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </filters>
        <getFirstRecordOnly>false</getFirstRecordOnly>
        <object>Opportunity_Contact__c</object>
        <storeOutputAutomatically>true</storeOutputAutomatically>
    </recordLookups>
    <loops>
        <name>Loop_Siblings</name>
        <label>Loop Siblings</label>
        <locationX>50</locationX>
        <locationY>200</locationY>
        <collectionReference>Get_Siblings</collectionReference>
        <iterationOrder>Asc</iterationOrder>
        <nextValueConnector><targetReference>Check_Role</targetReference></nextValueConnector>
        <noMoreValuesConnector><targetReference>Update_Opp</targetReference></noMoreValuesConnector>
    </loops>
    <decisions>
        <name>Check_Role</name>
        <label>Check Role</label>
        <locationX>200</locationX>
        <locationY>200</locationY>
        <defaultConnector><targetReference>Loop_Siblings</targetReference></defaultConnector>
        <defaultConnectorLabel>Other</defaultConnectorLabel>
        <rules>
            <name>Is_Manager</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>Loop_Siblings.Role__c</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue><stringValue>Property Manager</stringValue></rightValue>
            </conditions>
            <connector><targetReference>Append_Manager</targetReference></connector>
            <label>Is Manager</label>
        </rules>
        <rules>
            <name>Is_Owner</name>
            <conditionLogic>and</conditionLogic>
            <conditions>
                <leftValueReference>Loop_Siblings.Role__c</leftValueReference>
                <operator>EqualTo</operator>
                <rightValue><stringValue>Property Owner</stringValue></rightValue>
            </conditions>
            <connector><targetReference>Append_Owner</targetReference></connector>
            <label>Is Owner</label>
        </rules>
    </decisions>
    <assignments>
        <name>Append_Manager</name>
        <label>Append Manager</label>
        <locationX>350</locationX>
        <locationY>150</locationY>
        <assignmentItems>
            <assignToReference>varManagers</assignToReference>
            <operator>Add</operator>
            <value><stringValue>, </stringValue></value>
        </assignmentItems>
        <assignmentItems>
            <assignToReference>varManagers</assignToReference>
            <operator>Add</operator>
            <value><elementReference>Loop_Siblings.Contact_Name__c</elementReference></value>
        </assignmentItems>
        <connector><targetReference>Loop_Siblings</targetReference></connector>
    </assignments>
    <assignments>
        <name>Append_Owner</name>
        <label>Append Owner</label>
        <locationX>350</locationX>
        <locationY>250</locationY>
        <assignmentItems>
            <assignToReference>varOwners</assignToReference>
            <operator>Add</operator>
            <value><stringValue>, </stringValue></value>
        </assignmentItems>
        <assignmentItems>
            <assignToReference>varOwners</assignToReference>
            <operator>Add</operator>
            <value><elementReference>Loop_Siblings.Contact_Name__c</elementReference></value>
        </assignmentItems>
        <connector><targetReference>Loop_Siblings</targetReference></connector>
    </assignments>
    <recordUpdates>
        <name>Update_Opp</name>
        <label>Update Opp</label>
        <locationX>50</locationX>
        <locationY>300</locationY>
        <filterLogic>and</filterLogic>
        <filters>
            <field>Id</field>
            <operator>EqualTo</operator>
            <value><elementReference>$Record.Opportunity__c</elementReference></value>
        </filters>
        <inputAssignments>
            <field>Property_Manager_Contact__c</field>
            <value><elementReference>fxTrimManagers</elementReference></value>
        </inputAssignments>
        <inputAssignments>
            <field>Property_Owner_Contact__c</field>
            <value><elementReference>fxTrimOwners</elementReference></value>
        </inputAssignments>
        <object>Opportunity</object>
    </recordUpdates>
    <variables>
        <name>varManagers</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
        <value><stringValue></stringValue></value>
    </variables>
    <variables>
        <name>varOwners</name>
        <dataType>String</dataType>
        <isCollection>false</isCollection>
        <isInput>false</isInput>
        <isOutput>false</isOutput>
        <value><stringValue></stringValue></value>
    </variables>
    <formulas>
        <name>fxTrimManagers</name>
        <dataType>String</dataType>
        <expression>IF(LEN({!varManagers}) &gt; 0, MID({!varManagers}, 3, LEN({!varManagers})), "")</expression>
    </formulas>
    <formulas>
        <name>fxTrimOwners</name>
        <dataType>String</dataType>
        <expression>IF(LEN({!varOwners}) &gt; 0, MID({!varOwners}, 3, LEN({!varOwners})), "")</expression>
    </formulas>
</Flow>"""

files = {"flows/Opp_Contact_Role_Rollup.flow": FLOW}
members = [("Opp_Contact_Role_Rollup", "Flow")]

print("Check-only validation...")
if not deploy(sf, files, members, "flow-check", check_only=True):
    raise SystemExit("Flow validation failed — fix the reported element above and re-run.")
print("Validation OK. Deploying active flow...")
if not deploy(sf, files, members, "flow-deploy"):
    raise SystemExit(1)
print("Flow deployed and active.")
```

- [ ] **Step 2: Validate + deploy the Flow**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-deploy-contact-role-flow.py
```

Expected: `[flow-check] poll N: Succeeded`, then `[flow-deploy] poll N: Succeeded`, `Flow deployed and active.`
If check-only fails, the `FAIL:` line names the offending element — fix it in `FLOW` and re-run.

- [ ] **Step 3: Functionally test the Flow (create → verify → clean up)**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python -c "
from _md_deploy import connect; sf=connect()
opp = sf.query(\"SELECT Id, Name, Property_Manager_Contact__c FROM Opportunity WHERE RecordType.DeveloperName='MDU' AND Property_Manager_Contact__c=null LIMIT 1\")['records'][0]
con = sf.query('SELECT Id, Name FROM Contact LIMIT 1')['records'][0]
prior = opp['Property_Manager_Contact__c']
print('test opp:', opp['Name'], '| prior PM field:', prior, '| test contact:', con['Name'])
oc = sf.Opportunity_Contact__c.create({'Opportunity__c': opp['Id'], 'Contact__c': con['Id'], 'Role__c': 'Property Manager'})
after = sf.Opportunity.get(opp['Id'])['Property_Manager_Contact__c']
print('after create, PM field:', after)
assert after and con['Name'] in after, 'Flow did not populate the parent field!'
# cleanup: delete the test junction and restore the field to its prior value
sf.Opportunity_Contact__c.delete(oc['id'])
sf.Opportunity.update(opp['Id'], {'Property_Manager_Contact__c': prior or ''})
print('OK: Flow populated the parent field; test junction removed and field restored.')
"
```

Expected: `after create, PM field:` contains the test contact's name, then `OK: Flow populated the parent field; test junction removed and field restored.`

- [ ] **Step 4: Commit**

```bash
git add SalesForce/scripts/deploy/2026-06-17-deploy-contact-role-flow.py
git commit -m "feat(sf): add Opp Contact Role Rollup flow"
```

---

### Task 6: Backfill / resync existing opps

**Files:**
- Create: `SalesForce/scripts/fix/2026-06-17-backfill-opp-contact-roles.py`

**Interfaces:**
- Consumes: `simple_salesforce` (inline connect — `scripts/fix/` peers don't import the deploy helper). The Task-4 fields + Task-5 Flow must already exist.
- Produces: populated `Property_Manager_Contact__c` / `Property_Owner_Contact__c` on existing opps (~72 expected) + an audit CSV. Dry-run by default; `--apply` to write.

- [ ] **Step 1: Write the backfill script**

Create `SalesForce/scripts/fix/2026-06-17-backfill-opp-contact-roles.py`:

```python
"""Backfill / resync Opportunity.Property_Manager_Contact__c & Property_Owner_Contact__c
from Opportunity_Contact__c by role. The Flow only fires on future junction edits, so
this populates existing opps and is the resync tool after a contact is removed.
Dry-run by default (prints planned changes); pass --apply to write + log an audit CSV.
Caution per Koa's sync rule: preview before applying."""
import sys, csv
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from simple_salesforce import Salesforce

APPLY = "--apply" in sys.argv
sf = Salesforce(username="cass1@ubiquitygp.com", password="<password: see _shared/sf_auth.py>",
                security_token="<token: see _shared/sf_auth.py>")

def query_all(soql):
    out, r = [], sf.query(soql)
    out.extend(r["records"])
    while not r["done"]:
        r = sf.query_more(r["nextRecordsUrl"], True); out.extend(r["records"])
    return out

# Desired values from junctions, grouped by opp + role.
mgr, own = defaultdict(list), defaultdict(list)
for rec in query_all("SELECT Opportunity__c, Role__c, Contact_Name__c FROM Opportunity_Contact__c WHERE Opportunity__c != null"):
    name = (rec.get("Contact_Name__c") or "").strip()
    if not name:
        continue
    if rec["Role__c"] == "Property Manager":
        mgr[rec["Opportunity__c"]].append(name)
    elif rec["Role__c"] == "Property Owner":
        own[rec["Opportunity__c"]].append(name)

desired = {}  # opp_id -> (mgr_str, own_str)
for oid in set(mgr) | set(own):
    desired[oid] = (", ".join(mgr.get(oid, [])), ", ".join(own.get(oid, [])))

# Current field values (include opps already set, to catch stale that need clearing).
ids = set(desired)
current = {}
for rec in query_all("SELECT Id, Name, Property_Manager_Contact__c, Property_Owner_Contact__c "
                     "FROM Opportunity WHERE Property_Manager_Contact__c != null "
                     "OR Property_Owner_Contact__c != null"):
    current[rec["Id"]] = rec
    ids.add(rec["Id"])

# Build the change list.
changes = []  # (id, name, field, before, after)
names = {}
for rec in query_all("SELECT Id, Name FROM Opportunity WHERE Id IN ('%s')" % "','".join(ids)) if ids else []:
    names[rec["Id"]] = rec["Name"]
for oid in ids:
    want_m, want_o = desired.get(oid, ("", ""))
    cur = current.get(oid, {})
    have_m = cur.get("Property_Manager_Contact__c") or ""
    have_o = cur.get("Property_Owner_Contact__c") or ""
    nm = names.get(oid, oid)
    if want_m != have_m:
        changes.append((oid, nm, "Property_Manager_Contact__c", have_m, want_m))
    if want_o != have_o:
        changes.append((oid, nm, "Property_Owner_Contact__c", have_o, want_o))

print(f"Opps with contacts: {len(desired)} | planned field changes: {len(changes)}")
for c in changes[:25]:
    print(f"  {c[1][:32]:<32} {c[2].split('_')[1]:<8} {c[3]!r} -> {c[4]!r}")
if len(changes) > 25:
    print(f"  ... and {len(changes) - 25} more")

if not APPLY:
    print("\nDRY RUN. Re-run with --apply to write these changes.")
    raise SystemExit(0)

# Apply: group changes per opp into one update each.
per_opp = defaultdict(dict)
for oid, _, field, _, after in changes:
    per_opp[oid][field] = after
ok = 0
for oid, fields in per_opp.items():
    sf.Opportunity.update(oid, fields); ok += 1

# Audit log.
base = Path(__file__).resolve().parents[2] / "data" / "output" / "audit_logs"
base.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
path = base / f"{datetime.now():%Y-%m-%d_%H%M%S}-contact-role-backfill.csv"
with path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SF_Id", "Name", "Field", "Before", "After", "Source", "Timestamp", "Action"])
    for oid, nm, field, before, after in changes:
        w.writerow([oid, nm, field, before, after,
                    "scripts/fix/2026-06-17-backfill-opp-contact-roles.py", ts, "update"])
print(f"\nApplied {ok} opp update(s). Audit: {path}")
```

- [ ] **Step 2: Dry-run, review the preview**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/fix
python 2026-06-17-backfill-opp-contact-roles.py
```

Expected: `Opps with contacts: ~72 | planned field changes: N`, a sample of `Manager`/`Owner` before→after lines, ending `DRY RUN. Re-run with --apply to write these changes.` Eyeball that the names look right.

- [ ] **Step 3: Apply the backfill**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/fix
python 2026-06-17-backfill-opp-contact-roles.py --apply
```

Expected: `Applied ~72 opp update(s). Audit: ...contact-role-backfill.csv`.

- [ ] **Step 4: Verify population**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/fix
python -c "
from simple_salesforce import Salesforce
sf=Salesforce(username='cass1@ubiquitygp.com', password='<password: see _shared/sf_auth.py>', security_token='<token: see _shared/sf_auth.py>')
def c(q): return sf.query(q)['records'][0]['c']
print('opps with PM name:', c('SELECT COUNT(Id) c FROM Opportunity WHERE Property_Manager_Contact__c != null'))
print('opps with Owner name:', c('SELECT COUNT(Id) c FROM Opportunity WHERE Property_Owner_Contact__c != null'))
"
```

Expected: non-zero counts consistent with the ~72 populated opps.

- [ ] **Step 5: Commit**

```bash
git add SalesForce/scripts/fix/2026-06-17-backfill-opp-contact-roles.py
git commit -m "fix(sf): backfill/resync Opportunity contact-role fields"
```

---

### Task 7: Add the two contact columns to the report

**Files:**
- Modify: `SalesForce/scripts/deploy/2026-06-17-build-agreements-milestone-tracker-report.py`

**Interfaces:**
- Consumes: the report from Task 3; the two Opportunity contact fields from Task 4.
- Produces: the report re-deployed with Property Manager + Property Owner columns after Sales POC.

- [ ] **Step 1: Insert the two contact columns into the report's COLUMNS list**

Edit `2026-06-17-build-agreements-milestone-tracker-report.py` — change the `COLUMNS` list so the two contact fields sit right after the Owner column:

```python
COLUMNS = [
    OWNER_COL,                                  # Sales POC
    "Opportunity.Property_Manager_Contact__c",  # Property Manager
    "Opportunity.Property_Owner_Contact__c",    # Property Owner
    "OPPORTUNITY_NAME",                         # Property
    "Opportunity.Units__c",                     # Total Units
    "Opportunity.Property_Address__c",          # Address
    "Opportunity.Property_State__c",            # State
    "Opportunity.SiteTracker_Project_ID__c",    # SiteTracker project #
    "STAGE_NAME",                               # Stage (usability extra)
    "Opportunity.ST_Build_Status__c",           # ST Build Status (usability extra)
    "Opportunity.PAL_Signed_Date__c",
    "Opportunity.ROE_Signed_Date__c",
    "Opportunity.EMA_Signed_Date__c",
    "Opportunity.Bulk_Signed_Date__c",
    "Opportunity.PAL_Addendum_Signed_Date__c",
]
```

- [ ] **Step 2: Re-run the report build (idempotent redeploy)**

```bash
cd /c/Users/cass/Work_Projects/SalesForce/scripts/deploy
python 2026-06-17-build-agreements-milestone-tracker-report.py
```

Expected: `[report-check] poll N: Succeeded`, `[report-deploy] poll N: Succeeded`, `Report deployed.` (Row count is unchanged from Task 3 — only columns changed.)

- [ ] **Step 3: Eyeball the report**

Open the report in Salesforce; confirm the two new columns (Property Manager, Property Owner) appear after Sales POC and are populated for the backfilled opps (blank for the rest).

- [ ] **Step 4: Commit**

```bash
git add SalesForce/scripts/deploy/2026-06-17-build-agreements-milestone-tracker-report.py
git commit -m "feat(sf): add contact columns to MDU Agreements Milestone Tracker"
```

---

## Self-Review

**Spec coverage:**
- Sales POC → Owner column (Task 3). ✓
- Total units / Address / State / SiteTracker project # → existing Opp fields as columns (Task 3). ✓
- PAL, ROE, EMA, Bulk, PAL Addendum signed dates → five rollups (Task 2) + columns (Task 3). ✓ (PAL & ROE separate, per Koa.)
- Filter "where we have Signed PAL/ROE" → `RecordType=MDU AND (PAL date OR ROE date not blank)` (Task 3). ✓
- Taylor's signed definition → `Is_Signed__c` (Task 1). ✓
- Reconcile to Taylor's census → Task 3 Step 3. ✓
- `enableReports` foot-gun → baked into Task 1 header + Step 4 guard. ✓
- Contacts (Property Manager / Property Owner) → fields (Task 4) + Flow (Task 5) + backfill (Task 6) + columns (Task 7). ✓ (two role columns, native Flow, per Koa.)
- FLS to MDU team → Task 2 Step 2 (date fields) + Task 4 Step 2 (contact fields). ✓
- Design Phase completion date → **deferred to v2 by design** (spec §v2). Not in this plan. ✓ (intentional gap)
- Contact removal auto-clear → **intentionally out of Flow** (YAGNI; resync via Task 6 backfill). ✓ (documented gap)

**Placeholder scan:** No TBD/TODO. Two conditionals are concrete deterministic branches, not placeholders: `OWNER_COL` fallback to `FULL_NAME` (driven by check-only output) and the Flow's check-only gate.

**Type consistency:** Date-field API names identical across Tasks 2/3 (`PAL_Signed_Date__c`, `ROE_Signed_Date__c`, `EMA_Signed_Date__c`, `Bulk_Signed_Date__c`, `PAL_Addendum_Signed_Date__c`). Contact-field names identical across Tasks 4/5/6/7 (`Property_Manager_Contact__c`, `Property_Owner_Contact__c`, `Opportunity_Contact__c.Contact_Name__c`). Flow `Opp_Contact_Role_Rollup` references those exact fields; role literals `Property Manager` / `Property Owner` match the picklist + the backfill. `Is_Signed__c` defined in Task 1, consumed by Task 2 filters. `deploy(sf, files, members_types, label, check_only)` signature consistent across all call sites (now grouping members by type).

## Deferred (v2 — separate plan)

Design Phase completion date: confirm the design-milestone field on `MDU_Fiber__c` in the SiteTracker org → add `Design_Complete_Date__c` to the `SiteTracker_Project__c` mirror → add to `sync_sitetracker.py` query + upsert → surface to the Opp via `surface_to_opportunity.py` (Automation repo) → add the column to this report. Sequenced after v1 ships.
