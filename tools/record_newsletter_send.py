import argparse
import os
import sys
from datetime import date

import gspread
from dotenv import load_dotenv

from gsheets_auth import get_client

load_dotenv()

LOG_SHEET_NAME = "Send Log"
HEADERS = ["Date", "Issue", "Topic", "Subject", "Sent", "Skipped"]


def get_or_create_log_sheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(LOG_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=LOG_SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS)
        print(f"Created '{LOG_SHEET_NAME}' worksheet with headers", file=sys.stderr)
        return ws


def record_send(sheet_id: str, topic: str, subject: str, sent: int, skipped: int, issue: int) -> None:
    client = get_client()
    spreadsheet = client.open_by_key(sheet_id)
    ws = get_or_create_log_sheet(spreadsheet)

    row = [date.today().isoformat(), issue, topic, subject, sent, skipped]
    ws.append_row(row)
    print(f"Recorded to '{LOG_SHEET_NAME}': issue={issue} sent={sent} skipped={skipped}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Record a newsletter send to Google Sheets")
    parser.add_argument("--topic", required=True, help="Newsletter topic")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--sent", type=int, required=True, help="Number of emails sent")
    parser.add_argument("--skipped", type=int, required=True, help="Number of recipients skipped")
    parser.add_argument("--issue", type=int, default=1, help="Issue number (default: 1)")
    args = parser.parse_args()

    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
    if not sheet_id:
        print("ERROR: GOOGLE_SHEETS_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    # Strip full URL if the env value is a URL rather than just the ID
    if "spreadsheets/d/" in sheet_id:
        sheet_id = sheet_id.split("spreadsheets/d/")[1].split("/")[0]

    try:
        record_send(sheet_id, args.topic, args.subject, args.sent, args.skipped, args.issue)
    except FileNotFoundError:
        print("ERROR: credentials.json not found in project root", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
