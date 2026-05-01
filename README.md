# Newsletter Demo

An AI-powered newsletter pipeline built on the **WAT framework** (Workflows, Agents, Tools). Given a topic, the system researches it, generates branded infographics, writes a personalised HTML newsletter, and sends it to a recipient list from Google Sheets — all from a single command.

---

## How It Works

The pipeline has three layers:

| Layer | Role |
|---|---|
| **Workflows** | Markdown SOPs in `workflows/` that define exactly what to do and in what order |
| **Agent** | Claude reads the workflow, makes decisions, and calls the right tools in sequence |
| **Tools** | Python scripts in `tools/` that handle all deterministic execution |

This separation keeps AI focused on orchestration and lets deterministic code handle the parts that need to be reliable.

---

## Pipeline Overview

```
Topic input
    |
    +-- research_topic.py        (Groq / LLaMA-3.3-70b + DuckDuckGo)
    |
    +-- generate_infographic.py  (Kie.ai, overview + statistics aspects)
    |
    +-- draft_from_research.py   (Claude, branded HTML, image placeholders)
    |
    +-- send_gmail.py            (SMTP, inline base64 images, dry-run mode)
    |
    +-- record_newsletter_send.py (Google Sheets send log)
```

---

## Project Structure

```
tools/
  fetch_recipients.py       Pull Name/Email/Company rows from Google Sheets
  research_topic.py         Research a topic with Groq AI and DuckDuckGo
  generate_infographic.py   Generate two branded infographics via Kie.ai
  draft_from_research.py    Write a branded HTML newsletter with Claude
  draft_newsletter.py       News-feed based newsletter drafter (original flow)
  fetch_industry_news.py    Fetch top logistics headlines from NewsAPI
  send_gmail.py             Send HTML email via Gmail SMTP
  record_newsletter_send.py Append send stats to Google Sheets
  gsheets_auth.py           Shared Google service account auth helper

workflows/
  newsletter_from_topic.md  Full 6-step SOP: research to send to record
  send_newsletter.md        News-feed based send flow

brand_assets/
  brand_logo.png            Orca Transports brand logo (injected post-Claude)

.tmp/                       Intermediate files (gitignored, safe to delete)
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment variables**

Copy `.env.example` to `.env` and fill in all values:

```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GOOGLE_SHEETS_ID=your_sheet_id
ANTHROPIC_API_KEY=sk-ant-...
NEWS_API_KEY=...
GROQ_API_KEY=gsk_...
KIE_API_KEY=...
```

**3. Add Google credentials**

Place your Google service account JSON file at `credentials.json` in the project root and share your Google Sheet with the service account email.

---

## Usage

### Full pipeline from a topic

```bash
TOPIC="AI in supply chain logistics"
SUBJECT="Orca Transports: Special Report on AI in Logistics"

# Steps 1 and 2 run in parallel
python tools/fetch_recipients.py > .tmp/recipients.json &
python tools/research_topic.py --topic "$TOPIC" > .tmp/research.json &
wait

# Generate two infographics
cat .tmp/research.json | python tools/generate_infographic.py \
  --aspect overview --output .tmp/infographic.png > .tmp/infographic_meta.json

cat .tmp/research.json | python tools/generate_infographic.py \
  --aspect statistics --output .tmp/infographic_2.png > .tmp/infographic_2_meta.json

# Preview before sending
cat .tmp/research.json | python tools/draft_from_research.py \
  --topic "$TOPIC" \
  --infographic .tmp/infographic.png .tmp/infographic_2.png \
  --recipient-name "Test" \
  > .tmp/draft_preview.html
```

Open `.tmp/draft_preview.html` in a browser, then run the batch send (see `workflows/newsletter_from_topic.md`).

### Dry-run send to yourself

```bash
cat .tmp/draft_preview.html | python tools/send_gmail.py \
  --to-email you@email.com \
  --to-name "Test" \
  --subject "TEST - Newsletter" \
  --dry-run
```

---

## APIs Used

| Service | Purpose |
|---|---|
| [Groq](https://console.groq.com) | Topic research via LLaMA-3.3-70b |
| [Kie.ai](https://kie.ai) | AI infographic generation |
| [Anthropic Claude](https://anthropic.com) | HTML newsletter drafting |
| [NewsAPI](https://newsapi.org) | Industry news headlines |
| Gmail SMTP | Email delivery |
| Google Sheets API | Recipient list and send log |

---

## Token Safety

Never pass raw base64 image data directly in Claude prompts. A 500 KB image is roughly 125k tokens and will exhaust the per-minute quota in a single call.

The correct pattern used in this project:

```python
# Claude writes a placeholder
prompt = "Insert the logo here: {{BRAND_LOGO}}"

# Python injects the image bytes after Claude responds
html = call_claude(prompt)
html = html.replace("{{BRAND_LOGO}}", f'<img src="data:image/png;base64,{base64_logo}">')
```

---

## Workflows

Full step-by-step instructions with error handling are in:

- `workflows/newsletter_from_topic.md` - research-driven pipeline
- `workflows/send_newsletter.md` - news-feed-driven pipeline
