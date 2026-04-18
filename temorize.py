#!/usr/bin/env python3

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import llm_runtime
from provider import deepseek_demo, local_notes_to_input
from storage import (
    DEFAULT_DB_PATH,
    add_feedback_event,
    build_topic_labels,
    connect,
    delete_item,
    find_topic_by_slug,
    list_topics,
    load_active_items,
    lower_priority,
    mark_seen,
    slugify_topic,
    upsert_topic,
    upsert_items,
    upsert_source,
)


def parse_args():
    parser = argparse.ArgumentParser(description="temorize local storage workflow.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="Path to the local SQLite database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Ingest one file or directory into local storage.")
    source_group = add_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-file", help="Path to one local .md or .txt note file.")
    source_group.add_argument("--source-dir", help="Path to one local markdown directory or vault.")
    add_parser.add_argument("--subdir", help="Optional subdirectory under --source-dir.")
    add_parser.add_argument("--include-glob", help="Optional glob pattern under --source-dir.")
    add_parser.add_argument("--topic", help="Optional stable topic id for the extracted notes.")
    add_parser.add_argument("--topic-display-name", help="Optional user-facing topic label.")
    add_parser.add_argument(
        "--mode",
        choices=["question", "knowledge", "mixed"],
        default="mixed",
        help="Target generation mode for the extracted notes.",
    )
    add_parser.add_argument("--max-notes", type=int, default=8, help="Maximum number of notes to extract.")
    add_parser.add_argument("--max-files", type=int, default=20, help="Maximum number of markdown files to scan in directory mode.")

    run_parser = subparsers.add_parser("run", help="Run a recall session from local storage.")
    run_parser.add_argument("--topics", help="Optional comma-separated topic filter.")
    run_parser.add_argument(
        "--mode",
        choices=["question", "knowledge", "mixed"],
        default="mixed",
        help="Presentation mode to run.",
    )
    run_parser.add_argument("--max-items", type=int, default=5, help="Maximum number of items to show.")

    preview_parser = subparsers.add_parser(
        "preview",
        help="Run the local-note -> provider -> recall preview without storing items locally.",
    )
    preview_source_group = preview_parser.add_mutually_exclusive_group(required=True)
    preview_source_group.add_argument("--source-file", help="Path to one local .md or .txt note file.")
    preview_source_group.add_argument("--source-dir", help="Path to one local markdown directory or vault.")
    preview_parser.add_argument("--subdir", help="Optional subdirectory under --source-dir.")
    preview_parser.add_argument("--include-glob", help="Optional glob pattern under --source-dir.")
    preview_parser.add_argument("--topic", help="Optional stable topic id for the extracted notes.")
    preview_parser.add_argument("--topic-display-name", help="Optional user-facing topic label.")
    preview_parser.add_argument(
        "--mode",
        choices=["question", "knowledge", "mixed"],
        default="mixed",
        help="Target generation mode for the extracted notes and preview session.",
    )
    preview_parser.add_argument("--max-items", type=int, default=5, help="Maximum number of items to show.")
    preview_parser.add_argument("--max-notes", type=int, default=8, help="Maximum number of notes to extract.")
    preview_parser.add_argument("--max-files", type=int, default=5, help="Maximum number of markdown files to scan in directory mode.")
    preview_parser.add_argument(
        "--show-generated",
        action="store_true",
        help="Print the generated item JSON before entering the preview session.",
    )

    return parser.parse_args()


def slugify(text):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()


def derive_topic(args):
    if args.topic:
        return slugify(args.topic)
    if args.subdir:
        return slugify(Path(args.subdir).name) or "notes"
    source = Path(args.source_dir or args.source_file)
    stem = source.stem if source.is_file() else source.name
    return slugify(stem) or "notes"


def derive_topic_display_name(args, topic):
    if args.topic_display_name:
        return args.topic_display_name
    return topic.replace("-", " ").replace("_", " ").title()


def build_provider_bundle(args):
    args.derived_topic = derive_topic(args)
    args.derived_topic_display_name = derive_topic_display_name(args, args.derived_topic)
    args.topic = args.derived_topic
    args.topic_display_name = args.derived_topic_display_name
    input_paths = local_notes_to_input.iter_markdown_files(args)
    notes = local_notes_to_input.load_notes_from_paths(input_paths)
    bundle = local_notes_to_input.build_bundle(args, notes)
    return input_paths, bundle


def generate_preview_items(args):
    input_paths, bundles = build_provider_bundle(args)
    generated_items = []
    for bundle in bundles:
        generated_items.extend(deepseek_demo.call_deepseek(bundle))
    return input_paths, generated_items


def run_command(cmd):
    subprocess.run(cmd, check=True)


def build_topic_assignments(conn, args, generated_items):
    if args.user_provided_topic:
        primary_topic_id = upsert_topic(
            conn,
            args.derived_topic_display_name or args.derived_topic,
            status="active",
        )
        assignments = {}
        for item in generated_items:
            assignments[item["id"]] = {
                "primary_topic_id": primary_topic_id,
                "secondary_topic_id": None,
            }
        return assignments

    existing_topics = list_topics(conn, statuses=("active", "candidate"))
    suggested = deepseek_demo.suggest_topics_for_items(existing_topics, generated_items)
    assignments = {}
    for item_id, suggestion in suggested.items():
        primary_topic_id = resolve_topic_suggestion(
            conn,
            suggestion["primary_topic"],
            parent_id=None,
        )
        secondary_topic_id = None
        if suggestion["secondary_topic"]:
            secondary_topic_id = resolve_topic_suggestion(
                conn,
                suggestion["secondary_topic"],
                parent_id=primary_topic_id,
            )
        assignments[item_id] = {
            "primary_topic_id": primary_topic_id,
            "secondary_topic_id": secondary_topic_id,
        }
    return assignments


def resolve_topic_suggestion(conn, suggested_name, parent_id=None):
    slug = slugify_topic(suggested_name)
    existing = find_topic_by_slug(conn, slug, parent_id=parent_id, statuses=("active", "candidate"))
    if existing:
        return existing["id"]

    return upsert_topic(conn, suggested_name, parent_id=parent_id, status="candidate")


def ingest_source(conn, args):
    args.user_provided_topic = bool(args.topic)
    input_paths, generated_items = generate_preview_items(args)

    if not generated_items:
        raise RuntimeError("Provider did not generate any items.")

    source_type = "file" if args.source_file else "dir"
    source_path = args.source_file or args.source_dir
    source_id = upsert_source(
        conn,
        source_type=source_type,
        source_path=str(source_path),
        topic=args.topic,
        topic_display_name=args.topic_display_name,
    )
    item_topic_assignments = build_topic_assignments(conn, args, generated_items)
    upsert_items(conn, source_id, generated_items, item_topic_assignments=item_topic_assignments)

    print(f"Ingested {len(generated_items)} items from {len(input_paths)} file(s) into {args.db_path}")
    return 0


def choose_next_item(remaining, mode, last_topic):
    if not remaining:
        return None
    if mode == "mixed" and last_topic:
        for item in remaining:
            if item["topic"] != last_topic:
                return item
    return remaining[0]


def print_header(index, total, item):
    print()
    print(f"[{index}/{total}] [{item['topic_display_name']}] [{item['item_type']}]")
    print(item["content"])
    print()


def ask_question_item(item):
    print("j: show answer  n: remembered  f: forgot  l: lower priority  d: delete forever  q: quit")
    while True:
        try:
            action = input("> ").strip()
        except EOFError:
            return "quit"
        if action == "q":
            return "quit"
        if action == "l":
            return "lower_priority"
        if action == "d":
            return "delete"
        if action == "j":
            print()
            print(item["answer"])
            print()
            print("n: remembered  f: forgot  l: lower priority  d: delete forever  q: quit")
            while True:
                try:
                    result = input("> ").strip()
                except EOFError:
                    return "quit"
                if result == "n":
                    return "positive"
                if result == "f":
                    return "negative"
                if result == "l":
                    return "lower_priority"
                if result == "d":
                    return "delete"
                if result == "q":
                    return "quit"
        if action == "n":
            return "positive"
        if action == "f":
            return "negative"


def ask_knowledge_item():
    print("n: next  f: skip  l: lower priority  d: delete forever  q: quit")
    while True:
        try:
            action = input("> ").strip()
        except EOFError:
            return "quit"
        if action == "n":
            return "next"
        if action == "f":
            return "negative"
        if action == "l":
            return "lower_priority"
        if action == "d":
            return "delete"
        if action == "q":
            return "quit"


def print_summary(shown, feedback_counts, topics_seen, lowered_count, deleted_count):
    print()
    print("Session Summary")
    print(f"- total shown: {shown}")
    print(f"- positive: {feedback_counts['positive']}")
    print(f"- negative: {feedback_counts['negative']}")
    print(f"- lowered: {lowered_count}")
    print(f"- deleted: {deleted_count}")
    print(f"- topics covered: {', '.join(sorted(topics_seen)) if topics_seen else 'none'}")


def run_session(conn, args):
    items = load_active_items(conn, topics=args.topics, mode=args.mode, limit=args.max_items)
    if not items:
        print("No active items matched the selected topics and mode.")
        return 1

    random.shuffle(items)
    remaining = items[:]
    shown = 0
    lowered_count = 0
    deleted_count = 0
    feedback_counts = {"positive": 0, "negative": 0}
    last_topic = None
    topics_seen = set()

    while shown < args.max_items and remaining:
        item = choose_next_item(remaining, args.mode, last_topic)
        remaining.remove(item)
        mark_seen(conn, item["id"])

        current_index = shown + 1
        print_header(current_index, args.max_items, item)

        if item["item_type"] == "question":
            result = ask_question_item(item)
        else:
            result = ask_knowledge_item()

        if result == "quit":
            break

        shown += 1
        last_topic = item["topic"]
        topics_seen.add(item["topic"])

        if result == "next":
            continue
        if result == "lower_priority":
            lower_priority(conn, item["id"])
            lowered_count += 1
            continue
        if result == "delete":
            delete_item(conn, item["id"])
            deleted_count += 1
            continue

        feedback_counts[result] += 1
        add_feedback_event(conn, item["id"], result)

    print_summary(shown, feedback_counts, topics_seen, lowered_count, deleted_count)
    return 0


def preview_session(args):
    try:
        llm_runtime.ensure_runtime_ready()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    input_paths, generated_items = generate_preview_items(args)
    if not generated_items:
        raise RuntimeError("Provider did not generate any items.")

    with tempfile.TemporaryDirectory(prefix="temorize-preview-") as temp_dir:
        temp_root = Path(temp_dir)
        generated_items_path = temp_root / "generated_items.json"
        generated_items_path.write_text(
            json.dumps(generated_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if args.show_generated:
            print()
            print(generated_items_path.read_text(encoding="utf-8").rstrip())
            print()

        recall_cmd = [
            sys.executable,
            str(Path(__file__).parent / "recall.py"),
            "--items-file",
            str(generated_items_path),
            "--topics",
            args.derived_topic,
            "--mode",
            args.mode,
            "--max-items",
            str(args.max_items),
        ]
        run_command(recall_cmd)

    print()
    print(f"Previewed {min(args.max_items, len(generated_items))} item(s) from {len(input_paths)} file(s).")
    return 0


def main():
    args = parse_args()
    if args.command == "preview":
        args.derived_topic = derive_topic(args)
        args.derived_topic_display_name = derive_topic_display_name(args, args.derived_topic)
        args.topic = args.derived_topic
        args.topic_display_name = args.derived_topic_display_name
        return preview_session(args)

    conn = connect(args.db_path)
    try:
        if args.command == "add":
            return ingest_source(conn, args)
        if args.command == "run":
            return run_session(conn, args)
        raise RuntimeError(f"Unsupported command: {args.command}")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
