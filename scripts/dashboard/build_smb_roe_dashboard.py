"""
Build SMB ROE FF Sales Dashboard
Pulls data from Salesforce + original Excel, generates self-contained HTML.

Usage: python build_smb_roe_dashboard.py
"""

import json
import re
from datetime import datetime
from simple_salesforce import Salesforce
import openpyxl

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


# ── Connect ──
sf = Salesforce(
    username=_SF["username"],
    password=_SF["password"],
    security_token=_SF["token"]
)

# ── Pull SF data ──
result = sf.query("""
    SELECT Id, Name, City__c, State__c, Property_Unit_Count__c,
           FF_Sales_Project__c, FF_Sales_Assigned_Date__c, Build_Effort__c,
           User__c, ROE_Status__c, Property_Status__c, Property_Type__c,
           Active_Unit_Count__c, Market__c
    FROM Property_Location__c
    WHERE FF_Sales_Project__c = 'SMB ROE'
    AND Import_Delete_Property__c = false
    ORDER BY State__c, City__c, Name
""")

# Get user names
user_ids = {r['User__c'] for r in result['records'] if r['User__c']}
user_map = {}
if user_ids:
    ids_str = "','".join(user_ids)
    users = sf.query(f"SELECT Id, Name FROM User WHERE Id IN ('{ids_str}')")
    for u in users['records']:
        user_map[u['Id']] = u['Name']

# ── Pull RE initials + notes from Excel ──
EXCEL_PATH = r"C:\Users\cass\OneDrive - Ubiquity Management\Desktop\Assign to FF - SMB 4-1.xlsx"

def normalize_addr(full_addr):
    if not full_addr:
        return ''
    a = full_addr.split('\n')[0].strip()
    a = re.sub(r'\s+UNIT\s+\S+', '', a, flags=re.IGNORECASE)
    a = re.sub(r'\s+SUITE\s+\S+', '', a, flags=re.IGNORECASE)
    a = re.sub(r'\s+\d{5}$', '', a)
    return a.strip().upper()

excel_data = {}
try:
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb['Sheet1']
    for row in ws.iter_rows(min_row=2, values_only=True):
        base = normalize_addr(row[0])
        excel_data[base] = {
            're': row[5] or '',
            'notes': (row[8] or '')[:300]
        }
except Exception as e:
    print(f"Warning: Could not read Excel ({e}), RE initials will be blank")

# ── Build data ──
data = []
for r in result['records']:
    sf_name = r['Name']
    ex = excel_data.get(sf_name, {})
    data.append({
        'name': sf_name,
        'city': r['City__c'] or '',
        'state': r['State__c'] or '',
        'units': int(r['Property_Unit_Count__c'] or 0),
        'buildEffort': r['Build_Effort__c'] or '',
        'assignedDate': r['FF_Sales_Assigned_Date__c'] or '',
        'reAssigned': user_map.get(r['User__c'], ''),
        'reInitials': ex.get('re', ''),
        'roeStatus': r['ROE_Status__c'] or '',
        'propertyStatus': r['Property_Status__c'] or '',
        'propertyType': r['Property_Type__c'] or '',
        'activeUnits': int(r['Active_Unit_Count__c'] or 0),
        'reNotes': ex.get('notes', '')
    })

total = len(data)
total_units = sum(d['units'] for d in data)
now = datetime.now().strftime('%m/%d/%Y')

# Stats
by_state = {}
by_effort = {}
by_re = {}
for d in data:
    s = d['state']
    by_state.setdefault(s, {'count': 0, 'units': 0})
    by_state[s]['count'] += 1
    by_state[s]['units'] += d['units']

    e = d['buildEffort'] or 'Unknown'
    by_effort[e] = by_effort.get(e, 0) + 1

    r = d['reInitials'] or 'Unassigned'
    by_re.setdefault(r, {'count': 0, 'units': 0})
    by_re[r]['count'] += 1
    by_re[r]['units'] += d['units']

state_colors = {'AZ': '#2471a3', 'NE': '#1a5276', 'TX': '#6c3483'}
effort_colors = {'Easy': '#16a085', 'Medium': '#e67e22', 'Hard': '#c0392b'}

data_json = json.dumps(data)

# ── Build state summary cards ──
state_html = ""
for s in sorted(by_state.keys()):
    c = state_colors.get(s, '#7f8c8d')
    state_html += f'<div class="stat-row"><span class="stat-label"><span class="dot" style="background:{c}"></span>{s}</span><span class="stat-value">{by_state[s]["count"]} props &bull; {by_state[s]["units"]} units</span></div>\n'

effort_html = ""
for e in ['Easy', 'Medium', 'Hard']:
    c = effort_colors.get(e, '#7f8c8d')
    effort_html += f'<div class="stat-row"><span class="stat-label"><span class="dot" style="background:{c}"></span>{e}</span><span class="stat-value">{by_effort.get(e, 0)}</span></div>\n'

re_html = ""
for r in sorted(by_re.keys()):
    re_html += f'<div class="stat-row"><span class="stat-label">{r}</span><span class="stat-value">{by_re[r]["count"]} props &bull; {by_re[r]["units"]} units</span></div>\n'

state_btns = ""
for s in sorted(by_state.keys()):
    state_btns += f'<button class="slicer-btn" onclick="filterState(\'{s}\')">{s}</button>\n'

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMB ROE - FF Sales Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: "Segoe UI", "Trebuchet MS", sans-serif;
    background: linear-gradient(135deg, #f0f4f8 0%, #e8eef5 50%, #f5f0eb 100%);
    color: #1d2a38;
    min-height: 100vh;
    padding: 24px;
}}
.header {{ text-align: center; margin-bottom: 28px; }}
.header h1 {{ font-size: clamp(22px, 3vw, 32px); color: #1d2a38; margin-bottom: 6px; }}
.header .subtitle {{ color: #5a6a7b; font-size: 14px; }}

.kpi-row {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; justify-content: center; }}
.kpi {{
    background: white; border: 1px solid #d8e1ea; border-radius: 14px;
    padding: 20px 28px; text-align: center;
    box-shadow: 0 8px 24px rgba(20,40,60,0.08);
    min-width: 140px; flex: 1; max-width: 200px;
}}
.kpi .value {{ font-size: 32px; font-weight: 700; color: #1f6f8b; }}
.kpi .label {{ font-size: 12px; color: #5a6a7b; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}

.cards-row {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.card {{
    background: white; border: 1px solid #d8e1ea; border-radius: 14px;
    padding: 20px; box-shadow: 0 8px 24px rgba(20,40,60,0.08); flex: 1; min-width: 260px;
}}
.card h3 {{ font-size: 15px; color: #1d2a38; margin-bottom: 14px; border-bottom: 2px solid #d8e1ea; padding-bottom: 8px; }}
.stat-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f4f8; font-size: 14px; }}
.stat-row:last-child {{ border-bottom: none; }}
.stat-row .stat-label {{ display: flex; align-items: center; gap: 8px; }}
.stat-row .stat-value {{ font-weight: 600; }}
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}

.slicer-row {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }}
.slicer-label {{ font-size: 13px; color: #5a6a7b; font-weight: 600; margin-right: 4px; }}
.slicer-btn {{
    padding: 6px 14px; border: 1px solid #d8e1ea; border-radius: 8px;
    background: white; cursor: pointer; font-size: 13px; font-family: inherit; transition: all 0.15s;
}}
.slicer-btn:hover {{ background: #f0f4f8; }}
.slicer-btn.active {{ background: #1f6f8b; color: white; border-color: #1f6f8b; }}

.table-card {{
    background: white; border: 1px solid #d8e1ea; border-radius: 14px;
    padding: 20px; box-shadow: 0 16px 40px rgba(20,40,60,0.12); overflow-x: auto;
}}
.table-card h3 {{ font-size: 15px; margin-bottom: 12px; }}
.search-box {{
    padding: 8px 14px; border: 1px solid #d8e1ea; border-radius: 8px;
    font-size: 13px; width: 260px; margin-bottom: 12px; font-family: inherit;
}}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{
    background: #1f6f8b; color: white; padding: 10px 12px; text-align: left;
    cursor: pointer; white-space: nowrap; position: sticky; top: 0; user-select: none;
}}
th:hover {{ background: #1a5f78; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #e8eef5; white-space: nowrap; }}
tr:nth-child(even) {{ background: #f8fafc; }}
tr:hover {{ background: #edf2f7; }}

.effort-badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; color: white; }}
.effort-Easy {{ background: #16a085; }}
.effort-Medium {{ background: #e67e22; }}
.effort-Hard {{ background: #c0392b; }}
.row-count {{ font-size: 13px; color: #5a6a7b; margin-top: 10px; }}
.notes-cell {{ max-width: 350px; white-space: normal; font-size: 12px; line-height: 1.4; color: #5a6a7b; }}
</style>
</head>
<body>

<div class="header">
    <h1>SMB ROE &mdash; FiberFirst Sales Assignment</h1>
    <div class="subtitle">Assigned {now} &bull; {total} Properties &bull; {total_units} Total Units</div>
</div>

<div class="kpi-row">
    <div class="kpi"><div class="value">{total}</div><div class="label">Properties</div></div>
    <div class="kpi"><div class="value">{total_units}</div><div class="label">Total Units</div></div>
    <div class="kpi"><div class="value">{len(by_state)}</div><div class="label">States</div></div>
    <div class="kpi"><div class="value">{by_effort.get('Easy',0)}</div><div class="label">Easy Build</div></div>
    <div class="kpi"><div class="value">{by_effort.get('Medium',0)}</div><div class="label">Medium Build</div></div>
    <div class="kpi"><div class="value">{by_effort.get('Hard',0)}</div><div class="label">Hard Build</div></div>
</div>

<div class="cards-row">
    <div class="card"><h3>By State</h3>{state_html}</div>
    <div class="card"><h3>By Build Effort</h3>{effort_html}</div>
    <div class="card"><h3>By RE Assigned</h3>{re_html}</div>
</div>

<div class="slicer-row">
    <span class="slicer-label">State:</span>
    <button class="slicer-btn active" onclick="filterState('all')">All</button>
    {state_btns}
    <span class="slicer-label" style="margin-left:16px">Effort:</span>
    <button class="slicer-btn active" onclick="filterEffort('all')">All</button>
    <button class="slicer-btn" onclick="filterEffort('Easy')">Easy</button>
    <button class="slicer-btn" onclick="filterEffort('Medium')">Medium</button>
    <button class="slicer-btn" onclick="filterEffort('Hard')">Hard</button>
</div>

<div class="table-card">
    <h3>Property Details</h3>
    <input type="text" class="search-box" placeholder="Search address, city, notes..." oninput="searchTable(this.value)">
    <div style="max-height:600px;overflow-y:auto">
    <table id="propTable">
        <thead><tr>
            <th onclick="sortTable(0)">Address</th>
            <th onclick="sortTable(1)">City</th>
            <th onclick="sortTable(2)">State</th>
            <th onclick="sortTable(3)">Units</th>
            <th onclick="sortTable(4)">Build Effort</th>
            <th onclick="sortTable(5)">RE</th>
            <th onclick="sortTable(6)">Property Type</th>
            <th>RE Notes</th>
        </tr></thead>
        <tbody id="tableBody"></tbody>
    </table>
    </div>
    <div class="row-count" id="rowCount"></div>
</div>

<script>
var DATA = {data_json};
var currentState = "all";
var currentEffort = "all";
var currentSearch = "";

function renderTable() {{
    var filtered = DATA.filter(function(d) {{
        if (currentState !== "all" && d.state !== currentState) return false;
        if (currentEffort !== "all" && d.buildEffort !== currentEffort) return false;
        if (currentSearch) {{
            var s = currentSearch.toLowerCase();
            var hay = (d.name + d.city + d.state + d.reInitials + d.reNotes + d.propertyType).toLowerCase();
            if (hay.indexOf(s) === -1) return false;
        }}
        return true;
    }});
    var tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";
    for (var i = 0; i < filtered.length; i++) {{
        var d = filtered[i];
        var tr = document.createElement("tr");
        tr.innerHTML =
            "<td>" + d.name + "</td>" +
            "<td>" + d.city + "</td>" +
            "<td>" + d.state + "</td>" +
            "<td style='text-align:right'>" + d.units + "</td>" +
            "<td><span class='effort-badge effort-" + d.buildEffort + "'>" + d.buildEffort + "</span></td>" +
            "<td>" + (d.reInitials || "") + "</td>" +
            "<td>" + (d.propertyType || "") + "</td>" +
            "<td class='notes-cell'>" + (d.reNotes || "") + "</td>";
        tbody.appendChild(tr);
    }}
    var totalUnits = filtered.reduce(function(s, d) {{ return s + d.units; }}, 0);
    document.getElementById("rowCount").textContent =
        "Showing " + filtered.length + " of " + DATA.length + " properties (" + totalUnits + " units)";
}}

function filterState(s) {{
    currentState = s;
    document.querySelectorAll(".slicer-row .slicer-btn").forEach(function(b) {{
        if (b.getAttribute("onclick") && b.getAttribute("onclick").indexOf("filterState") !== -1) {{
            b.classList.remove("active");
            if ((s === "all" && b.textContent === "All") || b.textContent === s) b.classList.add("active");
        }}
    }});
    renderTable();
}}

function filterEffort(e) {{
    currentEffort = e;
    document.querySelectorAll(".slicer-row .slicer-btn").forEach(function(b) {{
        if (b.getAttribute("onclick") && b.getAttribute("onclick").indexOf("filterEffort") !== -1) {{
            b.classList.remove("active");
            if ((e === "all" && b.textContent === "All") || b.textContent === e) b.classList.add("active");
        }}
    }});
    renderTable();
}}

function searchTable(val) {{ currentSearch = val; renderTable(); }}

var sortDir = {{}};
function sortTable(col) {{
    sortDir[col] = !sortDir[col];
    var keys = ["name","city","state","units","buildEffort","reInitials","propertyType","reNotes"];
    var key = keys[col];
    var dir = sortDir[col] ? 1 : -1;
    DATA.sort(function(a, b) {{
        var va = a[key] || "";
        var vb = b[key] || "";
        if (typeof va === "number") return (va - vb) * dir;
        return va.toString().localeCompare(vb.toString()) * dir;
    }});
    renderTable();
}}

renderTable();
</script>
</body>
</html>"""

OUT = r"C:\Users\cass\Work_Projects\SalesForce\smb-roe-dashboard.html"
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Dashboard saved: {OUT}")
print(f"{total} properties, {total_units} units across {len(by_state)} states")
