# Workflow: Send Newsletter

## Objective
Send a personalised, AI-drafted HTML newsletter to all recipients in Google Sheets via Gmail.

## Required Inputs
| Input | Where to find it |
|---|---|
| Issue number | Increment from previous run |
| Subject line | e.g. `"Orca Transports — Industry Update #3"` |
| Google Sheet | Sheet must have columns: `Name`, `Email`, `Company` |

## Pre-flight Checklist
- [ ] `.env` has all 5 keys filled in (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GOOGLE_SHEETS_ID`, `ANTHROPIC_API_KEY`, `NEWS_API_KEY`)
- [ ] `credentials.json` is present in the project root (Google service account)
- [ ] Google Sheet is shared with the service account email
- [ ] Gmail App Password is active (not revoked)
- [ ] Dependencies installed: `pip install -r requirements.txt`

---

## Step 1 — Fetch Recipients
```bash
python tools/fetch_recipients.py > .tmp/recipients.json
```
- Reads `GOOGLE_SHEETS_ID` from `.env`
- Skips rows with blank or malformed emails (count logged to stderr)
- Output: `.tmp/recipients.json` — array of `{name, email, company}`

**If this fails:**
- `401 Unauthorized` → service account not shared on the sheet; open the sheet → Share → add service account email
- `File not found: credentials.json` → place the service account JSON file in the project root

---

## Step 2 — Fetch Industry News
```bash
python tools/fetch_industry_news.py > .tmp/news.json
```
- Queries NewsAPI for top 5 freight/logistics headlines published today
- Output: `.tmp/news.json` — array of `{title, description, url, source, published_at}`

**If this fails:**
- `426 Upgrade Required` → free NewsAPI plan only allows requests from localhost; use a server or upgrade plan
- `0 articles returned` → broaden query or try again later (may be a slow news day)
- Rate limit: free tier = 100 requests/day

---

## Step 3 — Send to Each Recipient
Loop through `.tmp/recipients.json` and for each recipient:

```bash
cat .tmp/news.json | python tools/draft_newsletter.py \
  --issue-number <N> \
  --recipient-name "<first name>" \
  | python tools/send_gmail.py \
  --to-email "<email>" \
  --to-name "<full name>" \
  --subject "<subject line>"
```

**Dry run first (strongly recommended):**
```bash
cat .tmp/news.json | python tools/draft_newsletter.py \
  --issue-number <N> \
  --recipient-name "Test" \
  | python tools/send_gmail.py \
  --to-email your@email.com \
  --to-name "Test" \
  --subject "TEST — Orca Newsletter #<N>" \
  --dry-run
```

**Batch send script** (run from project root):
```bash
python tools/fetch_recipients.py > .tmp/recipients.json
python tools/fetch_industry_news.py > .tmp/news.json

python - <<'EOF'
import json, subprocess, time, sys

ISSUE = 1              # change each run
SUBJECT = f"Orca Transports — Industry Update #{ISSUE}"

recipients = json.load(open(".tmp/recipients.json"))
sent, skipped = 0, 0

for r in recipients:
    first_name = r["name"].split()[0] if r["name"] else ""
    try:
        draft = subprocess.run(
            ["python", "tools/draft_newsletter.py",
             "--issue-number", str(ISSUE),
             "--recipient-name", first_name],
            stdin=open(".tmp/news.json"),
            capture_output=True, text=True, check=True
        )
        subprocess.run(
            ["python", "tools/send_gmail.py",
             "--to-email", r["email"],
             "--to-name", r["name"],
             "--subject", SUBJECT],
            input=draft.stdout,
            text=True, check=True
        )
        sent += 1
        time.sleep(1)  # avoid Gmail rate limits
    except subprocess.CalledProcessError as e:
        print(f"SKIP {r['email']}: {e.stderr.strip()}", file=sys.stderr)
        skipped += 1

log = f"Issue #{ISSUE}: sent={sent} skipped={skipped}\n"
open(".tmp/send_log.txt", "a").write(log)
print(log.strip())
EOF
```

---

## Error Handling

| Error | Action |
|---|---|
| `SMTPAuthenticationError` | Re-generate Gmail App Password; update `.env` |
| `SMTPRecipientsRefused` | Email address invalid — remove from sheet |
| `anthropic.RateLimitError` | Wait 60s, retry; if persistent, reduce batch size |
| `NewsAPI 426` | Free plan restriction — run from localhost or upgrade |
| Draft returns empty HTML | Check `ANTHROPIC_API_KEY` is valid and has credits |

---

## After the Run
- Check `.tmp/send_log.txt` for sent/skipped counts
- If any were skipped, review stderr output and fix the sheet or retry individually
- Increment the issue number for the next run
- If you discovered a new constraint (rate limit, API quirk), document it in the relevant step above
