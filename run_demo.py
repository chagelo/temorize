#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).parent.resolve()
DEFAULT_MAX_FILES = 5
DEFAULT_MAX_NOTES = 8


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the local-note -> provider -> recall demo with one command."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-file", help="Path to one local .md or .txt note file.")
    source_group.add_argument(
        "--source-dir", help="Path to one local markdown directory or vault."
    )
    parser.add_argument(
        "--subdir",
        help="Optional subdirectory under --source-dir to limit the scan scope.",
    )
    parser.add_argument(
        "--include-glob",
        help="Optional glob pattern, relative to --source-dir, for limiting scanned markdown files.",
    )
    parser.add_argument(
        "--topic",
        help="Optional topic label. Defaults to a slug derived from the source path.",
    )
    parser.add_argument(
        "--mode",
        choices=["question", "knowledge", "mixed"],
        default="mixed",
        help="Presentation mode to request from the provider and session.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of items to show in the final recall session.",
    )
    parser.add_argument(
        "--show-generated",
        action="store_true",
        help="Print the generated item JSON before entering the recall session.",
    )
    return parser.parse_args()


def slugify(text):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()


def derive_topic(args):
    if args.topic:
        return slugify(args.topic)

    if args.subdir:
        return slugify(Path(args.subdir).name)

    source = Path(args.source_dir or args.source_file)
    stem = source.stem if source.is_file() else source.name
    return slugify(stem) or "notes"


def topic_display_name(topic):
    return topic.replace("-", " ").replace("_", " ").title()


def run_command(cmd):
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main():
    args = parse_args()

    if "DEEPSEEK_API_KEY" not in os.environ:
        print("DEEPSEEK_API_KEY is not set in the environment.", file=sys.stderr)
        return 1

    topic = derive_topic(args)
    display_name = topic_display_name(topic)

    with tempfile.TemporaryDirectory(prefix="temorize-demo-") as temp_dir:
        temp_root = Path(temp_dir)
        provider_input = temp_root / "provider_input.json"
        generated_items = temp_root / "generated_items.json"

        adapter_cmd = [
            sys.executable,
            str(REPO_ROOT / "provider" / "local_notes_to_input.py"),
            "--topic",
            topic,
            "--topic-display-name",
            display_name,
            "--mode",
            args.mode,
            "--max-notes",
            str(DEFAULT_MAX_NOTES),
            "--output-file",
            str(provider_input),
        ]
        if args.source_file:
            adapter_cmd.extend(["--source-file", args.source_file])
        else:
            adapter_cmd.extend(
                [
                    "--source-dir",
                    args.source_dir,
                    "--max-files",
                    str(DEFAULT_MAX_FILES),
                ]
            )
            if args.subdir:
                adapter_cmd.extend(["--subdir", args.subdir])
            if args.include_glob:
                adapter_cmd.extend(["--include-glob", args.include_glob])

        provider_cmd = [
            sys.executable,
            str(REPO_ROOT / "provider" / "deepseek_demo.py"),
            "--input-file",
            str(provider_input),
            "--output-file",
            str(generated_items),
        ]
        recall_cmd = [
            sys.executable,
            str(REPO_ROOT / "recall.py"),
            "--items-file",
            str(generated_items),
            "--topics",
            topic,
            "--mode",
            args.mode,
            "--max-items",
            str(args.max_items),
        ]

        run_command(adapter_cmd)
        run_command(provider_cmd)

        if args.show_generated:
            print()
            print(generated_items.read_text(encoding="utf-8").rstrip())
            print()

        run_command(recall_cmd)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
