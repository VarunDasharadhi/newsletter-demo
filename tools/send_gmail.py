import argparse
import os
import re
import smtplib
import sys
from base64 import b64decode
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser

from dotenv import load_dotenv

load_dotenv()


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return " ".join(self._parts).strip()


def html_to_plain(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def extract_and_cid_images(html: str) -> tuple[str, list[tuple[str, str, bytes]]]:
    """
    Find all base64 data URIs in src attributes, replace with cid: references,
    and return the modified HTML plus a list of (cid, mime_subtype, image_bytes).
    """
    attachments = []
    pattern = re.compile(r'src="data:image/(\w+);base64,([^"]+)"')

    def replace(match):
        mime_subtype = match.group(1)   # e.g. "png", "jpeg"
        b64_data = match.group(2)
        idx = len(attachments) + 1
        cid = f"img{idx:03d}@orca"
        try:
            image_bytes = b64decode(b64_data)
        except Exception:
            return match.group(0)       # leave untouched if decode fails
        attachments.append((cid, mime_subtype, image_bytes))
        return f'src="cid:{cid}"'

    modified_html = pattern.sub(replace, html)
    return modified_html, attachments


def send_email(
    gmail_address: str,
    app_password: str,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    dry_run: bool = False,
) -> None:
    plain_body = html_to_plain(html_body)

    # Convert base64 data URIs → CID references and collect inline images
    cid_html, inline_images = extract_and_cid_images(html_body)

    # Build MIME structure:
    # multipart/mixed
    #   multipart/alternative
    #     text/plain
    #     multipart/related
    #       text/html  (cid: refs)
    #       image/png  (inline, Content-ID: <cid>)  × N
    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"] = f"Orca Transports <{gmail_address}>"
    outer["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(plain_body, "plain"))

    related = MIMEMultipart("related")
    related.attach(MIMEText(cid_html, "html"))

    for cid, mime_subtype, image_bytes in inline_images:
        img_part = MIMEImage(image_bytes, _subtype=mime_subtype)
        img_part.add_header("Content-ID", f"<{cid}>")
        img_part.add_header("Content-Disposition", "inline")
        related.attach(img_part)

    alternative.attach(related)
    outer.attach(alternative)

    if dry_run:
        print(f"[DRY RUN] Would send to {to_email} — Subject: {subject}")
        print(f"  Inline images: {len(inline_images)}")
        print("--- HTML preview (first 300 chars) ---")
        print(cid_html[:300])
        return

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to_email, outer.as_string())

    print(f"Sent to {to_email} ({len(inline_images)} inline image(s) attached)")


def main():
    parser = argparse.ArgumentParser(description="Send HTML newsletter via Gmail SMTP")
    parser.add_argument("--to-email", required=True, help="Recipient email address")
    parser.add_argument("--to-name", default="", help="Recipient display name")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--dry-run", action="store_true", help="Print email details without sending")
    args = parser.parse_args()

    gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_address or not app_password:
        print("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env", file=sys.stderr)
        sys.exit(1)

    html_body = sys.stdin.buffer.read().decode("utf-8").strip()
    if not html_body:
        print("ERROR: No HTML body received on stdin", file=sys.stderr)
        sys.exit(1)

    send_email(gmail_address, app_password, args.to_email, args.to_name, args.subject, html_body, args.dry_run)


if __name__ == "__main__":
    main()
