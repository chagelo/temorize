#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+")
SKIP_DIR_NAMES = {".obsidian"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert local markdown/text notes into provider input JSON."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source-file",
        help="Path to a local .md or .txt note file.",
    )
    source_group.add_argument(
        "--source-dir",
        help="Path to a local markdown vault or directory.",
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
        "--max-files",
        type=int,
        default=20,
        help="Maximum number of markdown files to scan when using --source-dir.",
    )
    parser.add_argument(
        "--subdir",
        help="Optional subdirectory under --source-dir to limit scanning scope.",
    )
    parser.add_argument(
        "--include-glob",
        help="Optional glob pattern, relative to --source-dir, for limiting scanned markdown files.",
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


def iter_markdown_files(args):
    if args.source_file:
        source_path = Path(args.source_file)
        if not source_path.is_file():
            raise RuntimeError(f"Source file does not exist: {source_path}")
        if source_path.suffix.lower() not in {".md", ".txt"}:
            raise RuntimeError("Source file must end with .md or .txt.")
        return [source_path]

    if args.max_files < 1:
        raise RuntimeError("--max-files must be at least 1.")

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise RuntimeError(f"Source directory does not exist: {source_dir}")

    scan_root = source_dir
    if args.subdir:
        scan_root = source_dir / args.subdir
        if not scan_root.is_dir():
            raise RuntimeError(f"Subdirectory does not exist under source dir: {scan_root}")

    if args.include_glob:
        candidates = scan_root.glob(args.include_glob)
    else:
        candidates = scan_root.rglob("*.md")

    files = []
    for path in candidates:
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() != ".md":
            continue
        files.append(path)

    files = sorted(files)
    return files[: args.max_files]


def load_notes_from_paths(paths):
    notes = []
    for path in paths:
        source_text = path.read_text(encoding="utf-8")
        notes.extend(extract_notes(source_text))
    return notes


def build_bundle(args, notes):
    if args.max_notes < 1:
        raise RuntimeError("--max-notes must be at least 1.")

    selected_notes = notes[: args.max_notes]
    if not selected_notes:
        raise RuntimeError("No usable notes were extracted from the selected source.")

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
    input_paths = iter_markdown_files(args)
    notes = load_notes_from_paths(input_paths)
    bundle = build_bundle(args, notes)

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    source_label = args.source_file or args.source_dir
    print(f"Scanned {len(input_paths)} file(s) from {source_label}")
    print(f"Extracted {len(bundle[0]['notes'])} notes into the provider bundle")
    print(f"Wrote provider input JSON to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
