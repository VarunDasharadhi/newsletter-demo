# Workflow: Newsletter from Topic

## Objective
Given any topic, research it with Groq AI, generate two infographics via Kie.ai, write a branded HTML newsletter using Claude, send it to all recipients in Google Sheets via Gmail, and record the send result back to Google Sheets.

## Required Inputs
| Input | Where to find it |
|---|---|
| Topic | Supplied at runtime (e.g. `"AI in supply chain logistics"`) |
| Subject line | e.g. `"Orca Transports: AI in Logistics"` |
| Google Sheet | Must have columns: `Name`, `Email`, `Company` |

## Pre-flight Checklist
- [ ] `.env` has all keys filled in: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GOOGLE_SHEETS_ID`, `ANTHROPIC_API_KEY`, `NEWS_API_KEY`, `GROQ_API_KEY`, `KIE_API_KEY`
- [ ] `credentials.json` is present in the project root (Google service account with edit access to the sheet)
- [ ] Google Sheet is shared with the service account email
- [ ] Gmail App Password is active (not revoked)
- [ ] Dependencies installed: `pip install -r requirements.txt`

---

## Step 1 - Fetch Recipients
```bash
python tools/fetch_recipients.py > .tmp/recipients.json
```
- Output: `.tmp/recipients.json` - array of `{name, email, company}`

**If this fails:** See `workflows/send_newsletter.md` Step 1 for troubleshooting.

---

## Step 2 - Research the Topic
```bash
python tools/research_topic.py --topic "AI in supply chain logistics" > .tmp/research.json
```
- Calls Groq API with `llama-3.3-70b-versatile`
- Attempts DuckDuckGo web search tool; falls back to pure LLM synthesis if search yields nothing
- Output: `.tmp/research.json` - `{topic, summary, key_points[], statistics[], insights[], sources[]}`

**If this fails:**
- `Invalid GROQ_API_KEY` - check `console.groq.com`, update `.env`
- `429 rate limit` - wait 60s and retry
- Output is malformed JSON - LLM returned non-JSON; check stderr, rerun

> **Note:** Steps 1 and 2 have no dependency on each other and can run simultaneously in separate terminals.

---

## Step 3 - Generate Two Infographics
Run both in sequence (each takes up to 3 minutes to complete):

```bash
# Overview infographic (key points and topic summary)
cat .tmp/research.json | python tools/generate_infographic.py \
  --aspect overview \
  --output .tmp/infographic.png \
  > .tmp/infographic_meta.json

# Statistics infographic (numbers and data)
cat .tmp/research.json | python tools/generate_infographic.py \
  --aspect statistics \
  --output .tmp/infographic_2.png \
  > .tmp/infographic_2_meta.json
```

- Each image is resized to 600px wide and saved as PNG
- `--aspect overview` focuses on key points; `--aspect statistics` focuses on charts and numbers

**If this fails:**
- `402` - add credits to your Kie.ai account
- `429` - wait 30s and retry
- `not a valid image` - generation is non-deterministic; rerun
- Network timeout - check internet connection and retry

---

## Step 4 - Preview the Draft (recommended before batch send)
```bash
cat .tmp/research.json | python tools/draft_from_research.py \
  --topic "AI in supply chain logistics" \
  --infographic .tmp/infographic.png .tmp/infographic_2.png \
  --recipient-name "Test" \
  > .tmp/draft_preview.html
```
Open `.tmp/draft_preview.html` in a browser to check layout. You should see two infographic images: one after the intro paragraph and one after the "By the Numbers" section.

**Dry-run send to yourself:**
```bash
cat .tmp/draft_preview.html | python tools/send_gmail.py \
  --to-email your@email.com \
  --to-name "Test" \
  --subject "TEST - Orca Special Report" \
  --dry-run
```

---

## Step 5 - Batch Send to All Recipients
```bash
python - <<'EOF'
import json, subprocess, time, sys

TOPIC = "AI in supply chain logistics"   # change this each run
SUBJECT = f"Orca Transports: Special Report on {TOPIC}"

recipients = json.load(open(".tmp/recipients.json"))
sent, skipped = 0, 0

for r in recipients:
    first_name = r["name"].split()[0] if r["name"] else ""
    try:
        draft = subprocess.run(
            ["python", "tools/draft_from_research.py",
             "--topic", TOPIC,
             "--infographic", ".tmp/infographic.png", ".tmp/infographic_2.png",
             "--recipient-name", first_name],
            stdin=open(".tmp/research.json"),
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

print(f"Done. sent={sent} skipped={skipped}")
open(".tmp/send_log.txt", "a").write(f"Topic '{TOPIC}': sent={sent} skipped={skipped}\n")
EOF
```

Note the `sent` and `skipped` counts from the output - you need them for Step 6.

---

## Step 6 - Record to Google Sheets
```bash
python tools/record_newsletter_send.py \
  --topic "AI in supply chain logistics" \
  --subject "Orca Transports: Special Report on AI in supply chain logistics" \
  --sent <N> \
  --skipped <M> \
  --issue 1
```
- Appends a row to the "Send Log" tab in your Google Sheet
- If the "Send Log" tab does not exist yet, it creates it with headers automatically
- Columns: `Date`, `Issue`, `Topic`, `Subject`, `Sent`, `Skipped`

**If this fails:**
- `credentials.json not found` - place your Google service account file in the project root
- `WorksheetNotFound` - the script creates the tab automatically; if you see this, check that the service account has edit access to the spreadsheet
- `403 permission denied` - share the spreadsheet with the service account email

---

## Complete One-Shot Pipeline
```bash
TOPIC="AI in supply chain logistics"
SUBJECT="Orca Transports: Special Report on AI in Logistics"

python tools/fetch_recipients.py > .tmp/recipients.json &
python tools/research_topic.py --topic "$TOPIC" > .tmp/research.json &
wait

cat .tmp/research.json | python tools/generate_infographic.py --aspect overview --output .tmp/infographic.png > .tmp/infographic_meta.json
cat .tmp/research.json | python tools/generate_infographic.py --aspect statistics --output .tmp/infographic_2.png > .tmp/infographic_2_meta.json

# Preview before sending
cat .tmp/research.json | python tools/draft_from_research.py \
  --topic "$TOPIC" \
  --infographic .tmp/infographic.png .tmp/infographic_2.png \
  --recipient-name "Test" \
  > .tmp/draft_preview.html

# Open .tmp/draft_preview.html in browser, then run Step 5 batch send, then Step 6 record
```

---

## Error Handling

| Error | Action |
|---|---|
| `Invalid GROQ_API_KEY` | Check `console.groq.com`; update `.env` |
| Groq returns non-JSON | Rerun (LLM occasionally fails structured output) |
| `KIE_API_KEY` invalid or 402 | Check kie.ai account; update `.env` or add credits |
| `not a valid image` from generate_infographic | Rerun; image generation is non-deterministic |
| `SMTPAuthenticationError` | Re-generate Gmail App Password; update `.env` |
| `anthropic.RateLimitError` in draft_from_research | Wait 60s, retry; reduce batch size if persistent |
| Email too large (>25 MB) | The infographic resize (600px) should prevent this; if it persists, reduce to 400px in `generate_infographic.py` |
| `credentials.json not found` in record step | Place Google service account JSON in project root |
| `403` on record step | Share the spreadsheet with the service account email (with Editor access) |

---

## After the Run
- Check `.tmp/send_log.txt` for sent/skipped counts
- Check the "Send Log" tab in Google Sheets for the recorded entry
- `.tmp/infographic.png` and `.tmp/infographic_2.png` can be reused for social media or slides
- Document any new API quirks discovered in the relevant step above
