import argparse
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for recent information about a topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
}

SYSTEM_PROMPT = """You are a research analyst. When given a topic, produce a comprehensive research brief as valid JSON.

Output ONLY a JSON object with exactly these keys:
- topic: string
- summary: string (2-3 sentences overview)
- key_points: array of strings (4-6 key findings)
- statistics: array of strings (3-5 notable stats or data points)
- insights: array of strings (3-4 strategic implications or takeaways)
- sources: array of strings (URLs or publication names cited)

No markdown, no code fences, no explanation — just the raw JSON object."""


def duckduckgo_search(query: str) -> str:
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=10,
        )
        data = resp.json()
        parts = []
        if data.get("AbstractText"):
            parts.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                parts.append(topic["Text"])
        return " ".join(parts)
    except Exception:
        return ""


def parse_research_json(raw: str, topic: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON from surrounding text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    return {
        "topic": data.get("topic", topic),
        "summary": data.get("summary", ""),
        "key_points": data.get("key_points", []),
        "statistics": data.get("statistics", []),
        "insights": data.get("insights", []),
        "sources": data.get("sources", []),
    }


def call_groq_synthesis_fallback(client: Groq, topic: str) -> dict:
    print("Using LLM synthesis fallback...", file=sys.stderr)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Research this topic thoroughly: {topic}"},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = response.choices[0].message.content or ""
    return parse_research_json(raw, topic)


def call_groq_with_web_search(client: Groq, topic: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Research this topic thoroughly: {topic}"},
    ]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=[WEB_SEARCH_TOOL],
        tool_choice="auto",
        temperature=0.3,
        max_tokens=1500,
    )

    msg = response.choices[0].message

    if msg.tool_calls:
        query = msg.tool_calls[0].function.arguments
        try:
            query = json.loads(query).get("query", topic)
        except Exception:
            query = topic

        print(f"Searching web for: {query}", file=sys.stderr)
        search_result = duckduckgo_search(query)

        messages.append({"role": "assistant", "content": None, "tool_calls": msg.tool_calls})
        messages.append({
            "role": "tool",
            "tool_call_id": msg.tool_calls[0].id,
            "content": search_result or f"No results found. Use your knowledge about: {topic}",
        })

        response2 = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.3,
            max_tokens=1500,
        )
        raw = response2.choices[0].message.content or ""
    else:
        raw = msg.content or ""

    result = parse_research_json(raw, topic)
    if not result["summary"]:
        raise ValueError("Empty response from Groq")
    return result


def main():
    parser = argparse.ArgumentParser(description="Research a topic using Groq AI")
    parser.add_argument("--topic", required=True, help="Topic to research")
    args = parser.parse_args()

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GROQ_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    client = Groq(api_key=api_key)
    topic = args.topic.strip()

    print(f"Researching: {topic}", file=sys.stderr)

    for attempt in range(2):
        try:
            result = call_groq_with_web_search(client, topic)
            print(json.dumps(result, indent=2))
            return
        except Exception as e:
            err = str(e)
            if "429" in err and attempt == 0:
                print("Rate limited. Waiting 5s...", file=sys.stderr)
                time.sleep(5)
                continue
            if "401" in err:
                print("ERROR: Invalid GROQ_API_KEY", file=sys.stderr)
                sys.exit(1)
            print(f"Web search path failed ({e}). Falling back to pure synthesis.", file=sys.stderr)
            break

    try:
        result = call_groq_synthesis_fallback(client, topic)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"ERROR: Groq synthesis failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
