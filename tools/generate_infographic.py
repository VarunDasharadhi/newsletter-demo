import argparse
import base64
import io
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

KIE_BASE = "https://api.kie.ai/api/v1"
WEBHOOK_SITE = "https://webhook.site"


def build_image_prompt(research: dict, aspect: str = "overview") -> str:
    topic = research.get("topic", "")
    key_points = research.get("key_points", [])[:3]
    statistics = research.get("statistics", [])

    if aspect == "statistics":
        stats_text = "\n".join(f"- {s}" for s in statistics) if statistics else ""
        return (
            f"Create a clean, professional data infographic titled 'By the Numbers: {topic}'\n\n"
            f"Statistics to visualize as charts and callout boxes:\n{stats_text}\n\n"
            "Style: Bold numbers front and center, bar charts or donut charts, white background, "
            "navy blue (#003366) and teal (#0099CC) color scheme, minimal text, clear data labels. "
            "Professional business aesthetic."
        )

    points_text = "\n".join(f"- {p}" for p in key_points) if key_points else ""
    stats_text = ", ".join(statistics[:2]) if statistics else ""

    return (
        f"Create a clean, professional infographic about: {topic}\n\n"
        f"Key points to visualize:\n{points_text}\n\n"
        f"Statistics to highlight: {stats_text}\n\n"
        "Style: Modern data visualization, white background, navy blue (#003366) and "
        "teal (#0099CC) color scheme, minimal text labels, icons and simple charts. "
        "Professional business aesthetic. Clear hierarchy with a bold title at the top."
    )


def create_webhook_token() -> str:
    """Create a temporary webhook.site token and return the UUID."""
    resp = requests.post(f"{WEBHOOK_SITE}/token", json={"default_status": 200}, timeout=10)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create webhook.site token: HTTP {resp.status_code}")
    return resp.json()["uuid"]


def create_kie_task(api_key: str, prompt: str, callback_url: str) -> str:
    resp = requests.post(
        f"{KIE_BASE}/jobs/createTask",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "nano-banana-2",
            "input": {"prompt": prompt, "image_size": "1:1", "output_format": "png"},
            "callBackUrl": callback_url,
        },
        timeout=30,
    )
    if resp.status_code == 402:
        print("ERROR: Insufficient Kie.ai credits. Top up at kie.ai", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 401:
        print("ERROR: Invalid KIE_API_KEY", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        raise RuntimeError(f"Kie.ai createTask HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"Kie.ai error: {data.get('msg', data)}")

    task_id = data["data"]["taskId"]
    print(f"Kie.ai task created: {task_id}", file=sys.stderr)
    return task_id


def poll_webhook(uuid: str, timeout: int = 180) -> str:
    """Poll webhook.site until Kie.ai fires the callback. Returns image URL."""
    deadline = time.time() + timeout
    interval = 5

    while time.time() < deadline:
        time.sleep(interval)
        resp = requests.get(f"{WEBHOOK_SITE}/token/{uuid}/requests", timeout=15)
        if resp.status_code != 200:
            continue

        data = resp.json()
        if data.get("total", 0) == 0:
            elapsed = int(time.time() - (deadline - timeout))
            print(f"  Waiting for Kie.ai callback... [{elapsed}s]", file=sys.stderr)
            continue

        # Callback received — parse the body
        content = data["data"][0].get("content", "{}")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            raise RuntimeError(f"Unparseable callback: {content[:200]}")

        state = payload.get("data", {}).get("state", "")
        if state == "failed":
            raise RuntimeError("Kie.ai generation failed")

        result_json_str = payload.get("data", {}).get("resultJson", "{}")
        result = json.loads(result_json_str)
        urls = result.get("resultUrls", [])
        if not urls:
            raise RuntimeError("Callback received but no result URLs found")

        return urls[0]

    raise RuntimeError(f"Kie.ai callback timed out after {timeout}s")


def generate_image(api_key: str, prompt: str) -> bytes:
    print("Creating webhook.site receiver...", file=sys.stderr)
    uuid = create_webhook_token()
    callback_url = f"{WEBHOOK_SITE}/{uuid}"

    task_id = create_kie_task(api_key, prompt, callback_url)
    print(f"Waiting for Kie.ai to complete (callback → {callback_url})", file=sys.stderr)

    image_url = poll_webhook(uuid, timeout=180)
    print(f"Image ready: {image_url[:60]}...", file=sys.stderr)

    img_resp = requests.get(image_url, timeout=60)
    if img_resp.status_code != 200:
        raise RuntimeError(f"Image download failed: HTTP {img_resp.status_code}")
    return img_resp.content


def save_and_encode(image_bytes: bytes, path: str) -> dict:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
    except Exception as e:
        print(f"ERROR: Downloaded file is not a valid image: {e}", file=sys.stderr)
        sys.exit(1)

    img = Image.open(io.BytesIO(image_bytes))

    if img.width > 600:
        ratio = 600 / img.width
        img = img.resize((600, int(img.height * ratio)), Image.LANCZOS)

    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    img.save(path, "PNG", optimize=True)
    print(f"Saved infographic to {path}", file=sys.stderr)

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return {"image_path": path, "base64_data": b64}


def main():
    parser = argparse.ArgumentParser(description="Generate infographic PNG from research JSON")
    parser.add_argument("--aspect", default="overview", choices=["overview", "statistics"],
                        help="Visual focus: overview (default) or statistics")
    parser.add_argument("--output", default=".tmp/infographic.png",
                        help="Output PNG path (default: .tmp/infographic.png)")
    args = parser.parse_args()

    api_key = os.getenv("KIE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: KIE_API_KEY not set in .env", file=sys.stderr)
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

    topic = research.get("topic", "unknown topic")
    print(f"Generating {args.aspect} infographic for: {topic}", file=sys.stderr)

    prompt = build_image_prompt(research, args.aspect)
    image_bytes = generate_image(api_key, prompt)

    os.makedirs(".tmp", exist_ok=True)
    result = save_and_encode(image_bytes, args.output)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
