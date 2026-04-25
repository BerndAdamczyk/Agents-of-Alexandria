# Agents of Alexandria

Topic-partitioned persistent memory for Claude Code, backed by Google NotebookLM.
Each topic is its own NotebookLM notebook; Claude picks or invents the topic
before every `save` / `query` / `summarize`. One library, many topics.

## Install

```bash
git clone https://github.com/BerndAdamczyk/Agents-of-Alexandria.git ~/src/agents-of-alexandria
cd ~/src/agents-of-alexandria
./install.sh
notebooklm login   # one-time Google auth
```

The installer:

- Copies the helper script, skill, slash command, and hooks into `~/.claude/`.
- Merges `SessionStart` and `Stop` hook entries into `~/.claude/settings.json`.
- Seeds `~/.claude/notebooklm-team.json` (empty by default).
- Installs `notebooklm-py[browser]` and Playwright Chromium on first run.
- Records the installed commit hash so the `SessionStart` hook can auto-update
  at most once per 24 hours.

Re-running `install.sh` is idempotent; the team-config file is never clobbered.

## Usage

Trigger from the Claude Code chat with `/memory <subcommand>`, or let the
installed hooks call the CLI directly.

| Subcommand | Purpose |
|---|---|
| `list-topics` | Show all topic notebooks (1-hour on-disk cache). |
| `save --topic=<t> "<text>"` | Save a note (no source-cap pressure). Add `--as-source` for an indexed source. |
| `query --topic=<t> "<q>"` | Ask one topic. Cross-topic iteration requires `NOTEBOOKLM_CROSS_TOPIC_QUERY=1`. |
| `load [--topic=<t>] [--all-topics]` | Prime context from one topic or the top-5 by last-updated. |
| `summarize <transcript.jsonl>` | Append session summary to `session-log` (override via `--topic`). |
| `share --topic=<t> --email=<addr>` | Invite collaborators to a topic notebook. |
| `merge --topic=<t> [--force]` | Manual archive when a notebook nears the 50-source cap. |

In an interactive shell, omitting `--topic` exits with code `2` and prints
`no topic provided; run 'list-topics' and retry with --topic=<name>`.
Hooks export `CLAUDE_HOOK=1` and fall back silently to
`NOTEBOOKLM_FALLBACK_TOPIC` (default `general`).

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `NOTEBOOKLM_MERGE_AT` | `40` | Source count that triggers an archive merge. |
| `NOTEBOOKLM_TOPIC_PREFIX` | `""` | Optional prefix stored in notebook titles; stripped on output. |
| `NOTEBOOKLM_TOPIC_EXCLUDE` | `""` | Python regex (`re.search` on the stripped title); matching notebooks are hidden from `list-topics`, `load`, and cross-topic query. |
| `NOTEBOOKLM_FALLBACK_TOPIC` | `general` | Hook-context fallback when `--topic` is missing. |
| `NOTEBOOKLM_SESSION_TOPIC` | `session-log` | Target topic for `summarize` without `--topic`. |
| `NOTEBOOKLM_LOAD_ON_START` | unset | Set `1` to run `load --all-topics` at `SessionStart` (heavier; off by default). |
| `NOTEBOOKLM_CROSS_TOPIC_QUERY` | unset | Set `1` to allow `query` without `--topic`. |

`NOTEBOOKLM_NOTEBOOK` is **removed** in v2. If still set, a one-shot stderr
warning fires and the variable is ignored.

## Team sharing

Populate `~/.claude/notebooklm-team.json`:

```json
{
  "emails": ["alice@example.com", "bob@example.com"],
  "role": "editor"
}
```

When a new topic notebook is created, collaborators are auto-invited via the
feature-detected NotebookLM share API. If the SDK does not expose sharing, a
manual URL is printed to stderr so the save still succeeds. An invalid `role`
falls back to `editor` with a one-shot warning.

## Merge mechanic

When a topic's mergeable source count reaches `NOTEBOOKLM_MERGE_AT`, all
originals are concatenated verbatim into one
`Merged Archive <utc-ts> (N sources)` source and the originals are deleted
best-effort. An advisory `fcntl` lock plus a same-UTC-day short-circuit prevent
duplicate archives under concurrency. Existing archive sources are excluded
from future merges to avoid recursive re-archival; unreadable sources are
retained (non-fatal).

## Hooks

Installed into `~/.claude/settings.json`:

- **SessionStart** — auto-update check (max once per 24 h) + `list-topics`
  preflight, so Claude sees the current topic set in its context without an
  extra call.
- **Stop** — appends a session excerpt to the `session-log` topic.

## Non-goals

- No Windows support. The merge lock uses POSIX `fcntl`.
- No automatic migration of the legacy `Claude Code Memory` notebook. On first
  `list-topics`, a one-shot stderr notice surfaces its URL; no content is
  rewritten.

## Deeper docs

- [`.claude/skills/memory/SKILL.md`](.claude/skills/memory/SKILL.md) — full
  skill spec Claude reads at topic-resolution time.
- [`.claude/commands/memory.md`](.claude/commands/memory.md) — slash-command
  contract.
- [`CLAUDE.md`](CLAUDE.md) — brief project note.
