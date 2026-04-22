Manage persistent memory using Google NotebookLM.

Arguments: $ARGUMENTS

Parse the first word of the arguments as the subcommand and the remainder as the argument to that subcommand. Then execute the appropriate command below and show the output to the user.

## Subcommands

**save <text>**
Run: `python3 ~/.claude/scripts/notebooklm_memory.py save "<text>"`
Use this to store important decisions, findings, or context that should persist across sessions.

**query <question>**
Run: `python3 ~/.claude/scripts/notebooklm_memory.py query "<question>"`
Use this to retrieve relevant past context or decisions from NotebookLM.

**load**
Run: `python3 ~/.claude/scripts/notebooklm_memory.py load --project "$PWD"`
Loads a contextual summary relevant to the current project directory.

**summarize**
Find the current session transcript path (look in ~/.claude/projects/ for the most recently modified .jsonl file matching the current session), then run:
`python3 ~/.claude/scripts/notebooklm_memory.py summarize <transcript_path>`
This saves the key content from the current session into NotebookLM as a source.

## Notes

- The notebook name defaults to "Claude Code Memory". Override with the `NOTEBOOKLM_NOTEBOOK` environment variable.
- If authentication is missing, run `notebooklm login` in the terminal first.
- `save` and `query` use lightweight notes; `summarize` creates a full source for deeper indexing.
