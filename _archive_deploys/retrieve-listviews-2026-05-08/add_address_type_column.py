"""Modify Property_Location__c.object: insert <columns>Address_Type__c</columns>
right after the first <columns>NAME</columns> in every listViews block."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

src = Path(r'C:\Users\cass\Work_Projects\SalesForce\retrieve-listviews-2026-05-08\retrieved\unpackaged\objects\Property_Location__c.object')
text = src.read_text(encoding='utf-8')

# Find each <listViews>...</listViews> block and modify
pattern = re.compile(r'(<listViews>)(.*?)(</listViews>)', re.DOTALL)
modified = []
def replace_block(m):
    head, body, tail = m.group(1), m.group(2), m.group(3)
    if '<columns>Address_Type__c</columns>' in body:
        return m.group(0)  # already present
    fn_match = re.search(r'<fullName>([^<]+)</fullName>', body)
    label = fn_match.group(1) if fn_match else '?'
    # Insert right after first <columns>NAME</columns>
    new_body, n = re.subn(
        r'(<columns>NAME</columns>\s*\n)',
        r'\1        <columns>Address_Type__c</columns>\n',
        body, count=1
    )
    if n == 0:
        # No NAME column? Add as first column
        new_body = re.sub(r'(<fullName>[^<]+</fullName>\s*\n)',
                          r'\1        <columns>Address_Type__c</columns>\n',
                          body, count=1)
    modified.append(label)
    return head + new_body + tail

new_text = pattern.sub(replace_block, text)
src.write_text(new_text, encoding='utf-8')
print(f'Modified {len(modified)} list views:')
for n in modified:
    print(f'  {n}')
