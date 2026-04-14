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
      "presentation_mode": "question|knowledge",
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
- For mode=knowledge, every item must be knowledge.
- For mode=mixed, you may mix question and knowledge items in one batch.
- Every item must include note_index using the 1-based position of the source note from the input list.
- Produce at most one item per source note.
- Question items must be self-contained and answerable without hidden context.
- Do not use bare deictic phrasing such as "这里", "这段", or "这个" unless the prompt itself also names the concrete code snippet, sentence fragment, or error context.
- If a note cannot support a self-contained question, prefer knowledge instead of a vague question.
- Knowledge items may leave answer empty.
- Knowledge items must be directly readable, reasonably complete, and useful on their own.
- Do not output bare titles, placeholders, or fragment-only prompts such as "似然的定义", "会遇到 403 的问题", or "这里需要改一下".
- Return valid JSON only. No markdown fences.
"""


DEICTIC_PROMPT_RE = re.compile(r"^\s*(为什么)?\s*(这里|这段|这个|这条|这句|该处|上述|上面)")


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


def apply_minimal_fallbacks(bundle, items):
    patched = []
    for item in items:
        copy = dict(item)
        note_index = copy.get("note_index")
        presentation_mode = copy.get("presentation_mode")
        source_note = None

        if isinstance(note_index, int) and 1 <= note_index <= len(bundle["notes"]):
            source_note = bundle["notes"][note_index - 1]

        if (
            presentation_mode == "knowledge"
            and source_note is not None
            and (not isinstance(copy.get("prompt"), str) or not copy.get("prompt", "").strip())
        ):
            copy["prompt"] = source_note

        if presentation_mode == "knowledge" and copy.get("answer") is None:
            copy["answer"] = ""

        if (
            presentation_mode == "question"
            and source_note is not None
            and not question_prompt_is_self_contained(copy.get("prompt", ""))
        ):
            if bundle["mode"] == "question":
                copy["prompt"] = build_question_fallback_prompt(source_note)
            else:
                copy["presentation_mode"] = "knowledge"
                copy["prompt"] = build_knowledge_fallback_prompt(source_note)
                copy["answer"] = ""

        patched.append(copy)
    return patched


def question_prompt_is_self_contained(prompt):
    if not isinstance(prompt, str):
        return False
    text = prompt.strip()
    if not text:
        return False
    if DEICTIC_PROMPT_RE.search(text):
        return False
    if "这里" in text:
        return False
    return True


def build_question_fallback_prompt(source_note):
    return f"根据这条原始笔记，核心结论是什么？\n原始笔记：{source_note}"


def build_knowledge_fallback_prompt(source_note):
    return source_note.strip()


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
    allowed_modes = {"question", "knowledge"}
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
        if bundle["mode"] == "knowledge" and presentation_mode != "knowledge":
            raise RuntimeError(f"Item #{index} must be knowledge mode for this request.")

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
    if not isinstance(parsed, dict):
        raise RuntimeError("Provider output must be a JSON object.")

    if "items" not in parsed:
        raise RuntimeError("Provider output is missing required top-level field 'items'.")

    raw_items = parsed["items"]
    if not isinstance(raw_items, list):
        raise RuntimeError("Provider output field 'items' must be a list.")

    items = validate_item_shape(bundle, {"items": apply_minimal_fallbacks(bundle, raw_items)})
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
