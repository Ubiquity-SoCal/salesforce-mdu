"""
Google Sheets connection helper.

First run opens a browser for OAuth login. After that, token.json is reused.
Credentials and token stored in the Google_Sheets folder.
"""

import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

CREDS_DIR = Path(r"C:\Users\cass\Work_Projects\Ting\Google_SoCal")
CREDS_FILE = list(CREDS_DIR.glob("client_secret_*.json"))[0]
TOKEN_FILE = CREDS_DIR / "token.json"


def get_credentials():
    """Get or refresh OAuth credentials."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

    return creds


def get_sheets_service():
    """Return an authenticated Google Sheets API service."""
    return build("sheets", "v4", credentials=get_credentials())


def get_drive_service():
    """Return an authenticated Google Drive API service."""
    return build("drive", "v3", credentials=get_credentials())


def list_shared_sheets(query=None):
    """List Google Sheets you have access to. Optional name filter."""
    drive = get_drive_service()
    q = "mimeType='application/vnd.google-apps.spreadsheet'"
    if query:
        q += f" and name contains '{query}'"

    results = drive.files().list(
        q=q,
        pageSize=50,
        fields="files(id, name, owners, modifiedTime)",
        orderBy="modifiedTime desc",
    ).execute()

    return results.get("files", [])


if __name__ == "__main__":
    print("Authenticating with Google...")
    print(f"Credentials: {CREDS_FILE.name}")
    print()

    # This will open a browser on first run
    creds = get_credentials()
    print("Authenticated successfully!\n")

    # List some sheets to prove it works
    print("Recent Google Sheets you have access to:")
    print("-" * 60)
    sheets = list_shared_sheets()
    if sheets:
        for s in sheets[:15]:
            owner = s.get("owners", [{}])[0].get("displayName", "Unknown")
            print(f"  {s['name']}")
            print(f"    ID: {s['id']}  |  Owner: {owner}")
    else:
        print("  No sheets found.")
