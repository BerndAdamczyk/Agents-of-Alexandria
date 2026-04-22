#!/usr/bin/env python3
"""NotebookLM persistent memory helper for Claude Code."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click

NOTEBOOK_NAME = os.environ.get("NOTEBOOKLM_NOTEBOOK", "Claude Code Memory")


def _require_client():
    try:
        from notebooklm import NotebookLMClient
        from notebooklm.exceptions import AuthError
        return NotebookLMClient, AuthError
    except ImportError:
        click.echo("Error: notebooklm-py is not installed.", err=True)
        click.echo("Run: pip install 'notebooklm-py[browser]'", err=True)
        sys.exit(1)


async def _get_or_create_notebook(client):
    notebooks = await client.notebooks.list()
    for nb in notebooks:
        if nb.title == NOTEBOOK_NAME:
            return nb
    click.echo(f"Creating notebook '{NOTEBOOK_NAME}'...", err=True)
    return await client.notebooks.create(NOTEBOOK_NAME)


def _run(coro):
    NotebookLMClient, AuthError = _require_client()

    async def _main():
        try:
            async with NotebookLMClient.from_storage() as client:
                return await coro(client)
        except AuthError:
            click.echo("Error: Not authenticated with Google NotebookLM.", err=True)
            click.echo("Run: notebooklm login", err=True)
            sys.exit(1)

    return asyncio.run(_main())


@click.group()
def cli():
    """NotebookLM persistent memory for Claude Code."""
    pass


@cli.command()
@click.argument("text")
def save(text):
    """Save a note to NotebookLM."""

    async def _save(client):
        nb = await _get_or_create_notebook(client)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"Note [{timestamp}]"
        await client.notes.create(nb.id, title=title, content=text)
        click.echo(f"Saved: {title}")

    _run(_save)


@cli.command()
@click.argument("question")
def query(question):
    """Query the NotebookLM notebook for relevant context."""

    async def _query(client):
        nb = await _get_or_create_notebook(client)
        result = await client.chat.ask(nb.id, question)
        click.echo(result.answer)

    _run(_query)


@cli.command()
@click.option("--project", default=None, help="Project directory path for context.")
def load(project):
    """Load relevant context from NotebookLM for the current project."""

    async def _load(client):
        nb = await _get_or_create_notebook(client)
        project_hint = project or os.getcwd()
        project_name = Path(project_hint).name
        question = (
            f"What relevant notes, decisions, or context exist for the project "
            f"'{project_name}' or for recent work? Summarize concisely."
        )
        result = await client.chat.ask(nb.id, question)
        click.echo(f"[NotebookLM Memory — {NOTEBOOK_NAME}]\n")
        click.echo(result.answer)

    _run(_load)


@cli.command()
@click.argument("transcript_path")
def summarize(transcript_path):
    """Extract key points from a session transcript and save to NotebookLM."""
    path = Path(transcript_path)
    if not path.exists():
        click.echo(f"Error: Transcript not found: {transcript_path}", err=True)
        sys.exit(1)

    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    content = entry.get("content", "")
                    if role in ("user", "assistant") and content:
                        if isinstance(content, list):
                            text_parts = [
                                c.get("text", "") for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            ]
                            content = " ".join(text_parts)
                        if content and len(str(content)) > 10:
                            messages.append(f"{role.upper()}: {str(content)[:500]}")
                except (json.JSONDecodeError, AttributeError):
                    continue
    except OSError as e:
        click.echo(f"Error reading transcript: {e}", err=True)
        sys.exit(1)

    if not messages:
        click.echo("No messages found in transcript, skipping summary.", err=True)
        return

    excerpt = "\n".join(messages[-40:])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_name = Path(os.getcwd()).name

    summary_content = (
        f"Session Summary — {project_name} — {timestamp}\n\n"
        f"Recent conversation excerpt:\n\n{excerpt}"
    )

    async def _summarize(client):
        nb = await _get_or_create_notebook(client)
        title = f"Session [{project_name}] {timestamp}"
        await client.sources.add_text(nb.id, title=title, content=summary_content)
        click.echo(f"Session summary saved: {title}")

    _run(_summarize)


if __name__ == "__main__":
    cli()
