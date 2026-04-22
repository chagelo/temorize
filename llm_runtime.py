#!/usr/bin/env python3

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_PROVIDER = "deepseek"
LOCAL_ENV_PATH = Path(__file__).resolve().parent / ".env.local"
_LOCAL_ENV_LOADED = False

PROVIDER_DEFAULTS = {
    "deepseek": {
        "default_model": "deepseek-chat",
        "default_base_url": "https://api.deepseek.com/chat/completions",
        "label": "DeepSeek",
    },
    "openai": {
        "default_model": "gpt-5-mini",
        "default_base_url": "https://api.openai.com/v1/chat/completions",
        "label": "OpenAI",
    },
}


def load_local_env():
    global _LOCAL_ENV_LOADED
    if _LOCAL_ENV_LOADED or not LOCAL_ENV_PATH.exists():
        _LOCAL_ENV_LOADED = True
        return

    for raw_line in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

    _LOCAL_ENV_LOADED = True


def extract_json_object(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
        stripped = stripped.strip()
    return json.loads(stripped)


def get_provider():
    load_local_env()
    return os.environ.get("TEMORIZE_MODEL_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def get_runtime_config():
    provider = get_provider()
    provider_defaults = PROVIDER_DEFAULTS.get(provider)
    if provider_defaults is None:
        raise RuntimeError(f"Unsupported model provider '{provider}'.")

    api_key = os.environ.get("TEMORIZE_API_KEY")
    if not api_key:
        raise RuntimeError("TEMORIZE_API_KEY is not set in the environment.")

    return {
        "provider": provider,
        "label": provider_defaults["label"],
        "api_key": api_key,
        "model": os.environ.get("TEMORIZE_MODEL", provider_defaults["default_model"]),
        "base_url": os.environ.get(
            "TEMORIZE_API_BASE_URL",
            provider_defaults["default_base_url"],
        ),
    }


def ensure_runtime_ready():
    config = get_runtime_config()
    return config["provider"]


def call_json_task(system_prompt, user_payload):
    config = get_runtime_config()
    if config["provider"] == "deepseek":
        return _call_chat_completions_json(config, system_prompt, user_payload)
    if config["provider"] == "openai":
        return _call_chat_completions_json(config, system_prompt, user_payload)
    raise RuntimeError(f"Unsupported model provider '{config['provider']}'.")


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


def _call_chat_completions_json(config, system_prompt, user_payload):
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }

    request = urllib.request.Request(
        config["base_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{config['label']} API request failed: {exc.code} {detail}"
        ) from exc

    content = body["choices"][0]["message"]["content"]
    return extract_json_object(content)
