import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

from gsheets_auth import get_client

load_dotenv()


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def fetch_recipients(sheet_id: str, sheet_index: int = 0) -> list[dict]:
    client = get_client()
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.get_worksheet(sheet_index)
    rows = worksheet.get_all_records()

    recipients = []
    skipped = 0
    for row in rows:
        # normalise keys to lowercase
        row = {k.lower().strip(): str(v).strip() for k, v in row.items()}
        email = row.get("email", "")
        if not email or not is_valid_email(email):
            skipped += 1
            continue
        recipients.append({
            "name": row.get("name", ""),
            "email": email,
            "company": row.get("company", ""),
        })

    if skipped:
        print(f"[fetch_recipients] Skipped {skipped} row(s) with missing/invalid email", file=sys.stderr)

    return recipients


def main():
    parser = argparse.ArgumentParser(description="Fetch newsletter recipients from Google Sheets")
    parser.add_argument("--sheet-index", type=int, default=0, help="0-based worksheet index (default: 0)")
    args = parser.parse_args()

    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    if not sheet_id:
        print("ERROR: GOOGLE_SHEETS_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    if "spreadsheets/d/" in sheet_id:
        sheet_id = sheet_id.split("spreadsheets/d/")[1].split("/")[0]

    recipients = fetch_recipients(sheet_id, args.sheet_index)
    print(json.dumps(recipients, indent=2))


if __name__ == "__main__":
    main()
