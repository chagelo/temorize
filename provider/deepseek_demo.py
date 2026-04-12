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
      "note_index": 1,
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
- Every item must include note_index using the 1-based position of the source note from the input list.
- Produce at most one item per source note.
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

    for item in items:
        note_index = item["note_index"]
        presentation_mode = item["presentation_mode"]
        normalized.append(
            {
                "id": f"{topic_slug}_{note_index:03d}_{presentation_mode}",
                "topic": topic,
                "topic_display_name": topic_display_name,
                "note_index": note_index,
                "content_type": item["content_type"],
                "presentation_mode": presentation_mode,
                "prompt": item["prompt"],
                "answer": item.get("answer", ""),
                "source": item.get("source") or source_default,
            }
        )
    return normalized


def validate_item_shape(bundle, parsed):
    if not isinstance(parsed, dict):
        raise RuntimeError("Provider output must be a JSON object.")

    items = parsed.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Provider output must contain an 'items' list.")

    max_note_index = len(bundle["notes"])
    allowed_modes = {"question", "raw_note"}
    seen_pairs = set()

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Item #{index} is not a JSON object.")

        for field in ("note_index", "content_type", "presentation_mode", "prompt"):
            if field not in item:
                raise RuntimeError(f"Item #{index} is missing required field '{field}'.")

        note_index = item["note_index"]
        if not isinstance(note_index, int) or note_index < 1 or note_index > max_note_index:
            raise RuntimeError(f"Item #{index} has invalid note_index '{note_index}'.")

        presentation_mode = item["presentation_mode"]
        if presentation_mode not in allowed_modes:
            raise RuntimeError(
                f"Item #{index} has invalid presentation_mode '{presentation_mode}'."
            )

        if bundle["mode"] == "question" and presentation_mode != "question":
            raise RuntimeError(f"Item #{index} must be question mode for this request.")
        if bundle["mode"] == "raw_note" and presentation_mode != "raw_note":
            raise RuntimeError(f"Item #{index} must be raw_note mode for this request.")

        if not isinstance(item["prompt"], str) or not item["prompt"].strip():
            raise RuntimeError(f"Item #{index} has an empty prompt.")

        if presentation_mode == "question":
            answer = item.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError(f"Question item #{index} must include a non-empty answer.")

        pair = (note_index, presentation_mode)
        if pair in seen_pairs:
            raise RuntimeError(
                f"Duplicate output for note_index={note_index} and mode={presentation_mode}."
            )
        seen_pairs.add(pair)

    return items


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
    items = validate_item_shape(bundle, parsed)
    return normalize_items(bundle, items)


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
