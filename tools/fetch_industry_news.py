import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_URL = "https://newsapi.org/v2/everything"
QUERY = "freight OR logistics OR trucking OR \"supply chain\""


def fetch_news(api_key: str, page_size: int = 5) -> list[dict]:
    params = {
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": api_key,
    }
    resp = requests.get(NEWSAPI_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {data.get('message', 'unknown error')}")

    articles = data.get("articles", [])
    if not articles:
        raise RuntimeError("NewsAPI returned 0 articles — check your API key or query")

    return [
        {
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "url": a.get("url", ""),
            "source": a.get("source", {}).get("name", ""),
            "published_at": a.get("publishedAt", ""),
        }
        for a in articles
        if a.get("title") and a.get("description")
    ]


def main():
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        print("ERROR: NEWS_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    try:
        articles = fetch_news(api_key.strip())
        print(json.dumps(articles, indent=2))
    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code} from NewsAPI — {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
