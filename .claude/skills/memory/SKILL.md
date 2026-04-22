---
name: memory
description: Topic-based collaborative knowledge library backed by Google NotebookLM. Every save, query, and summarize is scoped to a topic (one notebook per topic). ALWAYS resolve or invent a topic via list-topics before saving, querying, or summarizing. TRIGGER when starting work on an unfamiliar project (load context), making an architectural or product decision (save it), completing a significant task (save a summary), or when past decisions are referenced but missing from current context.
---

# NotebookLM Memory Skill (v2, topic-partitioned)

A collaborative, topic-indexed knowledge library that persists across Claude Code
sessions via Google NotebookLM. Every topic is a dedicated notebook; adding to
an existing topic is preferred over inventing a new one.

## Knowledge-library philosophy

One library, many topics. Claude alone is responsible for semantic
classification; the helper script stays deterministic and never guesses, fuzzy-
matches, or tries ML heuristics. Topic resolution happens in the chat layer via
`list-topics` → pick → `--topic=`.

## Topic workflow (non-negotiable)

1. Run `list-topics` first — cheap; results are cached for 1 hour on disk.
2. Choose the existing topic that best matches the material.
3. If none fits, invent a short kebab-case name (2-4 words).
4. Invoke the subcommand with `--topic=<name>`.

The script exits with code `2` when `--topic=` is missing in a TTY shell.
Hooks receive a silent fallback because the installed hook scripts export
`CLAUDE_HOOK=1`.

## When to use each subcommand

- **`list-topics`** — discovery; always run first when Claude does not already
  know which topic to use.
- **`save`** — durable facts, decisions, findings. Defaults to `notes.create`
  (does not count toward the 50-source cap). Pass `--as-source` for indexed
  content; that triggers the merge check.
- **`query`** — retrieval from a single topic. Cross-topic iteration requires
  `NOTEBOOKLM_CROSS_TOPIC_QUERY=1`.
- **`load`** — session priming. `--all-topics` summarises the top 5 topics by
  `last_updated`; gated behind `NOTEBOOKLM_LOAD_ON_START=1`.
- **`summarize`** — end-of-session capture. Defaults to the `session-log`
  topic (override via `--topic` or `NOTEBOOKLM_SESSION_TOPIC`).
- **`share`** — invite collaborators to an existing topic notebook.
- **`merge`** — manual archive when a notebook nears the 50-source cap;
  `--force` bypasses the threshold and the same-day short-circuit.

## Team sharing

Populate `~/.claude/notebooklm-team.json`:

```json
{
  "emails": ["alice@example.com", "bob@example.com"],
  "role": "editor"
}
```

When a new topic notebook is created, collaborators are auto-invited. The
NotebookLM SDK's share API is feature-detected; if unavailable, a manual URL is
printed to stderr so the save still succeeds. Absent or empty config → silent
no-op. Malformed JSON → one-shot stderr warning, then ignored.

## Merge mechanic

When a topic's source count reaches `NOTEBOOKLM_MERGE_AT` (default `40`), all
sources are concatenated verbatim into one `Merged Archive <utc-ts> (N sources)`
source. Originals are deleted when the SDK exposes `sources.delete`; otherwise
they are retained and a loud stderr warning fires once the count remains above
`MERGE_AT + 10`. An advisory `fcntl` file lock and a same-UTC-day archive-title
short-circuit prevent duplicate archives under concurrency.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `NOTEBOOKLM_MERGE_AT` | `40` | Source count that triggers merge. |
| `NOTEBOOKLM_TOPIC_PREFIX` | `""` | Optional prefix stored in notebook titles; stripped on output. |
| `NOTEBOOKLM_FALLBACK_TOPIC` | `"general"` | Topic used in hook context when `--topic` is missing. |
| `NOTEBOOKLM_SESSION_TOPIC` | `"session-log"` | Target topic for `summarize` without `--topic`. |
| `NOTEBOOKLM_LOAD_ON_START` | unset | Set to `1` to enable SessionStart `load --all-topics`. |
| `NOTEBOOKLM_CROSS_TOPIC_QUERY` | unset | Set to `1` to allow `query` without `--topic`. |
| `CLAUDE_HOOK` | unset | Automatically set to `1` by the installed hook scripts. |
| `NOTEBOOKLM_NOTEBOOK` | — | **Removed** in v2. Warn-once to stderr if still set, then ignored. |

## Non-goals

- Automatic migration of the legacy `"Claude Code Memory"` notebook. On first
  `list-topics`, a one-shot stderr notice shows the legacy notebook URL; no
  content is rewritten.
- Windows support. The merge lock uses `fcntl`, which is POSIX-only.
