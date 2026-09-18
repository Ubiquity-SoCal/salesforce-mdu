"""
Curated Salesforce -> HubSpot record export (Kia Zaman's 9/14 ask, part 1).

Kia asked for a full production export of every in-scope object: one row per record,
every field, with record, parent, owner and relationship IDs kept. A raw Setup > Data
Export would give her that as 400+ unlabeled files that walk straight into the traps
below. This builds the import-ready set instead, and it is rerunnable: run it again at
cutover for the final pull. Note bodies and files are cached by ContentVersion Id (a
version never changes once written), so a rerun only downloads new or edited notes.

What it does beyond a raw dump (decided with Koa 9/14; numbers from
scripts/_probes/2026-09-14-hubspot-export-sizing.py):
  - Adds the three junctions Kia's list left out. Opportunity_Contact__c is the ONLY
    thing connecting a contact to a deal (OpportunityContactRole has 1 row), and
    Opportunity_Campaign__c is the real campaign membership (CampaignMember has 0).
  - Adds User, Queue, RecordType and OpportunityStage so every OwnerId and RecordTypeId
    resolves. 70% of opportunities belong to deactivated users.
  - Excludes Business Sales (RecordType DeveloperName 'Business', out of scope since
    8/31) at source, with its owned children. Business ROE is a different record type
    and stays. Accounts and contacts are only dropped if nothing kept still points at them.
  - Tasks and Events via queryAll, so archived activity (a normal query skips it) is in.
  - Note bodies as text. They are not in any SOQL result, each is its own download.
  - EXPORT_* helper columns: owner and record type names beside the IDs, polymorphic
    target types, and the HubSpot dedupe collisions.

Then it checks itself and exits non-zero if any check fails:
  - fetched == org COUNT(), per object
  - every row received every field chunk (fields are fetched 80 at a time, merged by Id)
  - every Id is 18 characters and unique in its file
  - every reference resolves inside the export, points at an excluded Business Sales
    record, points at an object deliberately not sent, or no longer exists in Salesforce.
    A reference to a record that DOES exist, of a type we DID send, that is not in the
    export is a hard failure: a linked record was lost.

Run:  python -u export_hubspot_records.py               full run, zips on success
      python -u export_hubspot_records.py --skip-files  records only, no downloads
Out:  SalesForce/data/output/hubspot-export/<YYYY-MM-DD>/ and a .zip beside it.
      data/output is gitignored. This is contact PII: never force-add it.
"""
import argparse
import csv
import json
import re
import shutil
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests

sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import get_sf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "data" / "output" / "hubspot-export"
CACHE = ROOT / "_cache"

BUSINESS_SALES_DEV = "Business"
BUSINESS_SALES_NAME = "Business Sales"

RECORD_OBJECTS = [
    "Opportunity", "Agreement__c", "Contact", "Account", "Campaign", "CampaignMember",
    "Case", "AVR_Project_ID__c", "Property_Location__c", "Property_Unit__c",
    "SiteTracker_Project__c",
    "Opportunity_Contact__c", "Opportunity_Account__c", "Opportunity_Campaign__c",
    "Task", "Event", "EmailMessage", "Note", "OpportunityHistory",
]
QUERY_ALL = {"Task", "Event"}

# Rows that belong to a Business Sales opportunity and go with it. Only owning
# relationships are listed: a Case or Property Location that merely looks up to a
# Business Sales opp is in scope on its own and stays (the relationship check reports it).
BS_CHILDREN = [
    ("Agreement__c", "Opportunity__c"),
    ("Opportunity_Contact__c", "Opportunity__c"),
    ("Opportunity_Account__c", "Opportunity__c"),
    ("Opportunity_Campaign__c", "Opportunity__c"),
    ("OpportunityHistory", "OpportunityId"),
    ("Task", "WhatId"),
    ("Event", "WhatId"),
    ("EmailMessage", "RelatedToId"),
    ("Note", "ParentId"),
]

# Salesforce Files / notes can hang off any of these. Task and Event do not support the
# semi-join and carry no files in this org.
LINK_OBJECTS = [o for o in RECORD_OBJECTS if o not in ("Task", "Event", "CampaignMember", "OpportunityHistory")]

GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "aol.com", "hotmail.com", "outlook.com", "icloud.com", "me.com",
    "msn.com", "live.com", "comcast.net", "cox.net", "att.net", "sbcglobal.net", "verizon.net",
    "earthlink.net", "charter.net", "facebook.com", "linkedin.com", "instagram.com", "yelp.com",
    "google.com", "sites.google.com",
}

MANIFEST_NOTES = {
    "Opportunity": "Business Sales record type excluded (out of scope). Business ROE is a different record type and is included.",
    "Opportunity_Contact__c": "How contacts attach to opportunities. Role__c says Property Owner / Property Manager. OpportunityContactRole is not used in this org.",
    "Opportunity_Account__c": "Extra account (management company) links beyond Opportunity.AccountId.",
    "Opportunity_Campaign__c": "Campaign membership. CampaignMember is empty in this org.",
    "CampaignMember": "Empty in Salesforce. Campaign membership lives in Opportunity_Campaign__c.",
    "Contact": "EXPORT_SameEmailCount above 1: HubSpot matches contacts on email, so these merge into one contact on import.",
    "Account": "EXPORT_SameDomainCount above 1: these become one company if Website is mapped to Company domain name. EXPORT_DomainIsGeneric flags gmail, aol, facebook and similar.",
    "Task": "Includes archived tasks, which a standard export leaves out.",
    "Event": "Includes archived events, which a standard export leaves out.",
    "OpportunityHistory": "Stage history, one row per stage change.",
    "User": "Every OwnerId, CreatedById and LastModifiedById resolves here. EXPORT_OpportunitiesOwned counts exported opportunities per user, deactivated users included.",
    "Queue": "Queues that can own records (OwnerId starting 00G).",
    "BusinessProcess": "Sales processes. RecordType.BusinessProcessId resolves here; it decides which stages a record type offers.",
    "Notes": "Salesforce notes with the body as plain text and HTML. Linked records are in ContentDocumentLink.csv.",
    "Files": "Real files (not notes). The binary is in files/<ContentDocumentId>/.",
    "ContentDocumentLink": "Which record each note is attached to. One note can sit on several records.",
    "Attachment": "Classic attachments, all on email messages. Binary in attachments/<Id>/.",
}


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


class Ctx:
    def __init__(self, sf):
        self.sf = sf
        self.desc = {}
        self.prefix = {s["keyPrefix"]: s["name"] for s in sf.describe()["sobjects"] if s.get("keyPrefix")}

    def describe(self, obj):
        if obj not in self.desc:
            self.desc[obj] = getattr(self.sf, obj).describe()
        return self.desc[obj]

    def type_of(self, rid):
        return self.prefix.get((rid or "")[:3], "") if rid else ""


def cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def fetch(ctx, obj, cutoff):
    """All exportable fields of obj, 80 per query, merged by Id. Returns rows, field
    names, and the Ids that did not come back in every chunk."""
    d = ctx.describe(obj)
    names = [f["name"] for f in d["fields"] if f["type"] not in ("address", "location", "base64")]
    names = ["Id"] + [n for n in names if n != "Id"]
    chunks = [names[i:i + 80] for i in range(0, len(names), 80)]
    where = f"CreatedDate <= {cutoff}"
    if obj in QUERY_ALL:
        where = f"IsDeleted = false AND {where}"
    rows, hits = {}, Counter()
    for chunk in chunks:
        soql = f"SELECT {', '.join(dict.fromkeys(['Id'] + chunk))} FROM {obj} WHERE {where}"
        for r in ctx.sf.query_all_iter(soql, include_deleted=obj in QUERY_ALL):
            rows.setdefault(r["Id"], {}).update({k: v for k, v in r.items() if k != "attributes"})
            hits[r["Id"]] += 1
    incomplete = [rid for rid, n in hits.items() if n != len(chunks)]
    org = ctx.sf.query(f"SELECT COUNT() FROM {obj} WHERE {where}", include_deleted=obj in QUERY_ALL)["totalSize"]
    return rows, names, incomplete, org


def domain_of(website):
    w = (website or "").strip().lower()
    w = re.sub(r"^[a-z]+://", "", w)
    w = re.sub(r"^www\.", "", w)
    return w.split("/")[0].split("?")[0].strip()


BLOCK_RE = re.compile(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)\b[^>]*>")
LI_RE = re.compile(r"(?i)<\s*li\b[^>]*>")
TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(h):
    t = LI_RE.sub("- ", BLOCK_RE.sub("\n", h or ""))
    t = unescape(TAG_RE.sub("", t))
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def safe_name(name, ext=""):
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "file").strip(" .") or "file"
    n = n[:120]
    if ext and not n.lower().endswith("." + ext.lower()):
        n += "." + ext
    return n


_local = threading.local()


def _session(sf):
    """One keep-alive session per worker thread. A bare requests.get per file opened a
    fresh TLS connection every time and crawled at ~3 files/s on the first run."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {sf.session_id}"
        _local.s = s
    return s


def download(sf, jobs, workers=16):
    """jobs: {cache_path: url_suffix}. Downloads what is not cached. Returns failures."""
    todo = {p: u for p, u in jobs.items() if not p.exists()}
    if not todo:
        return []
    log(f"  downloading {len(todo)} (cached {len(jobs) - len(todo)})")
    t0 = time.time()

    def one(path, suffix):
        for attempt in range(3):
            try:
                r = _session(sf).get(sf.base_url + suffix, timeout=60)
                if r.status_code == 200:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(path.suffix + ".part")
                    tmp.write_bytes(r.content)
                    tmp.replace(path)
                    return None
                err = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                err = str(e)[:80]
            time.sleep(2 * (attempt + 1))
        return (str(path.name), err)

    fails, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, p, u) for p, u in todo.items()]
        for f in as_completed(futs):
            res = f.result()
            if res:
                fails.append(res)
            done += 1
            if done % 1000 == 0:
                log(f"    {done}/{len(todo)} ({done / (time.time() - t0):.0f}/s, {len(fails)} failed)")
    return fails


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([cell(r.get(h)) for h in header])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-files", action="store_true", help="no note bodies, files or attachments")
    # Koa 9/14: files and email attachments do not go to Kia. The signed ROEs among them are
    # already in IronClad and the rest were mostly email logos. Notes still go.
    ap.add_argument("--include-files", action="store_true", help="also export Salesforce files and email attachments")
    args = ap.parse_args()

    run_at = datetime.now(timezone.utc).replace(microsecond=0)
    cutoff = run_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = ROOT / run_at.astimezone().strftime("%Y-%m-%d")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    sf = get_sf()
    ctx = Ctx(sf)
    log(f"connected {sf.sf_instance}, cutoff {cutoff}, out {out}")
    failures = []

    # ---------------- reference tables ----------------
    rts = {r["Id"]: r for r in sf.query_all(
        "SELECT Id, SobjectType, Name, DeveloperName, IsActive, BusinessProcessId, Description FROM RecordType")["records"]}
    bs = [r for r in rts.values() if r["SobjectType"] == "Opportunity" and r["DeveloperName"] == BUSINESS_SALES_DEV]
    if len(bs) != 1 or bs[0]["Name"] != BUSINESS_SALES_NAME:
        raise SystemExit(f"Business Sales record type not found as expected: {[(r['Name'], r['DeveloperName']) for r in bs]}")
    bs_rt = bs[0]["Id"]

    users = {}
    for r in sf.query_all_iter("SELECT Id, Name, FirstName, LastName, Username, Email, IsActive, UserType, Title, "
                               "Department, Profile.Name, UserRole.Name, CreatedDate, LastLoginDate FROM User"):
        r.pop("attributes", None)
        r["EXPORT_ProfileName"] = (r.pop("Profile") or {}).get("Name", "")
        r["EXPORT_RoleName"] = (r.pop("UserRole") or {}).get("Name", "")
        users[r["Id"]] = r
    queues = {r["Id"]: {k: v for k, v in r.items() if k != "attributes"} for r in sf.query_all(
        "SELECT Id, Name, DeveloperName, Email, Type FROM Group WHERE Type = 'Queue'")["records"]}
    # RecordType.BusinessProcessId pointed at nothing in the export until 9/14 (caught by the
    # file verifier), so the sales processes travel too.
    processes = {r["Id"]: {k: v for k, v in r.items() if k != "attributes"} for r in sf.query_all(
        "SELECT Id, Name, TableEnumOrId, IsActive, Description FROM BusinessProcess")["records"]}
    for r in rts.values():
        r["EXPORT_SalesProcessName"] = (processes.get(r.get("BusinessProcessId")) or {}).get("Name", "")
    stages = [{k: v for k, v in r.items() if k != "attributes"} for r in sf.query_all(
        "SELECT Id, ApiName, MasterLabel, IsActive, IsClosed, IsWon, DefaultProbability, "
        "ForecastCategoryName, SortOrder, Description FROM OpportunityStage ORDER BY SortOrder")["records"]]

    # ---------------- records ----------------
    data, fields, org_counts = {}, {}, {}
    for obj in RECORD_OBJECTS:
        rows, names, incomplete, org = fetch(ctx, obj, cutoff)
        data[obj], fields[obj], org_counts[obj] = rows, names, org
        log(f"{obj:26} {len(rows):6} rows, {len(names)} fields, org count {org}")
        if len(rows) != org:
            failures.append(f"{obj}: fetched {len(rows)} but Salesforce COUNT() is {org}")
        if incomplete:
            failures.append(f"{obj}: {len(incomplete)} rows missing a field chunk, e.g. {incomplete[:3]}")

    # ---------------- Business Sales exclusion ----------------
    excluded = defaultdict(dict)
    bs_opps = {i for i, r in data["Opportunity"].items() if r.get("RecordTypeId") == bs_rt}
    for i in bs_opps:
        excluded["Opportunity"][i] = "Business Sales opportunity"
    for obj, fld in BS_CHILDREN:
        for i, r in data[obj].items():
            if r.get(fld) in bs_opps:
                excluded[obj][i] = f"{fld} is a Business Sales opportunity"

    # Accounts / contacts touched by excluded rows go only if no kept row points at them.
    candidates = {"Account": set(), "Contact": set()}
    for obj, ids in excluded.items():
        for i in ids:
            for v in data[obj][i].values():
                t = ctx.type_of(v) if isinstance(v, str) and len(v) == 18 else ""
                if t in candidates:
                    candidates[t].add(v)
    referenced = set()
    for obj, rows in data.items():
        for i, r in rows.items():
            if i in excluded[obj] or i in candidates.get(obj, ()):
                continue
            referenced.update(v for v in r.values() if isinstance(v, str) and len(v) == 18)
    for obj, ids in candidates.items():
        for i in ids:
            if i in data[obj] and i not in referenced:
                excluded[obj][i] = "only linked to Business Sales opportunities"
    for obj in RECORD_OBJECTS:
        if excluded[obj]:
            log(f"  excluded {obj}: {len(excluded[obj])}")

    kept = {obj: {i: r for i, r in rows.items() if i not in excluded[obj]} for obj, rows in data.items()}

    # For our review, not Kia's: sits beside the dated folder so it never goes in the zip.
    audit = []
    for obj in RECORD_OBJECTS:
        for i, reason in excluded[obj].items():
            r = data[obj][i]
            audit.append({"object": obj, "Id": i, "Name": r.get("Name") or r.get("Subject") or "",
                          "Owner": (users.get(r.get("OwnerId")) or {}).get("Name", ""),
                          "CreatedBy": (users.get(r.get("CreatedById")) or {}).get("Name", ""),
                          "CreatedDate": r.get("CreatedDate"), "LastModifiedDate": r.get("LastModifiedDate"),
                          "AccountId": r.get("AccountId") or "", "Email": r.get("Email") or "",
                          "Website": r.get("Website") or "", "reason": reason})
    write_csv(ROOT / f"{out.name}-excluded.csv", ["object", "Id", "Name", "Owner", "CreatedBy", "CreatedDate",
                                                  "LastModifiedDate", "AccountId", "Email", "Website", "reason"], audit)

    # ---------------- helper columns ----------------
    opp_owned = Counter(r.get("OwnerId") for r in kept["Opportunity"].values())
    for u in users.values():
        u["EXPORT_OpportunitiesOwned"] = opp_owned.get(u["Id"], 0)

    extra_cols = {}
    for obj in RECORD_OBJECTS:
        d = ctx.describe(obj)
        poly = [f["name"] for f in d["fields"] if f["type"] == "reference" and len(f.get("referenceTo") or []) > 1]
        cols = []
        names = set(fields[obj])
        if "RecordTypeId" in names:
            cols.append("EXPORT_RecordTypeName")
        if "OwnerId" in names:
            cols += ["EXPORT_OwnerName", "EXPORT_OwnerIsActive"]
        if "CreatedById" in names:
            cols.append("EXPORT_CreatedByName")
        cols += [f"EXPORT_{p}_Type" for p in poly]
        for r in kept[obj].values():
            if "EXPORT_RecordTypeName" in cols:
                r["EXPORT_RecordTypeName"] = (rts.get(r.get("RecordTypeId")) or {}).get("Name", "")
            if "EXPORT_OwnerName" in cols:
                o = r.get("OwnerId")
                r["EXPORT_OwnerName"] = (users.get(o) or queues.get(o) or {}).get("Name", "")
                r["EXPORT_OwnerIsActive"] = users[o]["IsActive"] if o in users else ""
            if "EXPORT_CreatedByName" in cols:
                r["EXPORT_CreatedByName"] = (users.get(r.get("CreatedById")) or {}).get("Name", "")
            for p in poly:
                r[f"EXPORT_{p}_Type"] = ctx.type_of(r.get(p))
        extra_cols[obj] = cols

    emails = Counter((r.get("Email") or "").strip().lower() for r in kept["Contact"].values())
    for r in kept["Contact"].values():
        e = (r.get("Email") or "").strip().lower()
        r["EXPORT_SameEmailCount"] = emails[e] if e else ""
    extra_cols["Contact"].append("EXPORT_SameEmailCount")
    doms = Counter(domain_of(r.get("Website")) for r in kept["Account"].values())
    for r in kept["Account"].values():
        dm = domain_of(r.get("Website"))
        r["EXPORT_WebsiteDomain"] = dm
        r["EXPORT_SameDomainCount"] = doms[dm] if dm else ""
        r["EXPORT_DomainIsGeneric"] = (dm in GENERIC_DOMAINS) if dm else ""
    extra_cols["Account"] += ["EXPORT_WebsiteDomain", "EXPORT_SameDomainCount", "EXPORT_DomainIsGeneric"]

    for obj in RECORD_OBJECTS:
        header = fields[obj] + extra_cols[obj]
        write_csv(out / f"{obj}.csv", header, kept[obj].values())

    write_csv(out / "User.csv", ["Id", "Name", "FirstName", "LastName", "Username", "Email", "IsActive", "UserType",
                                 "Title", "Department", "EXPORT_ProfileName", "EXPORT_RoleName", "CreatedDate",
                                 "LastLoginDate", "EXPORT_OpportunitiesOwned"], users.values())
    write_csv(out / "Queue.csv", ["Id", "Name", "DeveloperName", "Email", "Type"], queues.values())
    for r in rts.values():
        r["EXPORT_InScope"] = r["Id"] != bs_rt
    write_csv(out / "RecordType.csv", ["Id", "SobjectType", "Name", "DeveloperName", "IsActive", "BusinessProcessId",
                                       "EXPORT_SalesProcessName", "Description", "EXPORT_InScope"], rts.values())
    write_csv(out / "BusinessProcess.csv", ["Id", "Name", "TableEnumOrId", "IsActive", "Description"],
              processes.values())
    write_csv(out / "OpportunityStage.csv", ["Id", "ApiName", "MasterLabel", "IsActive", "IsClosed", "IsWon",
                                             "DefaultProbability", "ForecastCategoryName", "SortOrder", "Description"],
              stages)

    # ---------------- notes, files, attachments ----------------
    kept_ids = {i for rows in kept.values() for i in rows}
    excluded_ids = {i for ids in excluded.values() for i in ids}
    links = {}
    for obj in LINK_OBJECTS:
        try:
            for r in sf.query_all_iter("SELECT Id, ContentDocumentId, LinkedEntityId, ShareType, Visibility "
                                       f"FROM ContentDocumentLink WHERE LinkedEntityId IN (SELECT Id FROM {obj})"):
                links[r["Id"]] = {k: v for k, v in r.items() if k != "attributes"}
        except Exception as e:
            log(f"  link query skipped for {obj}: {str(e)[:70]}")
    doc_links = defaultdict(list)
    link_rows = []
    for l in links.values():
        if l["LinkedEntityId"] in excluded_ids:
            continue
        l["EXPORT_LinkedEntityType"] = ctx.type_of(l["LinkedEntityId"])
        link_rows.append(l)
        doc_links[l["ContentDocumentId"]].append(l["LinkedEntityId"])
    excluded_docs = {l["ContentDocumentId"] for l in links.values()} - set(doc_links)

    versions = {}
    doc_ids = sorted(doc_links)
    for i in range(0, len(doc_ids), 300):
        ids = "','".join(doc_ids[i:i + 300])
        for r in sf.query_all_iter(
                "SELECT Id, ContentDocumentId, Title, FileType, FileExtension, ContentSize, PathOnClient, CreatedDate, "
                "CreatedById, LastModifiedDate, LastModifiedById, OwnerId FROM ContentVersion "
                f"WHERE IsLatest = true AND ContentDocumentId IN ('{ids}')"):
            versions[r["ContentDocumentId"]] = {k: v for k, v in r.items() if k != "attributes"}
    if len(versions) != len(doc_ids):
        failures.append(f"ContentVersion: {len(doc_ids) - len(versions)} linked documents have no latest version")
    for l in link_rows:
        l["EXPORT_FileType"] = (versions.get(l["ContentDocumentId"]) or {}).get("FileType", "")
    log(f"content: {len(link_rows)} links, {len(doc_ids)} documents ({len(excluded_docs)} excluded, Business Sales only)")

    if not args.include_files:
        keep = {d for d in doc_ids if (versions.get(d) or {}).get("FileType") == "SNOTE"}
        log(f"  files left out (notes only): {len(doc_ids) - len(keep)} documents")
        link_rows = [l for l in link_rows if l["ContentDocumentId"] in keep]
        doc_ids = sorted(keep)

    note_ids = [d for d in doc_ids if (versions.get(d) or {}).get("FileType") == "SNOTE"]
    file_ids = [d for d in doc_ids if d in versions and d not in set(note_ids)]
    atts = {}
    if args.include_files:
        atts = {r["Id"]: {k: v for k, v in r.items() if k != "attributes"} for r in sf.query_all(
            "SELECT Id, ParentId, Name, ContentType, BodyLength, Description, IsPrivate, OwnerId, CreatedDate, "
            "CreatedById, LastModifiedDate, SystemModstamp FROM Attachment")["records"]}
        atts = {i: a for i, a in atts.items() if a["ParentId"] in kept_ids}

    if not args.skip_files:
        jobs = {CACHE / "versiondata" / f"{versions[d]['Id']}.bin":
                f"sobjects/ContentVersion/{versions[d]['Id']}/VersionData" for d in doc_ids if d in versions}
        stamp = lambda a: re.sub(r"\D", "", a["SystemModstamp"])[:14]  # noqa: E731
        jobs.update({CACHE / "attachment" / f"{a['Id']}-{stamp(a)}.bin": f"sobjects/Attachment/{a['Id']}/Body"
                     for a in atts.values()})
        fails = download(sf, jobs)
        if fails:
            failures.append(f"downloads: {len(fails)} failed, e.g. {fails[:3]}")

    def body_of(d):
        p = CACHE / "versiondata" / f"{versions[d]['Id']}.bin"
        return p.read_bytes() if p.exists() else None

    note_rows, empty_bodies, longest = [], 0, 0
    for d in note_ids:
        v = versions[d]
        raw = None if args.skip_files else body_of(d)
        html = raw.decode("utf-8", errors="replace") if raw is not None else ""
        text = html_to_text(html)
        empty_bodies += 0 if text else 1
        longest = max(longest, len(text))
        note_rows.append({
            "ContentDocumentId": d, "ContentVersionId": v["Id"], "Title": v["Title"],
            "CreatedDate": v["CreatedDate"], "CreatedById": v["CreatedById"],
            "EXPORT_CreatedByName": (users.get(v["CreatedById"]) or {}).get("Name", ""),
            "LastModifiedDate": v["LastModifiedDate"], "OwnerId": v["OwnerId"],
            "EXPORT_OwnerName": (users.get(v["OwnerId"]) or {}).get("Name", ""),
            "EXPORT_LinkedRecordIds": ";".join(doc_links[d]),
            "EXPORT_LinkedRecordTypes": ";".join(ctx.type_of(x) for x in doc_links[d]),
            "BodyText": text, "BodyHtml": html,
            # HubSpot notes have a body and no title. 295 notes on 9/14 were title-only
            # ("VISITED AND GOT BUSINESS CARD", body <p></p>), so BodyText alone would
            # import them blank and drop the title from every other note.
            "EXPORT_NoteForHubSpot": f"{(v['Title'] or '').strip()}\n\n{text}".strip(),
        })
    write_csv(out / "Notes.csv", list(note_rows[0].keys()) if note_rows else ["ContentDocumentId"], note_rows)

    file_rows = []
    for d in file_ids:
        v = dict(versions[d])
        rel = Path("files") / d / safe_name(v["Title"], v.get("FileExtension") or "")
        if not args.skip_files and body_of(d) is not None:
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(body_of(d))
        v.update({"EXPORT_LocalPath": rel.as_posix(), "EXPORT_LinkedRecordIds": ";".join(doc_links[d]),
                  "EXPORT_LinkedRecordTypes": ";".join(ctx.type_of(x) for x in doc_links[d])})
        file_rows.append(v)
    if args.include_files:
        write_csv(out / "Files.csv", ["ContentDocumentId", "Id", "Title", "FileType", "FileExtension", "ContentSize",
                                      "PathOnClient", "CreatedDate", "CreatedById", "LastModifiedDate", "OwnerId",
                                      "EXPORT_LocalPath", "EXPORT_LinkedRecordIds", "EXPORT_LinkedRecordTypes"],
                  file_rows)
    write_csv(out / "ContentDocumentLink.csv", ["Id", "ContentDocumentId", "LinkedEntityId", "EXPORT_LinkedEntityType",
                                                "EXPORT_FileType", "ShareType", "Visibility"], link_rows)

    att_rows = []
    for a in atts.values():
        rel = Path("attachments") / a["Id"] / safe_name(a["Name"])
        cached = CACHE / "attachment" / f"{a['Id']}-{re.sub(r'[^0-9]', '', a['SystemModstamp'])[:14]}.bin"
        if not args.skip_files and cached.exists():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached, out / rel)
        att_rows.append({**a, "EXPORT_ParentType": ctx.type_of(a["ParentId"]), "EXPORT_LocalPath": rel.as_posix()})
    if args.include_files:
        write_csv(out / "Attachment.csv", ["Id", "ParentId", "EXPORT_ParentType", "Name", "ContentType", "BodyLength",
                                           "Description", "IsPrivate", "OwnerId", "CreatedDate", "CreatedById",
                                           "LastModifiedDate", "EXPORT_LocalPath"], att_rows)
    log(f"notes {len(note_rows)} (empty body {empty_bodies}, longest {longest:,} chars), files {len(file_rows)}, "
        f"attachments {len(att_rows)}")

    # ---------------- validation: IDs ----------------
    for obj, rows in list(kept.items()) + [("User", users), ("Queue", queues), ("RecordType", rts)]:
        bad = [i for i in rows if len(i) != 18]
        if bad:
            failures.append(f"{obj}: {len(bad)} Ids not 18 characters, e.g. {bad[:3]}")

    # ---------------- validation: relationships ----------------
    exported = {}
    for obj, rows in kept.items():
        exported.update(dict.fromkeys(rows, obj))
    exported.update(dict.fromkeys(users, "User"))
    exported.update(dict.fromkeys(queues, "Group"))
    exported.update(dict.fromkeys(rts, "RecordType"))
    exported.update(dict.fromkeys(processes, "BusinessProcess"))
    exported.update(dict.fromkeys(doc_ids, "ContentDocument"))
    exported_types = set(exported.values())

    checks = []  # (file, field, points_to, [values])
    for obj in RECORD_OBJECTS:
        for f in ctx.describe(obj)["fields"]:
            if f["type"] == "reference" and f["name"] in fields[obj]:
                checks.append((obj, f["name"], "/".join(f.get("referenceTo") or []),
                               [r.get(f["name"]) for r in kept[obj].values()]))
    checks.append(("ContentDocumentLink", "LinkedEntityId", "any", [l["LinkedEntityId"] for l in link_rows]))
    checks.append(("Attachment", "ParentId", "any", [a["ParentId"] for a in att_rows]))
    checks.append(("Notes", "OwnerId", "User", [n["OwnerId"] for n in note_rows]))

    report, missing = [], defaultdict(set)
    for file, fld, to, vals in checks:
        vals = [v for v in vals if v]
        row = {"file": f"{file}.csv", "field": fld, "points_to": to, "references": len(vals),
               "resolved_in_export": 0, "points_at_excluded_business_sales": 0,
               "points_outside_export": 0, "outside_objects": Counter(), "_missing": []}
        for v in vals:
            if v in exported:
                row["resolved_in_export"] += 1
            elif v in excluded_ids:
                row["points_at_excluded_business_sales"] += 1
            elif ctx.type_of(v) not in exported_types:
                row["points_outside_export"] += 1
                row["outside_objects"][ctx.type_of(v) or "?"] += 1
            else:
                row["_missing"].append(v)
                missing[ctx.type_of(v)].add(v)
        report.append(row)

    # A reference to a type we sent that did not resolve: does the target still exist?
    exists = set()
    for t, ids in missing.items():
        ids = sorted(ids)
        for i in range(0, len(ids), 300):
            chunk = "','".join(ids[i:i + 300])
            live = "IsDeleted = false AND " if t in QUERY_ALL else ""
            try:
                exists.update(r["Id"] for r in sf.query_all(
                    f"SELECT Id FROM {t} WHERE {live}Id IN ('{chunk}')", include_deleted=t in QUERY_ALL)["records"])
            except Exception as e:
                failures.append(f"could not check existence of {t} ids: {str(e)[:80]}")
    for row in report:
        m = row.pop("_missing")
        row["not_found_in_salesforce"] = sum(1 for v in m if v not in exists)
        row["LOST"] = sum(1 for v in m if v in exists)
        row["outside_objects"] = ", ".join(f"{k} {n}" for k, n in row["outside_objects"].most_common())
        if row["LOST"]:
            failures.append(f"{row['file']} {row['field']}: {row['LOST']} references to records that exist but were not exported")
    rep_cols = ["file", "field", "points_to", "references", "resolved_in_export", "points_at_excluded_business_sales",
                "points_outside_export", "outside_objects", "not_found_in_salesforce", "LOST"]
    write_csv(out / "relationship-check.csv", rep_cols, [r for r in report if r["references"]])

    # ---------------- manifest ----------------
    null_rt = sum(1 for r in kept["Opportunity"].values() if not r.get("RecordTypeId"))
    MANIFEST_NOTES["Opportunity"] += f" {null_rt} have no record type and are included."
    man = []
    for obj in RECORD_OBJECTS:
        reasons = Counter(excluded[obj].values())
        man.append({"file": f"{obj}.csv", "salesforce_object": obj, "rows_exported": len(kept[obj]),
                    "rows_in_salesforce": org_counts[obj], "rows_excluded": len(excluded[obj]),
                    "exclusion_reason": "; ".join(f"{n} {k}" for k, n in reasons.items()),
                    "columns": len(fields[obj]) + len(extra_cols[obj]), "notes": MANIFEST_NOTES.get(obj, "")})
    for name, n, extra in ((("User", len(users), ""), ("Queue", len(queues), ""), ("RecordType", len(rts), ""),
                           ("BusinessProcess", len(processes), ""), ("OpportunityStage", len(stages), ""),
                           ("Notes", len(note_rows), f"{len(excluded_docs)} notes/files excluded, attached only to Business Sales"),
                           ("ContentDocumentLink", len(link_rows), ""))
                          + ((("Files", len(file_rows), ""), ("Attachment", len(att_rows), ""))
                             if args.include_files else ())):
        man.append({"file": f"{name}.csv", "salesforce_object": name, "rows_exported": n, "rows_in_salesforce": "",
                    "rows_excluded": "", "exclusion_reason": extra, "columns": "", "notes": MANIFEST_NOTES.get(name, "")})
    write_csv(out / "manifest.csv", ["file", "salesforce_object", "rows_exported", "rows_in_salesforce",
                                     "rows_excluded", "exclusion_reason", "columns", "notes"], man)

    dup_contacts = sum(1 for r in kept["Contact"].values() if (r["EXPORT_SameEmailCount"] or 0) > 1)
    dup_accounts = sum(1 for r in kept["Account"].values() if (r["EXPORT_SameDomainCount"] or 0) > 1)
    (out / "read-me.txt").write_text(f"""Salesforce export for the HubSpot migration
Generated {run_at:%Y-%m-%d %H:%M} UTC from the production org (Generate Ubiquity Services LLC).
Records created after that time are not included.

FILES
One CSV per Salesforce object, named by its API name, one row per record, every field.
Column headers are the Salesforce field API names; salesforce-hubspot-field-map.xlsx has
the label, type, picklist values and formula for each one.
manifest.csv lists every file with its row count against Salesforce and anything excluded.
relationship-check.csv shows, for every ID column, how many IDs resolve to a record in this
export. Anything in points_outside_export is a lookup to an object that is not being migrated
(for example IronClad, which moves by its own sync).

IDS
Every ID is the 18-character Salesforce ID. Use these, not the 15-character IDs shown in
Salesforce reports or URLs. The 15-character form is case sensitive and Excel lookups treat
two different IDs as the same value.

COLUMNS STARTING WITH EXPORT_
Not Salesforce fields. Added to help the import: owner and record type names next to their
IDs, whether the owner is still active, which object a multi-object lookup points at, and
duplicate flags. Map them or ignore them.

HOW RECORDS CONNECT
- Contacts attach to opportunities through Opportunity_Contact__c, not the standard
  OpportunityContactRole, which is unused. Role__c on that file says owner or manager.
- Campaign membership is Opportunity_Campaign__c. CampaignMember is empty.
- Opportunity_Account__c links extra management companies beyond Opportunity.AccountId.
- Notes attach through ContentDocumentLink.csv. One note can sit on several records.
- OwnerId resolves in User.csv or Queue.csv. Many owners are deactivated users; see
  EXPORT_OwnerIsActive and User.csv EXPORT_OpportunitiesOwned.

EXCLUDED
Business Sales opportunities (record type "Business Sales") are out of scope and excluded,
with their campaign links, account links, stage history, tasks, emails and notes. Accounts
linked only to those opportunities are excluded too. Business ROE is a different record type
and is fully included.
{"" if args.include_files else '''Salesforce files and email attachments are not included. The signed agreements among them
are in IronClad.'''}

BEFORE IMPORTING
- {dup_contacts} contacts share an email address with another contact (EXPORT_SameEmailCount above 1).
  HubSpot matches contacts on email, so each group becomes one contact on import.
- {dup_accounts} accounts share a website domain with another account (EXPORT_SameDomainCount above 1),
  some of them gmail, aol or facebook (EXPORT_DomainIsGeneric). If Website maps to Company domain
  name, unrelated companies merge.
- Tasks and Events include archived activity, which a standard Salesforce export leaves out.
- Salesforce notes have a title and a body; HubSpot notes have only a body. Notes.csv
  EXPORT_NoteForHubSpot joins the two. {empty_bodies} notes are title only, so importing BodyText
  alone would bring them in blank.
- Formula fields are exported as their current value. In HubSpot they are static unless rebuilt
  as calculated properties; the field map has each formula.
""", encoding="utf-8")

    # ---------------- result ----------------
    lost = ", ".join(f"{r['file']} {r['field']} LOST {r['LOST']}" for r in report if r["LOST"])
    log(f"relationship check: {lost or 'nothing lost'}")
    if failures:
        log(f"FAILED {len(failures)} check(s):")
        for f in failures:
            log(f"  - {f}")
        log(f"output left in {out} for inspection, NOT zipped")
        sys.exit(1)
    if args.skip_files:
        log(f"all checks passed (records only, no downloads). {out}")
        return
    zip_path = shutil.make_archive(str(ROOT / f"hubspot-export-{out.name}"), "zip", out)
    log(f"all checks passed. {out}")
    log(f"zip {zip_path} ({Path(zip_path).stat().st_size / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
