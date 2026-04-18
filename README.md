# temorize

`temorize` is a terminal-native recall prototype for turning local notes into short recall sessions.

The repo currently supports two main workflows through `temorize.py`:
- `preview`: quick end-to-end demo from local notes to a temporary session
- `add` / `run`: SQLite-backed ingest and run workflow for local persistence

## Main Workflows

### 1. Preview

Use this when you want to try the pipeline without storing items locally.

Single file:

```bash
python3 temorize.py preview \
  --source-file data/example_local_notes.md \
  --mode mixed
```

Directory / vault:

```bash
python3 temorize.py preview \
  --source-dir data/example_vault \
  --subdir rust \
  --mode mixed \
  --show-generated
```

What it does:
- reads local notes
- generates `question` / `knowledge` items with the provider
- starts a short recall session

### 2. SQLite Workflow

Use this when you want to ingest notes once, keep items locally, and run later from storage.

Ingest one file:

```bash
python3 temorize.py add \
  --source-file data/example_local_notes.md \
  --mode mixed
```

Ingest one directory:

```bash
python3 temorize.py add \
  --source-dir data/example_vault \
  --subdir rust \
  --mode mixed
```

Run from local storage:

```bash
python3 temorize.py run \
  --mode mixed \
  --max-items 5
```

Default local database:

```text
~/.temorize/temorize.db
```

## Topic Assignment

There are two ingest paths:

1. Manual topic assignment

```bash
python3 temorize.py add \
  --source-file data/example_local_notes.md \
  --topic rust \
  --topic-display-name Rust \
  --mode mixed
```

2. Model-assisted topic assignment

If you omit `--topic`, the system:
- loads the existing topic list from SQLite
- asks the model to suggest topic assignments
- reuses existing topics when slugs already match
- creates new suggestions as `candidate` topics instead of directly promoting them to formal active topics

Current topic shape is intentionally small:
- controlled topic table in SQLite
- up to two levels: primary and secondary
- candidate topics for unconfirmed new suggestions

## Session Modes

Supported modes:
- `question`
- `knowledge`
- `mixed`

`question` items are expected to be self-contained and answerable.

`knowledge` items are direct resurfaced knowledge points that should be readable on their own.

## Keybindings

### `temorize.py run`

Question items:
- `j`: show answer
- `n`: remembered
- `f`: forgot
- `l`: lower priority
- `d`: delete forever
- `q`: quit

Knowledge items:
- `n`: next
- `f`: skip
- `l`: lower priority
- `d`: delete forever
- `q`: quit

### `recall.py`

The lower-level prototype CLI keeps the lighter key set without storage actions:

Question items:
- `j`: show answer
- `n`: remembered
- `f`: forgot
- `q`: quit

Knowledge items:
- `n`: next
- `f`: skip
- `q`: quit

## Local Sources

The local note adapter supports:
- one local `.md` or `.txt` file via `--source-file`
- one local markdown directory / vault via `--source-dir`

Directory mode defaults:
- recursively scans `.md`
- skips `.obsidian/`
- does not parse frontmatter, tags, or wiki-links
- uses `--subdir` or `--include-glob` only for scope control

If you want one specific file, use `--source-file`. `--subdir` is for directories, not files.

## Feedback and Storage

Two persistence layers exist now:

1. Session feedback log

`recall.py` appends minimal feedback records to:

```text
~/.temorize/sessions.jsonl
```

Each record currently contains:
- `timestamp`
- `item_id`
- `topic`
- `result`

2. SQLite item storage

`temorize.py` stores:
- sources
- items
- feedback events
- controlled topics

This is the current foundation for later features such as replay avoidance, topic cleanup, and lightweight priority control.

## Provider and Secrets

The provider currently uses DeepSeek.

Required environment variable:

```bash
export DEEPSEEK_API_KEY="your_key"
```

Optional environment variables:
- `TEMORIZE_MODEL_PROVIDER` (`deepseek` for now)
- `DEEPSEEK_MODEL`
- `DEEPSEEK_API_BASE_URL`

Never commit real keys into the repo.

## Lower-Level Dev Chain

The lower-level scripts are still available when you want to inspect each stage directly:
- `provider/local_notes_to_input.py`
- `provider/deepseek_demo.py`
- `recall.py`

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

## Important Files

- `temorize.py`: SQLite-backed ingest/run workflow
- `llm_runtime.py`: thin model runtime abstraction, currently backed by DeepSeek
- `storage.py`: local SQLite schema and storage helpers
- `run_demo.py`: compatibility wrapper that forwards to `temorize.py preview`
- `recall.py`: lower-level prototype CLI
- `provider/local_notes_to_input.py`: local note adapter
- `provider/deepseek_demo.py`: provider + validation + topic suggestion logic
- `docs/terminal-recall-mvp-spec.md`: earlier MVP spec
- `docs/deepseek-provider-mini-spec.md`: provider-oriented spec
