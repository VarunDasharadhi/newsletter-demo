import argparse
import base64
import io
import json
import os
import sys

import anthropic
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

BRAND_LOGO_PATH = "brand_assets/brand_logo.png"

# Claude writes these tokens; Python replaces them after generation
HEADER_PLACEHOLDER = "{{HEADER_BLOCK}}"
INFOGRAPHIC_PLACEHOLDERS = ["{{INFOGRAPHIC_1}}", "{{INFOGRAPHIC_2}}"]

SYSTEM_PROMPT = """You are a newsletter writer for Orca Transports Ltd, a freight and logistics company.
Write a single-topic deep-dive HTML newsletter based on the research brief provided.

Brand guidelines (taken directly from the company logo):
- Primary colour: #003366 (deep navy blue) for section headings, borders, dividers
- Accent colour: #0099CC (teal) for bullet borders, links, highlights
- Background accent: #E8DCC8 (cream/beige) for callout boxes and stat panels
- Text on dark: #FFFFFF (white)
- Body text: #333333
- Font: Arial, sans-serif throughout
- Tone: Clear, direct, and informative. Write the way a knowledgeable colleague would brief you. No marketing fluff.
- Always sign off from "The Orca Transports Team"

Writing style:
- Write naturally. Short sentences. Active voice.
- No em dashes or en dashes anywhere. Use a comma or a full stop instead.
- No corporate jargon or filler phrases.
- Spell-check every word before writing.

HTML requirements:
- Inline CSS only (no <style> blocks, many email clients strip them)
- Single-column layout, max-width 600px, centred with margin:0 auto
- The header is handled externally. Write {{HEADER_BLOCK}} exactly once at the very top, then continue with the body.
- Opening paragraph greeting the recipient by name (below the header)
- Place {{INFOGRAPHIC_1}} immediately after the intro paragraph
- Summary section with a 2-3 sentence overview
- "Key Findings" section: 4-6 bullet points each with a 4px left border in #0099CC and padding-left:12px
- "By the Numbers" callout box: background #E8DCC8, border-left:4px solid #003366, padding:16px, listing statistics
- Place {{INFOGRAPHIC_2}} immediately after the "By the Numbers" box
- "Insights & Implications" section: 3-4 bullet points (keep each under 2 sentences)
- Sources as a small-font list at the bottom (font-size:12px, color:#666)
- Footer in #003366 background with white text, unsubscribe placeholder, and "© Orca Transports Ltd"
- Output ONLY the raw HTML. No markdown, no explanation, no code fences.

IMPORTANT - placeholders:
- Write {{HEADER_BLOCK}} once at the top (do NOT build the header yourself)
- Write {{INFOGRAPHIC_1}} after the intro paragraph
- Write {{INFOGRAPHIC_2}} after the "By the Numbers" box
- Do NOT write any <img> tags or base64 data yourself"""


def load_logo_base64(path: str) -> tuple[str, str] | tuple[None, None]:
    if not path or not os.path.exists(path):
        return None, None
    try:
        img = Image.open(path).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, "image/png"
    except Exception as e:
        print(f"WARNING: Could not load logo from {path}: {e}", file=sys.stderr)
        return None, None


def load_infographic_base64(path: str) -> str | None:
    if not path or not os.path.exists(path):
        print(f"WARNING: Infographic not found at {path}, sending without image", file=sys.stderr)
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_header(logo_b64: str | None, logo_mime: str | None, topic: str) -> str:
    if logo_b64 and logo_mime:
        logo_html = (
            f'<img src="data:{logo_mime};base64,{logo_b64}" '
            f'alt="Orca Transports" '
            f'style="width:110px;height:110px;border-radius:50%;'
            f'border:3px solid #E8DCC8;display:block;margin:0 auto 14px auto;" />'
        )
    else:
        logo_html = (
            '<div style="width:110px;height:110px;border-radius:50%;background:#0099CC;'
            'border:3px solid #E8DCC8;margin:0 auto 14px auto;display:flex;align-items:center;'
            'justify-content:center;font-family:Arial,sans-serif;font-size:28px;'
            'color:#fff;font-weight:bold;">OT</div>'
        )

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background-color:#003366;border-bottom:4px solid #0099CC;">'
        "<tr><td style=\"padding:32px 24px 28px;text-align:center;\">"
        + logo_html
        + '<div style="color:#E8DCC8;font-family:Arial,sans-serif;font-size:10px;'
        'letter-spacing:3px;text-transform:uppercase;margin-bottom:10px;">'
        "ORCA TRANSPORTS LTD</div>"
        '<div style="color:#ffffff;font-family:Arial,sans-serif;font-size:22px;'
        'font-weight:bold;line-height:1.3;margin-bottom:8px;">'
        + topic
        + "</div>"
        '<div style="color:#0099CC;font-family:Arial,sans-serif;font-size:12px;'
        'letter-spacing:1px;text-transform:uppercase;">Industry Intelligence Report</div>'
        "</td></tr></table>"
    )


def ensure_closed(html: str) -> str:
    """Append missing closing tags if Claude hit the token limit mid-output."""
    tail = html.strip()
    if not tail.endswith("</html>"):
        if "</body>" not in tail:
            html = html.rstrip() + "\n</body>\n</html>\n"
        else:
            html = html.rstrip() + "\n</html>\n"
    return html


def inject_images(
    html: str,
    logo_b64: str | None,
    logo_mime: str | None,
    infographic_b64_list: list[str | None],
    topic: str,
) -> str:
    header_html = build_header(logo_b64, logo_mime, topic)
    html = html.replace(HEADER_PLACEHOLDER, header_html)

    for i, placeholder in enumerate(INFOGRAPHIC_PLACEHOLDERS):
        b64 = infographic_b64_list[i] if i < len(infographic_b64_list) else None
        if b64:
            tag = (
                f'<img src="data:image/png;base64,{b64}" '
                f'alt="Infographic: {topic}" '
                f'style="width:100%;max-width:600px;display:block;margin:20px auto;border-radius:6px;" />'
            )
        else:
            tag = ""
        html = html.replace(placeholder, tag)

    return ensure_closed(html)


def build_user_prompt(research: dict, topic: str, recipient_name: str) -> str:
    name = recipient_name or "there"
    key_points = "\n".join(f"- {kp}" for kp in research.get("key_points", []))
    statistics = "\n".join(f"- {s}" for s in research.get("statistics", []))
    insights = "\n".join(f"- {i}" for i in research.get("insights", []))
    sources = ", ".join(research.get("sources", []))

    return f"""Write a deep-dive newsletter on: {topic}

Recipient first name: {name}

RESEARCH BRIEF:
Summary: {research.get('summary', '')}

Key Points:
{key_points}

Statistics:
{statistics}

Insights:
{insights}

Sources: {sources}

Remember: write {{{{HEADER_BLOCK}}}} once at the very top, then {{{{INFOGRAPHIC_1}}}} after the intro paragraph, then {{{{INFOGRAPHIC_2}}}} after the "By the Numbers" box.
End with a CTA to reply with questions or visit orca-transports.onrender.com."""


def draft_from_research(
    research: dict,
    topic: str,
    recipient_name: str,
    infographic_paths: list[str],
    api_key: str,
) -> str:
    logo_b64, logo_mime = load_logo_base64(BRAND_LOGO_PATH)
    infographic_b64_list = [load_infographic_base64(p) for p in infographic_paths]

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = build_user_prompt(research, topic, recipient_name)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    html = message.content[0].text
    return inject_images(html, logo_b64, logo_mime, infographic_b64_list, topic)


def main():
    parser = argparse.ArgumentParser(description="Draft HTML newsletter from research JSON using Claude")
    parser.add_argument("--topic", default="", help="Topic name (defaults to topic field in research JSON)")
    parser.add_argument("--infographic", nargs="+", default=[".tmp/infographic.png"],
                        help="One or more infographic PNG paths (first after intro, second after stats)")
    parser.add_argument("--recipient-name", default="", help="Recipient first name for personalisation")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: No research JSON received on stdin", file=sys.stderr)
        sys.exit(1)

    try:
        research = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    topic = args.topic or research.get("topic", "Newsletter")

    try:
        html = draft_from_research(research, topic, args.recipient_name, args.infographic, api_key)
    except anthropic.RateLimitError:
        print("ERROR: Anthropic rate limit hit. Wait 60s and retry.", file=sys.stderr)
        sys.exit(1)

    if not html.strip():
        print("ERROR: Claude returned empty content", file=sys.stderr)
        sys.exit(1)

    sys.stdout.buffer.write(html.encode("utf-8"))


if __name__ == "__main__":
    main()
