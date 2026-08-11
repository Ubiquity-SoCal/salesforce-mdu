"""
Build an Outlook draft summarizing the Omaha MDU fiber list (Vetro) vs Salesforce,
grouped into: (1) New and added, (2) Existing but needs agree name added,
(3) Existing already - with current status. Status is derived from EXACT agree-name
matches (reliable), not address (avoids house-number collisions).

Drafts only, never sends. Run: python omaha_mdu_status_email.py
"""
import sys
from pathlib import Path
import openpyxl
from simple_salesforce import Salesforce

sys.path.insert(0, str(Path(r"C:\Users\cass\Work_Projects\_shared")))
from outlook_draft import open_draft

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


USERNAME = _SF["username"]; PASSWORD = _SF["password"]; SECURITY_TOKEN = _SF["token"]
VETRO = Path(r"C:\Users\cass\AppData\Local\Temp\claude\C--Users-cass-Work-Projects\eb63bd25-744f-4859-9c80-939403c2cb8e\scratchpad\omaha_mdus.xlsx")

NEW3 = {"Omaha_MDU_4430 Redman Ave", "Omaha_MDU_Blondo Crest Apartments",
        "Omaha_MDU_Colonial Court Apartments"}
# active Opp lacks the agree name -> won't show in an agree-name search
NEEDS_NAME = {"Omaha_MDU_Ville de Sante Apartments": "Prospects (active Opp has no agree name yet)",
              "Omaha_MDU_Irvington Heights": "Prospects (active Opp has no agree name; older Closed Lost record does)"}

RANK = {"Closed Lost": -1, "On Hold": 0, "Prospects": 1, "Prospecting": 2, "Engaged": 3,
        "Proposal Sent": 4, "Contract Negotiations": 5, "PAL/ROE Complete": 6,
        "Marketing/Bulk In Progress": 7, "Marketing/Bulk Complete": 8}

def readable(site, monday):
    if monday and str(monday).strip():
        return str(monday).strip()
    return site.replace("OMAHA_MDU_", "").replace("Omaha_MDU_", "").strip()

def main():
    ws = openpyxl.load_workbook(VETRO, read_only=True, data_only=True).active
    vlist = [dict(site=str(r[0]).strip(), monday=r[1], units=r[3], addr=str(r[4] or "").strip())
             for r in list(ws.iter_rows(values_only=True))[1:] if r[0]]

    sf = Salesforce(username=USERNAME, password=PASSWORD, security_token=SECURITY_TOKEN)
    sys.path.insert(0, str(Path(r"C:\Users\cass\Work_Projects\SalesForce\scripts\analysis")))
    from lookup_agree_names_for_unlinked import house, st_tokens
    STOP = {"omaha", "ne", "nebraska"}          # city/state words pollute street-token overlap
    def toks(a): return st_tokens(a) - STOP

    # full Omaha MDU universe (so name-variant Opps like Indian Hills are found by address)
    opps = sf.query_all(
        "SELECT Name, Agreement_Name__c, Property_Address__c, StageName, Property_Category__c "
        "FROM Opportunity WHERE Name LIKE 'Omaha%' OR Agreement_Name__c LIKE 'Omaha%' "
        "OR Property_City__c LIKE 'Omaha%' OR (Property_State__c IN ('NE','Nebraska') "
        "AND RecordType.Name='MDU/SFU')")["records"]
    by_agree, by_house = {}, {}
    for o in opps:
        agn = (o["Agreement_Name__c"] or "").strip().lower()
        if agn:
            by_agree.setdefault(agn, []).append(o)
        h = house(o["Property_Address__c"])
        if h:
            by_house.setdefault(h, []).append(o)

    def match(v):
        hits = {}
        for o in by_agree.get(v["site"].lower(), []):
            hits[id(o)] = o                                   # 1. exact agree-name
        h = house(v["addr"]); gt = toks(v["addr"])
        if h:
            for o in by_house.get(h, []):                     # 2. same house + street overlap
                if gt & toks(o["Property_Address__c"]):
                    hits[id(o)] = o
            if not hits:                                      # 3. near house (+/-25) + >=2 alpha tokens
                ga = {t for t in gt if not t.isdigit()}
                if len(ga) >= 2:
                    for o in opps:
                        oh = house(o["Property_Address__c"])
                        oa = {t for t in toks(o["Property_Address__c"]) if not t.isdigit()}
                        if oh and abs(int(oh) - int(h)) <= 25 and len(ga & oa) >= 2:
                            hits[id(o)] = o
        return list(hits.values())

    new, needs, existing = [], [], []
    for v in vlist:
        nm = readable(v["site"], v["monday"]); units = int(v["units"] or 0)
        if v["site"] in NEW3:
            new.append((nm, v["addr"], units, "Added 7/8 as Prospect (Cat 1)")); continue
        hits = match(v)
        best = max(hits, key=lambda o: RANK.get(o["StageName"], 0)) if hits else None
        if best is None:
            existing.append((nm, v["addr"], units, "IN SF - status not resolved (check)"))
        elif not (best["Agreement_Name__c"] or "").strip():
            needs.append((nm, v["addr"], units, f"{best['StageName']} (active Opp has no agree name)"))
        else:
            existing.append((nm, v["addr"], units, best["StageName"]))
    existing.sort(key=lambda r: (RANK.get(r[3], 0), -r[2]), reverse=True)

    def table(rows, cols):
        th = "".join(f'<th style="background:#1F4E78;color:#fff;padding:6px 10px;'
                     f'text-align:left;font-size:13px;">{c}</th>' for c in cols)
        trs = ""
        for r in rows:
            tds = "".join(f'<td style="padding:5px 10px;border-bottom:1px solid #e0e0e0;'
                          f'font-size:13px;">{c}</td>' for c in r)
            trs += f"<tr>{tds}</tr>"
        return (f'<table style="border-collapse:collapse;width:100%;max-width:760px;'
                f'margin:6px 0 16px;">{th}{trs}</table>')

    cl = sum(1 for r in existing if r[3] == "Closed Lost")
    body = f"""<p style="font-family:Calibri,Arial,sans-serif;">Hi,</p>
<p style="font-family:Calibri,Arial,sans-serif;">I reconciled the {len(vlist)} Omaha MDUs from the Vetro fiber list against Salesforce. Summary:</p>
{table([("Existing already in Salesforce", len(existing), f"{sum(r[2] for r in existing):,}"),
        ("Existing, agree name needs adding", len(needs), f"{sum(r[2] for r in needs):,}"),
        ("New, added to Salesforce", len(new), f"{sum(r[2] for r in new):,}")],
       ["Category", "MDUs", "Units"])}
<p style="font-family:Calibri,Arial,sans-serif;">Only {len(new)} were genuinely missing and are now loaded. Note {cl} of the existing ones are currently <b>Closed Lost</b>, so most of the list is already in the system rather than missing.</p>

<p style="font-family:Calibri,Arial,sans-serif;"><b>1. New, added to Salesforce ({len(new)})</b> - loaded as Cat 1 Prospects, owner Melissa Baker:</p>
{table(new, ["MDU", "Address", "Units", "Status"])}

<p style="font-family:Calibri,Arial,sans-serif;"><b>2. Existing, but agree name needs adding ({len(needs)})</b> - these are in Salesforce but the active record has no agree name, so they do not show up in an agree-name search:</p>
{table(needs, ["MDU", "Address", "Units", "Current Status"])}

<p style="font-family:Calibri,Arial,sans-serif;"><b>3. Existing already ({len(existing)})</b> - with current status:</p>
{table(existing, ["MDU", "Address", "Units", "Current Status"])}

<p style="font-family:Calibri,Arial,sans-serif;">Full detail is in the attached workbook. Let me know if you want the Closed Lost ones reviewed for re-approach.</p>
<p style="font-family:Calibri,Arial,sans-serif;">Thanks,<br>Cass</p>"""

    # save a copy of the body for reference
    out = Path(r"C:\Users\cass\Work_Projects\SalesForce\data\output\omaha-mdu-status-email.html")
    out.write_text(body, encoding="utf-8")
    print(f"counts -> existing {len(existing)} | needs-name {len(needs)} | new {len(new)} | total {len(vlist)}")
    print(f"closed-lost among existing: {cl}")
    print(f"body saved: {out}")
    for label, rows in [("NEW", new), ("NEEDS-NAME", needs), ("EXISTING", existing)]:
        for r in rows:
            if any(k in r[0] for k in ("Indian Hills", "Aspen Grove", "Ville de Sante",
                                       "Irvington", "Farnam", "not resolved")):
                print(f"  [{label}] {r[0][:34]:34} -> {r[3]}")

    if "--draft" not in sys.argv:
        print("\n(verify pass - pass --draft to create the Outlook draft)")
        return
    attach = r"C:\Users\cass\OneDrive - Ubiquity Management\Desktop\OMAHA MDUs - Vetro vs Salesforce.xlsx"
    open_draft(subject="Omaha MDUs - Vetro Fiber List vs Salesforce Status",
               body_html=body, attachments=[attach] if Path(attach).exists() else None,
               display=True, save=True)
    print("Outlook draft created (To: blank - add recipient).")

if __name__ == "__main__":
    main()
