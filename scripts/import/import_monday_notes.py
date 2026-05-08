"""Import Monday.com updates as Salesforce ContentNotes on sample Opportunities."""
import requests, json, base64, time
from simple_salesforce import Salesforce

API_KEY = open(r'C:\Users\cass\Work_Projects\Monday.com\Monday.com_Key.txt').read().strip()
MONDAY_URL = "https://api.monday.com/v2"
monday_headers = {"Authorization": API_KEY, "Content-Type": "application/json"}

sf = Salesforce(username='cass1@ubiquitygp.com', password='Karate88!', security_token='Ktc1n9mLmD9vwEcVcl45q0iAD')

# Sample items to import notes for
sample_items = {
    "4210794018": "006WR00000udaZhYAI",  # Waterstone Apartments
    "3136295928": "006WR00000udTrcYAE",  # Olympus Waterford
    "11464022779": "006WR00000ucC3BYAU", # Town East
    "11005114785": "006WR00000udDmlYAE", # 120 Sunset Dr
}

print("Step 1: Pulling updates from Monday.com...\n")

all_notes = {}  # monday_id -> list of updates

for monday_id, sf_id in sample_items.items():
    query = f'''{{
      items(ids: [{monday_id}]) {{
        name
        updates {{
          id
          text_body
          created_at
          creator {{
            name
          }}
        }}
      }}
    }}'''

    resp = requests.post(MONDAY_URL, headers=monday_headers, json={"query": query})
    data = resp.json()

    items = data.get('data', {}).get('items', [])
    if not items:
        print(f"  No item found for Monday ID {monday_id}")
        continue

    item = items[0]
    updates = item.get('updates', [])
    print(f"  {item['name']}: {len(updates)} updates")

    # Sort oldest first so when we create them in order, newest ends up on top
    updates.sort(key=lambda u: u['created_at'])

    all_notes[monday_id] = {
        'name': item['name'],
        'sf_id': sf_id,
        'updates': updates
    }

    for u in updates:
        author = u['creator']['name'] if u.get('creator') else 'Unknown'
        date = u['created_at'][:10]
        text = (u.get('text_body') or '')[:80]
        print(f"    {date} by {author}: {text}...")

print(f"\nStep 2: Creating ContentNotes in Salesforce...\n")

total_created = 0

for monday_id, item_data in all_notes.items():
    sf_opp_id = item_data['sf_id']
    opp_name = item_data['name']
    updates = item_data['updates']

    print(f"  {opp_name} ({len(updates)} notes):")

    for u in updates:
        author = u['creator']['name'] if u.get('creator') else 'Unknown'
        created = u['created_at']
        date_str = created[:10]
        text_body = u.get('text_body') or '(no text)'

        # Note title: Author - Date
        title = f"{author} - {date_str}"

        # Note body: full text with metadata header
        # ContentNote body must be base64-encoded and content type is text/plain or text/html
        body_text = f"{author} | {created[:19].replace('T', ' ')}\n\n{text_body}"

        # Create ContentNote
        # ContentNote.Content must be base64-encoded
        content_b64 = base64.b64encode(body_text.encode('utf-8')).decode('utf-8')

        try:
            note = sf.ContentNote.create({
                'Title': title,
                'Content': content_b64,
            })
            note_id = note['id']

            # ContentNote Id IS the ContentDocumentId — use directly
            sf.ContentDocumentLink.create({
                'ContentDocumentId': note_id,
                'LinkedEntityId': sf_opp_id,
                'ShareType': 'V',  # Viewer
                'Visibility': 'AllUsers'
            })

            total_created += 1
            print(f"    + {title}")

        except Exception as e:
            print(f"    ERROR: {title} - {e}")

        # Small delay to avoid API limits
        time.sleep(0.2)

print(f"\nDone! Created {total_created} notes across {len(all_notes)} Opportunities.")
