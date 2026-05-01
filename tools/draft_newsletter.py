import argparse
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a professional newsletter writer for Orca Transports Ltd, a freight and logistics company.
Your job is to write a concise, engaging HTML newsletter email for industry professionals.

Brand guidelines:
- Primary colour: #003366 (deep navy blue)
- Accent colour: #0077CC (bright blue)
- Font: Arial, sans-serif
- Tone: Professional, informative, confident — like a trusted industry expert
- Always sign off from "The Orca Transports Team"

HTML requirements:
- Inline CSS only (no <style> blocks — many email clients strip them)
- Single-column layout, max-width 600px, centred
- Header bar in #003366 with white company name
- Each news section: bold headline as a link, 2–3 sentence summary, one sentence on why it matters for freight operators
- Footer with unsubscribe placeholder and company name
- Output ONLY the raw HTML — no markdown, no explanation, no code fences"""


def draft_newsletter(articles: list[dict], issue_number: int, recipient_name: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | {a['published_at'][:10]}\n{a['description']}\nURL: {a['url']}"
        for i, a in enumerate(articles)
    )

    user_prompt = f"""Write Issue #{issue_number} of the Orca Transports newsletter.

Recipient first name: {recipient_name or 'there'}

Here are this week's industry news articles to feature:

{articles_text}

Write 3–4 sections (one per article). Each section should:
1. Use the article headline as a linked heading
2. Summarise the story in 2–3 sentences
3. Add one sentence connecting it to freight operators / Orca Transports clients

End with a short closing paragraph and a CTA to reply with questions or visit orca-transports.onrender.com."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Draft HTML newsletter using Claude")
    parser.add_argument("--issue-number", type=int, default=1, help="Newsletter issue number")
    parser.add_argument("--recipient-name", type=str, default="", help="Recipient first name for personalisation")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No news JSON received on stdin", file=sys.stderr)
        sys.exit(1)

    try:
        articles = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    html = draft_newsletter(articles, args.issue_number, args.recipient_name, api_key.strip())
    print(html)


if __name__ == "__main__":
    main()
