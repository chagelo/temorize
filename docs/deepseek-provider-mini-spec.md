# DeepSeek Provider Mini Spec

## Goal

Replace the fake-data-only path with a minimal real-content generation chain:

`raw notes -> DeepSeek -> schema-compatible item JSON -> recall.py`

This phase does not change the terminal session shape, keybindings, or summary model.

## Non-Goals

- No new UI mode
- No menu bar or ambient trigger work
- No advanced ranking or scheduling
- No multi-step note analysis pipeline
- No secret storage in repo

## Inputs

Provider input should stay small and explicit.

```json
{
  "topic": "rust",
  "topic_display_name": "Rust",
  "mode": "question",
  "notes": [
    "String 实现了 Deref，所以可以从 &String 得到 &str。",
    "map(|&x| x) 这里会把 &str 解成 str，str 是 DST。"
  ]
}
```

Fields:
- `topic`: stable internal topic id
- `topic_display_name`: user-facing topic label
- `mode`: target output style, one of `question | knowledge | mixed`
- `notes`: 3 to 5 raw notes for the initial validation pass

For the first real note-source integrations, these fields may be produced by a thin local adapter over:
- one markdown/text note file
- or one local markdown directory / vault

The adapter should only normalize raw notes into this bundle shape; it should not contain recall logic.

Mode notes:
- `mode=question`: output should only contain `presentation_mode=question`
- `mode=knowledge`: output should only contain `presentation_mode=knowledge`
- `mode=mixed`: output may contain `question` and `knowledge` items in the same batch

## Output Contract

The provider must return items that fit the current CLI schema.

```json
[
  {
    "id": "rust_001_knowledge",
    "topic": "rust",
    "topic_display_name": "Rust",
    "note_index": 1,
    "content_type": "concept",
    "presentation_mode": "knowledge",
    "prompt": "str 是 DST，不能像普通定长类型那样直接按值拿出来。",
    "answer": "",
    "source": "provider:deepseek"
  }
]
```

Required fields:
- `id`
- `topic`
- `topic_display_name`
- `note_index`
- `content_type`
- `presentation_mode`
- `prompt`
- `answer`
- `source`

Rules:
- `note_index` must point to the 1-based position of the source note in the provider input list
- `presentation_mode=question` requires both `prompt` and `answer`
- `presentation_mode=knowledge` is for directly resurfacing a readable knowledge point such as a word, phrase, definition, concise rule, or lightly cleaned note-derived statement
- `knowledge` may leave `answer` empty
- `question` prompts must be self-contained and answerable without hidden context
- provider should not emit vague prompts such as bare `这里 / 这段 / 这个`
- output must remain compatible with `recall.py` without changing the current interaction model
- `id` should be generated predictably by the provider layer using:
  - `topic + "_" + note_index + "_" + presentation_mode`
  - example: `rust_001_question`

## V1 Provider Behavior

Keep the first provider implementation narrow:

- If the note is suitable for recall questioning, generate a `question` item
- If the note is suitable for direct resurfacing, generate a `knowledge` item
- For V1, each source note should produce at most one output item
- Do not do ranking, scoring, summarization, or multi-item reasoning
- Do not try to infer spaced-repetition metadata in this phase
- If a generated `question` is still vague after prompting, the provider should:
  - downgrade it to `knowledge` for `mixed` or `knowledge` requests
  - repair it into a self-contained fallback prompt for `question` requests

## Prompting Requirement

The provider prompt should instruct DeepSeek to:

- stay within the supplied topic
- choose either `question` or `knowledge`
- return JSON only
- include `note_index` for every returned item
- preserve factual meaning from the original note
- avoid inventing extra facts not present in the note
- avoid unresolved references like `这里 / 这段 / 这个`
- include a concrete anchor when a question depends on code, a sentence fragment, or an error context
- do not emit bare titles or fragment-only knowledge items

## Secret Handling

- API key must only come from local environment variables
- runtime-facing variable name: `TEMORIZE_API_KEY`
- provider selection variable name: `TEMORIZE_MODEL_PROVIDER`
- repo may contain setup guidance only
- repo must not contain any real key value

## V1 Validation Flow

1. Prepare 3 to 5 real notes for one topic
2. Call DeepSeek through a provider script
3. Save returned items as JSON
4. Run `recall.py` against that JSON shape
5. Check:
   - schema compatibility
   - item quality
   - whether question/knowledge selection feels reasonable
   - invalid model output is rejected before it reaches the session layer

## Immediate Build Target

The next implementation step should be a tiny provider demo that:

- reads local input notes
- reads provider credentials from the runtime environment
- calls DeepSeek once
- writes schema-compatible JSON
- can be used in place of `data/fake_items.json` for a manual test run

The real-source adapters should stay equally small:

- support one local `.md` / `.txt` file or one local markdown directory
- in directory mode, recurse through `.md` files, skip `.obsidian/`, and rely on scope-control flags instead of smart filtering
- extract bullet items and short paragraphs as raw notes
- write a single provider-input bundle
- feed that bundle into the existing DeepSeek demo without changing `recall.py`
