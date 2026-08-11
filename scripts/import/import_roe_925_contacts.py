"""
Parse Management Company and Owner/Property Contact fields from ROE 9-25 data,
create Contacts in Salesforce, and link to Opportunities via Opportunity_Contact__c.

Re-runnable: checks for existing contacts by email before creating duplicates.
"""

import sys
import csv
import re
from simple_salesforce import Salesforce

import sys as _sys
_sys.path.insert(0, r"C:\Users\cass\Work_Projects")
from _shared.sf_auth import creds as _sf_creds  # single source of truth for SF creds
_SF = _sf_creds()


DRY_RUN = "--dry-run" in sys.argv

PHONE_RE = re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE)
# Pattern: "c/o FirstName LastName" or "FirstName LastName phone/email"
NAME_PATTERNS = [
    re.compile(r'c/o\s+([A-Z][a-z]+)\s+([A-Z][a-zA-Z\'-]+)', re.IGNORECASE),
    re.compile(r'POC:\s*([A-Z][a-z]+)\s+([A-Z][a-zA-Z\'-]+)', re.IGNORECASE),
    re.compile(r'(?:Owner|PM|contact|manager|leasing)[:\s]+([A-Z][a-z]+)\s+([A-Z][a-zA-Z\'-]+)', re.IGNORECASE),
]


def normalize_phone(raw):
    """Extract digits and format as (XXX) XXX-XXXX."""
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == '1':
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return raw.strip()


def clean_text(raw):
    """Collapse whitespace, strip junk."""
    text = re.sub(r'\s+', ' ', raw).strip()
    text = re.sub(r'[^\x20-\x7E]', '', text)  # strip non-printable / unicode junk
    return text


def extract_company_name(text):
    """Try to extract the company/LLC name from the beginning of the text."""
    cleaned = clean_text(text)
    # Strip phone numbers before matching so they don't get captured
    no_phones = PHONE_RE.sub('', cleaned).strip()
    # Look for LLC, LP, Inc, Corp, Trust, HOA, Properties, Management, etc.
    company_patterns = [
        re.compile(r'^([\w\s&\'-]+(?:LLC|LP|Inc|Corp|Trust|HOA|Association|Enterprises|Properties|Investments|Realty|Development))', re.IGNORECASE),
        re.compile(r'^([\w\s&\'-]+(?:Management|Residential|Capital))', re.IGNORECASE),
    ]
    for pat in company_patterns:
        m = pat.search(no_phones)
        if m:
            name = m.group(1).strip()
            # Don't return if it's just one word
            if len(name.split()) >= 2:
                return name
    return None


def is_junk_name(name):
    """Return True if a name is clearly not a real contact name."""
    if not name:
        return True
    low = name.lower().strip()
    junk_starts = [
        'parcel', 'property management', 'property address', 'recorded owner',
        'same property', 'pin ', 'pin-', 'll denied', '2/', '1/', '3/',
        'phone:', 'email:', 'cell:', 'brothers property',
    ]
    for js in junk_starts:
        if low.startswith(js):
            return True
    digit_ratio = sum(1 for c in name if c.isdigit()) / max(len(name), 1)
    if digit_ratio > 0.3:
        return True
    junk_exact = {
        'property management', 'property manager', 'parcel id',
        'same property', 'ko property', 'brothers property',
        'office elwood', 'gold leaf',
    }
    if low in junk_exact:
        return True
    # Also catch "Parcel ID" even with trailing content
    if low.startswith('parcel id') or low.startswith('parcel #'):
        return True
    return False


def clean_last_name(name):
    """Trim address/junk from end of a name used as LastName."""
    if not name:
        return name
    # Strip trailing address patterns: "Name 4107 Izard St" -> "Name"
    # But keep company suffixes like LLC, LP, Trust
    cleaned = re.sub(r'\s+\d{3,5}\s+(?:N|S|E|W|North|South|East|West)?\s*\w+\s*(?:St|Ave|Rd|Dr|Blvd|Cir|Ct|Pl|Ln|Trl|Street|Avenue|Drive|Road).*$', '', name, flags=re.IGNORECASE)
    # Strip "Parcel ID..." from end
    cleaned = re.sub(r'\s*Parcel\s*(?:ID|#).*$', '', cleaned, flags=re.IGNORECASE)
    # Strip "Property Address..." from end
    cleaned = re.sub(r'\s*Property Address.*$', '', cleaned, flags=re.IGNORECASE)
    # Strip trailing phone-like patterns
    cleaned = re.sub(r'\s*Phone:.*$', '', cleaned, flags=re.IGNORECASE)
    # Strip " - apartment/unit info" from end
    cleaned = re.sub(r'\s*-\s*(?:\d+\s+)?(?:units?|apartments?).*$', '', cleaned, flags=re.IGNORECASE)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:80] if cleaned else name[:80]


def parse_contacts_from_field(raw_text):
    """
    Parse a free-text field into one or more contact dicts.
    Returns list of: {first_name, last_name, phone, email, company, description}
    """
    if not raw_text or not raw_text.strip():
        return []

    cleaned = clean_text(raw_text)
    emails = EMAIL_RE.findall(raw_text)
    phones = [normalize_phone(p) for p in PHONE_RE.findall(raw_text)]
    company = extract_company_name(raw_text)

    contacts = []

    # Try to find named people
    # Pattern 1: "c/o Name", "POC: Name", "Owner: Name", "PM Name"
    found_names = []
    for pat in NAME_PATTERNS:
        for m in pat.finditer(raw_text):
            found_names.append((m.group(1).strip(), m.group(2).strip()))

    # Words that are NOT person names
    skip_words = {
        'Property', 'Management', 'Real', 'Estate', 'Capital', 'Community',
        'Development', 'Senior', 'Living', 'Investment', 'Affordable', 'Housing',
        'Recorded', 'Office', 'Leasing', 'Same', 'True', 'Phone', 'Cell',
        'Email', 'Address', 'Parcel', 'Unit', 'Street', 'Avenue', 'Drive',
        'Building', 'Burlington', 'Apartments', 'Realty', 'Group', 'Services',
        'Partners', 'Properties', 'Investors', 'Commercial', 'Residential',
        'Mobile', 'Park', 'Prop', 'Mgmt', 'Onsite', 'Elwood', 'Office',
        'Burlington', 'Seldin', 'Haycon', 'Midtown', 'Plaza', 'Premier',
    }

    def is_valid_name(fn, ln):
        if fn in skip_words or ln in skip_words:
            return False
        if len(fn) < 2 or len(ln) < 2:
            return False
        # Reject if last name looks like a partial word or number
        if re.match(r'\d', ln):
            return False
        return True

    # Pattern 2: "FirstName LastName phone/email" — look for names near emails
    for email in emails:
        idx = raw_text.find(email)
        before = raw_text[max(0, idx - 60):idx]
        # Strip phone numbers from the "before" text to avoid matching digits as names
        before_clean = PHONE_RE.sub(' ', before).strip()
        name_match = re.search(r'([A-Z][a-z]+)\s+([A-Z][a-zA-Z\'-]+)\s*$', before_clean)
        if name_match:
            fn, ln = name_match.group(1), name_match.group(2)
            if is_valid_name(fn, ln) and (fn, ln) not in found_names:
                found_names.append((fn, ln))

    # Pattern 3: "FirstName LastName phone" without email
    if not found_names:
        for phone_raw in PHONE_RE.finditer(raw_text):
            idx = phone_raw.start()
            before = raw_text[max(0, idx - 60):idx]
            before_clean = PHONE_RE.sub(' ', before).strip()
            name_match = re.search(r'([A-Z][a-z]+)\s+([A-Z][a-zA-Z\'-]+)\s*$', before_clean)
            if name_match:
                fn, ln = name_match.group(1), name_match.group(2)
                if is_valid_name(fn, ln) and (fn, ln) not in found_names:
                    found_names.append((fn, ln))

    if found_names:
        # Create a contact for each named person
        for i, (fn, ln) in enumerate(found_names):
            contact = {
                'first_name': fn,
                'last_name': clean_last_name(ln),
                'phone': phones[min(i, len(phones) - 1)] if phones else None,
                'email': emails[min(i, len(emails) - 1)] if emails else None,
                'company': company,
                'description': cleaned,
            }
            contacts.append(contact)
    elif company:
        # No named person found, create a company contact
        contact = {
            'first_name': None,
            'last_name': clean_last_name(company),
            'phone': phones[0] if phones else None,
            'email': emails[0] if emails else None,
            'company': company,
            'description': cleaned,
        }
        contacts.append(contact)
    elif phones or emails:
        # No name or company, but we have contact info
        # Try to extract the first meaningful text chunk as a label
        no_phones = PHONE_RE.sub('', cleaned)
        no_emails = EMAIL_RE.sub('', no_phones)
        label = no_emails.split('.')[0].split(',')[0].split('(')[0].strip()
        label = re.sub(r'[-/\s]+$', '', label).strip()
        if label and len(label) > 2 and len(label) < 80 and not is_junk_name(label):
            contact = {
                'first_name': None,
                'last_name': clean_last_name(label),
                'phone': phones[0] if phones else None,
                'email': emails[0] if emails else None,
                'company': None,
                'description': cleaned,
            }
            contacts.append(contact)

    # Final filter: drop any contact with a junk last_name
    contacts = [c for c in contacts if not is_junk_name(c['last_name'])]

    return contacts


def main():
    print("=" * 60)
    print(f"ROE 9-25 Contact Import ({'DRY RUN' if DRY_RUN else 'LIVE'})")
    print("=" * 60)

    sf = Salesforce(
        username=_SF["username"],
        password=_SF["password"],
        security_token=_SF["token"],
    )

    # Get opps created today
    opps = sf.query_all("""
        SELECT Id, Name, Agreement_Name__c
        FROM Opportunity WHERE RecordType.Name = 'MDU' AND CreatedDate = TODAY
    """)['records']
    opp_by_agree = {r['Agreement_Name__c']: r['Id'] for r in opps if r.get('Agreement_Name__c')}
    print(f"Opportunities: {len(opps)}")

    # Load existing contacts by email to avoid duplicates
    existing_contacts = sf.query_all(
        "SELECT Id, Email FROM Contact WHERE Email != null"
    )['records']
    email_to_contact = {r['Email'].lower(): r['Id'] for r in existing_contacts if r.get('Email')}
    print(f"Existing contacts with email: {len(email_to_contact)}")

    # Load ROE data
    roe = []
    with open('C:/Users/cass/Work_Projects/SalesForce/roe_925_all_data.csv', 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            roe.append(row)

    # Parse and build contact + link records
    to_create = []  # (contact_dict, opp_id, role)
    to_link_existing = []  # (existing_contact_id, opp_id, role)

    for row in roe:
        agree_name = row['AgreeName'].strip()
        opp_id = opp_by_agree.get(agree_name)
        if not opp_id:
            continue

        # Parse Management Company
        mgmt_contacts = parse_contacts_from_field(row.get('Management Company', ''))
        for c in mgmt_contacts:
            if c['email'] and c['email'].lower() in email_to_contact:
                to_link_existing.append((email_to_contact[c['email'].lower()], opp_id, 'Property Manager'))
            else:
                to_create.append((c, opp_id, 'Property Manager'))

        # Parse Owner/Property Contact
        owner_contacts = parse_contacts_from_field(row.get('Owner/Property Contact', ''))
        for c in owner_contacts:
            if c['email'] and c['email'].lower() in email_to_contact:
                to_link_existing.append((email_to_contact[c['email'].lower()], opp_id, 'Property Owner'))
            else:
                to_create.append((c, opp_id, 'Property Owner'))

    print(f"\nNew contacts to create: {len(to_create)}")
    print(f"Existing contacts to link: {len(to_link_existing)}")

    if DRY_RUN:
        print("\n-- DRY RUN -- Sample new contacts (first 15):")
        for i, (c, opp_id, role) in enumerate(to_create[:15]):
            name = f"{c['first_name'] or ''} {c['last_name']}".strip()
            print(f"  {i+1}. {name}")
            if c['company']:
                print(f"     Company: {c['company']}")
            if c['phone']:
                print(f"     Phone: {c['phone']}")
            if c['email']:
                print(f"     Email: {c['email']}")
            print(f"     Role: {role}")
            print(f"     Desc: {c['description'][:100]}...")
            print()
        print(f"  ... and {len(to_create) - 15} more")
        print("\nRun without --dry-run to import.")
        return

    # Create contacts and link them
    created = 0
    linked = 0
    errors = []
    # Track emails we create this run to avoid duplicates within the batch
    created_emails = {}

    for c, opp_id, role in to_create:
        contact_id = None

        # Check if we already created this email in this batch
        if c['email'] and c['email'].lower() in created_emails:
            contact_id = created_emails[c['email'].lower()]
        else:
            # Create the contact
            contact_data = {
                'LastName': c['last_name'],
            }
            if c['first_name']:
                contact_data['FirstName'] = c['first_name']
            if c['phone']:
                contact_data['Phone'] = c['phone']
            if c['email']:
                contact_data['Email'] = c['email']

            try:
                result = sf.Contact.create(contact_data)
                contact_id = result['id']
                created += 1
                if c['email']:
                    created_emails[c['email'].lower()] = contact_id
                if created % 50 == 0:
                    print(f"  Contacts created: {created}...")
            except Exception as e:
                errors.append(f"Contact {c['last_name']}: {e}")
                continue

        # Link to opportunity
        if contact_id:
            try:
                sf.Opportunity_Contact__c.create({
                    'Opportunity__c': opp_id,
                    'Contact__c': contact_id,
                    'Role__c': role,
                })
                linked += 1
            except Exception as e:
                errors.append(f"Link {c['last_name']} -> {opp_id}: {e}")

    # Link existing contacts
    for contact_id, opp_id, role in to_link_existing:
        try:
            sf.Opportunity_Contact__c.create({
                'Opportunity__c': opp_id,
                'Contact__c': contact_id,
                'Role__c': role,
            })
            linked += 1
        except Exception as e:
            errors.append(f"Link existing {contact_id} -> {opp_id}: {e}")

    print(f"\n{'='*60}")
    print(f"COMPLETE")
    print(f"  Contacts created: {created}")
    print(f"  Links created: {linked}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for e in errors[:10]:
            print(f"    {e}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
