#!/usr/bin/env python3

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


SYSTEM_PROMPT = """You convert raw notes into recall items.

Return JSON only in the form:
{
  "items": [
    {
      "content_type": "concept|vocab|sentence|raw_fragment|pronunciation|error",
      "presentation_mode": "question|raw_note",
      "prompt": "...",
      "answer": "...",
      "source": "provider:deepseek"
    }
  ]
}

Rules:
- Stay within the given topic and notes.
- Do not invent facts beyond the notes.
- For mode=question, every item must be question.
- For mode=raw_note, every item must be raw_note.
- For mode=mixed, you may mix question and raw_note items in one batch.
- raw_note items may leave answer empty.
- Return valid JSON only. No markdown fences.
"""


def parse_args():
    parser = argparse.ArgumentParser(description="Generate recall items using DeepSeek.")
    parser.add_argument("--input-file", required=True, help="Path to the provider input JSON.")
    parser.add_argument("--output-file", required=True, help="Path to the generated item JSON.")
    return parser.parse_args()


def load_input(path):
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def extract_json_object(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
        stripped = stripped.strip()
    return json.loads(stripped)


def sanitize_topic(topic):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", topic).strip("-").lower()


def normalize_items(bundle, items):
    normalized = []
    topic = bundle["topic"]
    topic_display_name = bundle["topic_display_name"]
    source_default = f"provider:deepseek:{topic}"
    topic_slug = sanitize_topic(topic)

    for index, item in enumerate(items, start=1):
        presentation_mode = item["presentation_mode"]
        normalized.append(
            {
                "id": f"{topic_slug}_{index:03d}_{presentation_mode}",
                "topic": topic,
                "topic_display_name": topic_display_name,
                "content_type": item["content_type"],
                "presentation_mode": presentation_mode,
                "prompt": item["prompt"],
                "answer": item.get("answer", ""),
                "source": item.get("source") or source_default,
            }
        )
    return normalized


def call_deepseek(bundle):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment.")

    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    url = os.environ.get("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com/chat/completions")

    user_payload = {
        "topic": bundle["topic"],
        "topic_display_name": bundle["topic_display_name"],
        "mode": bundle["mode"],
        "notes": bundle["notes"],
    }
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API request failed: {exc.code} {detail}") from exc

    content = body["choices"][0]["message"]["content"]
    parsed = extract_json_object(content)
    return normalize_items(bundle, parsed["items"])


def main():
    args = parse_args()
    bundles = load_input(args.input_file)
    generated_items = []
    for bundle in bundles:
        generated_items.extend(call_deepseek(bundle))

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(generated_items, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Wrote {len(generated_items)} items to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
