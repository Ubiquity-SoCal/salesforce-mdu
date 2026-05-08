"""
Parse MDU Projects - Weekly Tracker (3).xlsb and dump as CSV + JSON for matching.
Excel serial dates -> ISO dates.
"""
from pyxlsb import open_workbook
from datetime import datetime, timedelta
import csv, json

WB = r'C:\Users\cass\Downloads\MDU Projects - Weekly Tracker (3).xlsb'

def excel_serial_to_iso(v):
    if v is None or v == '':
        return None
    if isinstance(v, str):
        return v
    try:
        d = datetime(1899, 12, 30) + timedelta(days=float(v))
        return d.strftime('%Y-%m-%d')
    except Exception:
        return str(v)

with open_workbook(WB) as wb:
    sn = wb.sheets[0]
    with wb.get_sheet(sn) as sh:
        rows = [[c.v for c in r] for r in sh.rows()]

headers = rows[0]
data = rows[1:]
# Trim trailing empties / blank rows
data = [r for r in data if any(c not in (None, '') for c in r)]

print(f"Headers ({len(headers)}):")
for i, h in enumerate(headers):
    print(f"  [{i}] {h!r}")

# Convert dates: indices 8 (Target Close Date), 13/14/15 (PAL/ROE/?), 16/17/18/19 (Project Start, etc)
date_cols = [8, 13, 14, 15, 16, 17, 18, 19]

records = []
for r in data:
    rec = {}
    for i, h in enumerate(headers):
        if h is None:
            h = f"col_{i}"
        v = r[i] if i < len(r) else None
        if i in date_cols:
            v_iso = excel_serial_to_iso(v)
            rec[h] = v_iso
        else:
            rec[h] = v
    records.append(rec)

# Save
with open('weekly_tracker_parsed.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, indent=2, default=str)

print(f"\n=== {len(records)} rows in tracker ===\n")
for r in records:
    site = r.get('Site Name', '')
    owner = r.get('Owner', '')
    target = r.get('Target Close Date', '')
    status = r.get('Status', '')
    units = r.get('Total Units', '')
    print(f"  [{owner!s:10s}] {site!s:55s} units={units!s:5s} target={target!s:12s} status={(status or '')[:50]}")
