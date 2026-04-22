Manage persistent topic-based memory using Google NotebookLM.

Arguments: $ARGUMENTS

## Workflow for Claude

Before running `save`, `query`, or `summarize` WITHOUT an explicit `--topic=<name>`
from the user, FIRST run `list-topics`. Read the existing topics, pick the best
semantic match, or invent a short kebab-case name (e.g. `auth`, `db-schema`,
`payment-flow`) when none fits. Then invoke the subcommand with `--topic=<name>`.

The script's `--topic` flag is the contract:
- In an interactive shell, omitting it exits with code 2 and prints
  `no topic provided; run 'list-topics' and retry with --topic=<name>`.
- In a hook context, the installed hook scripts already export `CLAUDE_HOOK=1`,
  which enables a silent fallback to `NOTEBOOKLM_FALLBACK_TOPIC` (default `general`)
  or — for `summarize` — `NOTEBOOKLM_SESSION_TOPIC` (default `session-log`).
  Claude should still pass `--topic=` explicitly from the chat.

Parse the first word of the arguments as the subcommand and the remainder as
the argument(s). Extract `--topic=value` or `--topic value` from the remainder
before invocation.

## Subcommands

| Subcommand | Invocation |
|---|---|
| `list-topics` | `python3 ~/.claude/scripts/notebooklm_memory.py list-topics` |
| `save` | `python3 ~/.claude/scripts/notebooklm_memory.py save --topic="<topic>" "<text>"` |
| `save --as-source` | Append `--as-source` to write a full source instead of a note (counts toward the 50-source cap; triggers the merge check). |
| `query` | `python3 ~/.claude/scripts/notebooklm_memory.py query --topic="<topic>" "<question>"` |
| `load` | `python3 ~/.claude/scripts/notebooklm_memory.py load --all-topics --project "$PWD"` |
| `summarize` | Find the current session transcript (most recently modified `.jsonl` in `~/.claude/projects/`), then: `python3 ~/.claude/scripts/notebooklm_memory.py summarize --topic="<topic>" <transcript_path>` |
| `share` | `python3 ~/.claude/scripts/notebooklm_memory.py share --topic="<topic>"` |
| `merge` | `python3 ~/.claude/scripts/notebooklm_memory.py merge --topic="<topic>"` |

## Notes

- Authenticate once with `notebooklm login`.
- `save` without `--as-source` writes a note (cheap, does not count toward the
  50-source cap). With `--as-source`, writes a full source (indexed, does
  count).
- `query` without `--topic` is refused by default. Set
  `NOTEBOOKLM_CROSS_TOPIC_QUERY=1` to iterate all topic notebooks.
- `NOTEBOOKLM_NOTEBOOK` is removed. If still set in the environment, a
  one-time warning fires and the variable is ignored.
- On POSIX only — the merge mechanism uses `fcntl` for advisory locking.
