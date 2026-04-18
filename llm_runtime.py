#!/usr/bin/env python3

import json
import os
import re
import urllib.error
import urllib.request


DEFAULT_PROVIDER = "deepseek"


def extract_json_object(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
        stripped = stripped.strip()
    return json.loads(stripped)


def get_provider():
    return os.environ.get("TEMORIZE_MODEL_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def ensure_runtime_ready():
    provider = get_provider()
    if provider == "deepseek":
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment.")
        return provider
    raise RuntimeError(f"Unsupported model provider '{provider}'.")


def call_json_task(system_prompt, user_payload):
    provider = ensure_runtime_ready()
    if provider == "deepseek":
        return _call_deepseek_json(system_prompt, user_payload)
    raise RuntimeError(f"Unsupported model provider '{provider}'.")


def generate_recall_items(bundle, system_prompt):
    user_payload = {
        "topic": bundle["topic"],
        "topic_display_name": bundle["topic_display_name"],
        "mode": bundle["mode"],
        "notes": bundle["notes"],
    }
    return call_json_task(system_prompt, user_payload)


def suggest_topics(existing_topics, items, system_prompt):
    user_payload = {
        "existing_topics": existing_topics,
        "items": [
            {
                "item_id": item["id"],
                "item_type": item["presentation_mode"],
                "prompt": item["prompt"],
                "answer": item.get("answer", ""),
            }
            for item in items
        ],
    }
    return call_json_task(system_prompt, user_payload)


def _call_deepseek_json(system_prompt, user_payload):
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    url = os.environ.get("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com/chat/completions")
    api_key = os.environ["DEEPSEEK_API_KEY"]

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
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
    return extract_json_object(content)
