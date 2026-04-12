# temorize

`temorize` is a terminal-native recall prototype. The current MVP is a short CLI session that shows items from selected topics in either `question`, `raw_note`, or `mixed` mode.

## Current Files

- `docs/terminal-recall-mvp-spec.md`: current MVP spec
- `docs/deepseek-provider-mini-spec.md`: next-phase provider spec
- `data/fake_items.json`: fake dataset used for the prototype
- `recall.py`: minimal CLI demo

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

## Current Behavior

- loads fake items from `data/fake_items.json`
- filters by topic and session mode
- tries to avoid consecutive same-topic items in `mixed`
- stores feedback internally as `positive`, `neutral`, or `negative`
- expects `question` items to be self-contained; vague prompts should be repaired or downgraded in the provider layer

## Provider Demo

The next-phase provider path keeps the current CLI shape and only swaps the item source.

1. Prepare a notes input file
2. Generate schema-compatible items with the DeepSeek provider demo
3. Run `recall.py` against the generated JSON

Example:

```bash
python3 provider/deepseek_demo.py \
  --input-file data/sample_provider_notes.json \
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
