#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DATA_PATH = Path(__file__).parent / "data" / "fake_items.json"
DEFAULT_FEEDBACK_LOG_PATH = Path.home() / ".temorize" / "sessions.jsonl"


def parse_args():
    parser = argparse.ArgumentParser(description="Run a terminal recall session.")
    parser.add_argument(
        "--topics",
        required=True,
        help="Comma-separated list of active topics, for example rust,english-vocab",
    )
    parser.add_argument(
        "--mode",
        choices=["question", "raw_note", "fact", "mixed"],
        default="mixed",
        help="How items should be presented in this session.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of items to show in this session.",
    )
    parser.add_argument(
        "--items-file",
        default=str(DATA_PATH),
        help="Path to the JSON item file to consume.",
    )
    parser.add_argument(
        "--feedback-log-file",
        default=str(DEFAULT_FEEDBACK_LOG_PATH),
        help="Path to the JSONL file where session feedback is appended.",
    )
    return parser.parse_args()


def load_items(items_file):
    with Path(items_file).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def filter_items(items, topics, mode):
    topic_set = {topic.strip() for topic in topics if topic.strip()}
    filtered = [item for item in items if item["topic"] in topic_set]
    if mode == "mixed":
        return filtered
    return [item for item in filtered if item["presentation_mode"] == mode]


def choose_next_item(remaining, mode, last_topic):
    if not remaining:
        return None

    if mode == "mixed" and last_topic:
        for item in remaining:
            if item["topic"] != last_topic:
                return item
    return remaining[0]


def print_header(index, total, item):
    topic_name = item.get("topic_display_name") or item["topic"]
    print()
    print(f"[{index}/{total}] [{topic_name}] [{item['presentation_mode']}]")
    print(item["prompt"])
    print()


def ask_question_item(item):
    print("j: show  k: remembered  l: fuzzy  ;: forgot  q: quit")
    while True:
        try:
            action = input("> ").strip()
        except EOFError:
            return "quit"
        if action == "q":
            return "quit"
        if action == "j":
            print()
            print(item["answer"])
            print()
            print("k: remembered  l: fuzzy  ;: forgot  q: quit")
            while True:
                try:
                    result = input("> ").strip()
                except EOFError:
                    return "quit"
                if result == "k":
                    return "positive"
                if result == "l":
                    return "neutral"
                if result == ";":
                    return "negative"
                if result == "q":
                    return "quit"
        if action == "k":
            return "positive"
        if action == "l":
            return "neutral"
        if action == ";":
            return "negative"


def ask_raw_note_item():
    print("j: next  k: useful  l: neutral  ;: skip  q: quit")
    while True:
        try:
            action = input("> ").strip()
        except EOFError:
            return "quit"
        if action == "j":
            return "next"
        if action == "k":
            return "positive"
        if action == "l":
            return "neutral"
        if action == ";":
            return "negative"
        if action == "q":
            return "quit"


def print_summary(shown, feedback_counts, topics_seen):
    print()
    print("Session Summary")
    print(f"- total shown: {shown}")
    print(f"- positive: {feedback_counts['positive']}")
    print(f"- neutral: {feedback_counts['neutral']}")
    print(f"- negative: {feedback_counts['negative']}")
    print(f"- topics covered: {', '.join(sorted(topics_seen)) if topics_seen else 'none'}")


def build_feedback_entry(item, result):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "item_id": item["id"],
        "topic": item["topic"],
        "result": result,
    }


def append_feedback_log(log_path, entries):
    if not entries:
        return

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    args = parse_args()
    topics = args.topics.split(",")
    items = filter_items(load_items(args.items_file), topics, args.mode)

    if not items:
        print("No items matched the selected topics and mode.")
        return 1

    remaining = items[:]
    shown = 0
    last_topic = None
    topics_seen = set()
    feedback_counts = {"positive": 0, "neutral": 0, "negative": 0}
    feedback_log_entries = []

    while shown < args.max_items and remaining:
        item = choose_next_item(remaining, args.mode, last_topic)
        remaining.remove(item)

        current_index = shown + 1
        print_header(current_index, args.max_items, item)
        if item["presentation_mode"] == "question":
            result = ask_question_item(item)
        else:
            result = ask_raw_note_item()

        if result == "quit":
            break

        shown += 1
        last_topic = item["topic"]
        topics_seen.add(item["topic"])

        if result == "next":
            continue

        feedback_counts[result] += 1
        feedback_log_entries.append(build_feedback_entry(item, result))

    append_feedback_log(args.feedback_log_file, feedback_log_entries)
    print_summary(shown, feedback_counts, topics_seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
