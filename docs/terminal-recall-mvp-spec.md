# Terminal Recall MVP Spec

## Product Definition

Terminal Recall is a terminal-native recall session tool. The user opens a dedicated terminal window, runs a CLI command, and reviews a short sequence of items drawn from selected topics. Each item is surfaced either as a question or as a direct knowledge point.

## V1 Scope

Included:
- Dedicated terminal session started explicitly by the user
- Topic selection via CLI
- Session modes: `question`, `knowledge`, `mixed`
- Limited session size via `max_items`
- One item shown at a time
- Lightweight keyboard feedback
- Fake data support before real API integration

Excluded:
- Ambient triggers
- Shell hooks
- Menu bar UI
- Side panes or overlays
- Complex ranking or scheduling
- Full note management or editing
- Rich TUI animation

## Goals

- Let the user complete a light recall session in 3 to 5 minutes
- Support multiple active topics in one session
- Support quiz-like recall and direct knowledge-point resurfacing
- Be simple enough to prototype with fake data first

## Core CLI

```bash
recall --topics rust,english-vocab --mode mixed --max-items 5
```

Parameters:
- `topics`: comma-separated topic list
- `mode`: `question | knowledge | mixed`
- `max-items`: maximum number of items in the session

Deferred:
- `preset`
- `session_profile`
- `frequency`

## Item Schema

```json
{
  "id": "rust_001",
  "topic": "rust",
  "topic_display_name": "Rust",
  "content_type": "concept",
  "presentation_mode": "question",
  "prompt": "为什么 str 不能像普通定长类型那样直接按值拿出来？",
  "answer": "因为这样会试图按值拿出 str，而 str 是 DST，编译期大小未知。",
  "source": "Rust note: str / &str / String"
}
```

Field notes:
- `topic`: stable internal topic id
- `topic_display_name`: optional user-facing topic label
- `content_type`: what the item fundamentally is, such as `concept`, `vocab`, `sentence`, `raw_fragment`
- `presentation_mode`: how the item should be surfaced by default, such as `question` or `knowledge`
- `prompt`: either a question or the knowledge-point text
- `answer`: empty for knowledge items
- `source`: lightweight origin reference

## Selection Rules

V1 keeps selection intentionally simple:
- Only select items from the requested `topics`
- `mode=question` only selects items with `presentation_mode=question`
- `mode=knowledge` only selects items with `presentation_mode=knowledge`
- `mode=mixed` may return any supported presentation mode
- In `mixed`, try to avoid consecutive items from the same topic
- No advanced weighting or spaced repetition in V1

## Session Flow

1. User starts the CLI with `topics`, `mode`, and `max-items`
2. Session loads candidate items from fake data or provider output
3. System selects the next item according to the simple V1 rules
4. Terminal renders:
   - position like `[1/5]`
   - `topic_display_name` or `topic`
   - current `presentation_mode`
   - `prompt`
5. User gives lightweight feedback
6. Session continues until `max-items` is reached or user quits
7. Session ends with a small summary

## Interaction Model

Underlying stored feedback is unified across modes:
- `positive`
- `neutral`
- `negative`

### Question Mode

Initial screen:
- `j`: show answer
- `k`: remembered
- `l`: fuzzy
- `;`: forgot
- `q`: quit

After showing answer:
- `k`: remembered
- `l`: fuzzy
- `;`: forgot
- `q`: quit

### Knowledge Mode

- `j`: next
- `k`: useful
- `l`: neutral
- `;`: skip
- `q`: quit

## Summary Output

At the end of the session, show only:
- total shown
- positive
- neutral
- negative
- topics covered

## Example Items

```json
{
  "id": "rust_001",
  "topic": "rust",
  "topic_display_name": "Rust",
  "content_type": "concept",
  "presentation_mode": "question",
  "prompt": "为什么 str 不能像普通定长类型那样直接按值拿出来？",
  "answer": "因为这样会试图按值拿出 str，而 str 是 DST，编译期大小未知。",
  "source": "Rust note: str / &str / String"
}
```

```json
{
  "id": "eng_vocab_001",
  "topic": "english-vocab",
  "topic_display_name": "English Vocab",
  "content_type": "vocab",
  "presentation_mode": "knowledge",
  "prompt": "tap into = 利用、发掘、借助（资源 / 潜力 / 人才）",
  "answer": "",
  "source": "English vocab note"
}
```

```json
{
  "id": "eng_vocab_002",
  "topic": "english-vocab",
  "topic_display_name": "English Vocab",
  "content_type": "raw_fragment",
  "presentation_mode": "knowledge",
  "prompt": "walk out on someone = 抛弃某人 / 离开某人（感情里）",
  "answer": "",
  "source": "English vocab note"
}
```

```json
{
  "id": "pron_001",
  "topic": "english-pronunciation",
  "topic_display_name": "English Pronunciation",
  "content_type": "pronunciation",
  "presentation_mode": "knowledge",
  "prompt": "of -> əv",
  "answer": "",
  "source": "Pronunciation note"
}
```

```json
{
  "id": "sent_001",
  "topic": "english-sentence",
  "topic_display_name": "English Sentence",
  "content_type": "sentence",
  "presentation_mode": "knowledge",
  "prompt": "do you know how long it's been since i've grabbed a spoon.",
  "answer": "",
  "source": "Sentence note"
}
```

## Example Session

```text
$ recall --topics rust,english-vocab,english-pronunciation --mode mixed --max-items 5

[1/5] [Rust] [question]
为什么 str 不能像普通定长类型那样直接按值拿出来？

j: show  k: remembered  l: fuzzy  ;: forgot  q: quit

> j
因为这样会试图按值拿出 str，而 str 是 DST，编译期大小未知。

k: remembered  l: fuzzy  ;: forgot  q: quit

> k

[2/5] [English Vocab] [knowledge]
walk out on someone = 抛弃某人 / 离开某人（感情里）

j: next  k: useful  l: neutral  ;: skip  q: quit
```

## Immediate Build Plan

1. Hand-author 10 fake items from existing Rust and English notes
2. Implement a tiny CLI demo using the fake dataset
3. Run 2 to 3 real sessions
4. Adjust schema and keybindings only if the session experience exposes problems
5. Integrate the real content-provider API afterward
