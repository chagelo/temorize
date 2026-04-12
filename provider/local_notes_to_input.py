#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert local markdown/text notes into provider input JSON."
    )
    parser.add_argument(
        "--source-file",
        required=True,
        help="Path to a local .md or .txt note file.",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Stable topic id for the extracted notes.",
    )
    parser.add_argument(
        "--topic-display-name",
        required=True,
        help="User-facing topic label.",
    )
    parser.add_argument(
        "--mode",
        choices=["question", "raw_note", "mixed"],
        default="mixed",
        help="Target provider mode for the extracted notes.",
    )
    parser.add_argument(
        "--max-notes",
        type=int,
        default=5,
        help="Maximum number of notes to include in the provider input bundle.",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Path to write the provider input JSON.",
    )
    return parser.parse_args()


def clean_note_text(text):
    stripped = text.strip()
    stripped = CHECKBOX_RE.sub("", stripped)
    stripped = BULLET_RE.sub("", stripped)
    return stripped.strip()


def extract_notes(source_text):
    notes = []
    paragraph_lines = []
    in_code_block = False

    def flush_paragraph():
        if not paragraph_lines:
            return
        note = clean_note_text(" ".join(part.strip() for part in paragraph_lines if part.strip()))
        if note:
            notes.append(note)
        paragraph_lines.clear()

    for raw_line in source_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            flush_paragraph()
            continue

        if in_code_block:
            continue

        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            continue

        if CHECKBOX_RE.match(line) or BULLET_RE.match(line):
            flush_paragraph()
            note = clean_note_text(line)
            if note:
                notes.append(note)
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    return notes


def build_bundle(args, notes):
    if args.max_notes < 1:
        raise RuntimeError("--max-notes must be at least 1.")

    selected_notes = notes[: args.max_notes]
    if not selected_notes:
        raise RuntimeError("No usable notes were extracted from the source file.")

    return [
        {
            "topic": args.topic,
            "topic_display_name": args.topic_display_name,
            "mode": args.mode,
            "notes": selected_notes,
        }
    ]


def main():
    args = parse_args()
    source_path = Path(args.source_file)
    source_text = source_path.read_text(encoding="utf-8")
    notes = extract_notes(source_text)
    bundle = build_bundle(args, notes)

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Extracted {len(bundle[0]['notes'])} notes from {source_path}")
    print(f"Wrote provider input JSON to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
