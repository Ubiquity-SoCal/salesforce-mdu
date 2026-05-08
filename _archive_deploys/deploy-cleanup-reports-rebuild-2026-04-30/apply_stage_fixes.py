"""Apply stage filter updates to deploy copies of report XMLs (post 4/29 stage restructure)."""
from pathlib import Path
base = Path(__file__).parent / 'force-app/main/default/reports/MDU_Sales_Reports'

ACTIVE_BEYOND = 'Engaged,Proposal Sent,Contract Negotiations,PAL/ROE Complete'
ACTIVE_INCL_BULK = 'Engaged,Proposal Sent,Contract Negotiations,PAL/ROE Complete,EMA/Bulk In Progress'
COMPLETED = 'PAL/ROE Complete,EMA/Bulk In Progress,EMA/Bulk Complete'

EDITS = [
    ('Cleanup_Under_Contract_No_PAL.report-meta.xml', [
        ('<value>Under Contract</value>', f'<value>PAL/ROE Complete</value>'),
        ('<name>Cleanup: Under Contract: No PAL</name>', '<name>Cleanup: PAL/ROE Complete: No PAL</name>'),
    ]),
    ('Cleanup_Opps_No_RE_Assigned.report-meta.xml', [
        ('<value>Contract Negotiations,ROE Secured,Under Contract</value>', f'<value>{ACTIVE_BEYOND}</value>'),
    ]),
    ('Cleanup_Opps_No_Projected_Close.report-meta.xml', [
        ('<value>Contract Negotiations,ROE Secured,Under Contract</value>', f'<value>{ACTIVE_BEYOND}</value>'),
    ]),
    ('Cleanup_Opps_No_Property_Location.report-meta.xml', [
        ('<value>Engaged,Contract Negotiations,ROE Secured,Under Contract</value>', f'<value>{ACTIVE_INCL_BULK}</value>'),
    ]),
    ('Cleanup_Stale_Active_Opps.report-meta.xml', [
        ('<value>Engaged,Contract Negotiations,ROE Secured,Under Contract</value>', f'<value>{ACTIVE_INCL_BULK}</value>'),
    ]),
    ('Cleanup_Stale_EMA_Bulk_Opps.report-meta.xml', [
        ('<value>Under Contract,EMA/Bulk In Progress,EMA/Bulk Completed</value>', f'<value>{COMPLETED}</value>'),
    ]),
]

for filename, edits in EDITS:
    p = base / filename
    text = p.read_text(encoding='utf-8')
    orig = text
    for old, new in edits:
        if old not in text:
            print(f'  ! {filename}: old string not found: {old[:60]}')
            continue
        text = text.replace(old, new)
        print(f'  + {filename}: replaced {old[:60]} -> {new[:60]}')
    if text != orig:
        p.write_text(text, encoding='utf-8')

# Print all final STAGE_NAME and name values for verification
print('\nFinal state of files:')
for f in sorted(base.glob('*.xml')):
    text = f.read_text(encoding='utf-8')
    name_line = next((l.strip() for l in text.splitlines() if '<name>' in l and '</name>' in l), '?')
    print(f'  {f.name}: {name_line}')
