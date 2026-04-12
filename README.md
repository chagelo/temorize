# temorize

`temorize` is a terminal-native recall prototype. The current MVP is a short CLI session that shows items from selected topics in either `question`, `raw_note`, or `mixed` mode.

## Current Files

- `docs/terminal-recall-mvp-spec.md`: current MVP spec
- `docs/deepseek-provider-mini-spec.md`: next-phase provider spec
- `data/fake_items.json`: fake dataset used for the prototype
- `data/example_local_notes.md`: example local note file for source-adapter testing
- `data/example_vault/`: example markdown vault for directory-adapter testing
- `recall.py`: minimal CLI demo
- `provider/local_notes_to_input.py`: local markdown/text note-source adapter

## Run

From the repo root:

```bash
python3 recall.py --topics rust,english-vocab --mode mixed --max-items 5
```

Other examples:

```bash
python3 recall.py --topics rust --mode question --max-items 3
python3 recall.py --topics english-vocab,english-sentence --mode raw_note --max-items 3
```

## CLI Parameters

- `--topics`: comma-separated topic list
- `--mode`: `question | raw_note | mixed`
- `--max-items`: maximum number of items to show
- `--items-file`: optional JSON file path, defaults to `data/fake_items.json`
- `--feedback-log-file`: optional JSONL path for persisted session feedback, defaults to `~/.temorize/sessions.jsonl`

## Current Behavior

- loads fake items from `data/fake_items.json`
- filters by topic and session mode
- tries to avoid consecutive same-topic items in `mixed`
- stores feedback internally as `positive`, `neutral`, or `negative`
- expects `question` items to be self-contained; vague prompts should be repaired or downgraded in the provider layer
- appends submitted feedback results to a local JSONL log at session end

## Provider Demo

The next-phase provider path keeps the current CLI shape and only swaps the item source.

1. Prepare a notes input file
2. Generate schema-compatible items with the DeepSeek provider demo
3. Run `recall.py` against the generated JSON

Example:

```bash
python3 provider/local_notes_to_input.py \
  --source-file data/example_local_notes.md \
  --topic rust \
  --topic-display-name Rust \
  --mode mixed \
  --output-file data/local_provider_input.json

python3 provider/deepseek_demo.py \
  --input-file data/local_provider_input.json \
  --output-file data/generated_items.json

python3 recall.py \
  --items-file data/generated_items.json \
  --topics rust \
  --mode mixed \
  --max-items 5
```

Secrets:

- keep `DEEPSEEK_API_KEY` only in local environment variables
- use `.env.example` only as a setup reference
- never commit real keys

## Feedback Persistence

Session feedback is now appended to a local JSONL file by default:

```text
~/.temorize/sessions.jsonl
```

Each appended record currently contains:
- `timestamp`
- `item_id`
- `topic`
- `result`

This is intentionally minimal. It does not yet drive replay avoidance, weighting, or scheduling.

## Local Note Source

The local note-source adapter now supports:
- one local `.md` or `.txt` file via `--source-file`
- one local markdown directory / vault via `--source-dir`

`provider/local_notes_to_input.py`:
- reads one local note file or scans one markdown directory
- extracts bullet items and short paragraphs as note candidates
- writes the existing provider input JSON shape
- keeps the rest of the chain unchanged

Single-file example:

```bash
python3 provider/local_notes_to_input.py \
  --source-file /path/to/your/notes.md \
  --topic rust \
  --topic-display-name Rust \
  --mode mixed \
  --max-notes 5 \
  --output-file data/local_provider_input.json
```

Directory / vault example:

```bash
python3 provider/local_notes_to_input.py \
  --source-dir data/example_vault \
  --subdir rust \
  --topic rust \
  --topic-display-name Rust \
  --mode mixed \
  --max-files 10 \
  --max-notes 5 \
  --output-file data/vault_provider_input.json
```

Directory mode defaults:
- recursively scans `.md` files
- skips `.obsidian/`
- does not parse frontmatter, tags, or wiki-links
- uses `--subdir` or `--include-glob` only for scope control

## Keybindings

Question items:

- `j`: show answer
- `k`: remembered
- `l`: fuzzy
- `;`: forgot
- `q`: quit

Raw-note items:

- `j`: next
- `k`: useful
- `l`: neutral
- `;`: skip
- `q`: quit

## Next Steps

- review fake data alignment with the spec
- tighten CLI behavior if implementation issues appear
- replace fake data with content-provider output later
- use `.env.example` as the setup reference for local provider integration
