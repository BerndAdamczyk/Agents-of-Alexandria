#!/usr/bin/env python3
"""NotebookLM topic-partitioned persistent memory helper for Claude Code."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

# --- User-specified constants (verbatim) ---
DEFAULT_FALLBACK_TOPIC = os.environ.get("NOTEBOOKLM_FALLBACK_TOPIC", "general")
MERGE_AT = int(os.environ.get("NOTEBOOKLM_MERGE_AT", "40"))
TOPIC_PREFIX = os.environ.get("NOTEBOOKLM_TOPIC_PREFIX", "")
SESSION_TOPIC = os.environ.get("NOTEBOOKLM_SESSION_TOPIC", "session-log")
TEAM_CONFIG_PATH = Path.home() / ".claude" / "notebooklm-team.json"

# --- v2 internal constants ---
NOTEBOOKLM_MEMORY_SKILL_VERSION = "2"
TOPIC_CACHE_PATH = Path.home() / ".claude" / "scripts" / ".notebooklm-topic-cache"
TOPIC_CACHE_TTL_SEC = 3600
MERGE_LOCK_PATH = Path.home() / ".claude" / ".notebooklm-merge.lock"
LEGACY_NOTICE_FLAG = Path.home() / ".claude" / "scripts" / ".notebooklm-legacy-notice-shown"
ENV_WARNED_FLAG = Path.home() / ".claude" / "scripts" / ".notebooklm-env-warned"
TEAM_WARNED_FLAG = Path.home() / ".claude" / "scripts" / ".notebooklm-team-warned"

LEGACY_NOTEBOOK_TITLE = "Claude Code Memory"
IS_HOOK = os.environ.get("CLAUDE_HOOK") == "1"


def _touch(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError:
        pass


def _warn_once_env() -> None:
    """Warn once if the removed NOTEBOOKLM_NOTEBOOK env var is still set."""
    if not os.environ.get("NOTEBOOKLM_NOTEBOOK"):
        return
    if ENV_WARNED_FLAG.exists():
        return
    click.echo(
        "[warn] NOTEBOOKLM_NOTEBOOK is removed in skill v2; ignoring. "
        "Content in the old notebook is not migrated.",
        err=True,
    )
    _touch(ENV_WARNED_FLAG)


_warn_once_env()


def _require_client():
    try:
        from notebooklm import NotebookLMClient
        from notebooklm.exceptions import AuthError
        return NotebookLMClient, AuthError
    except ImportError:
        click.echo("Error: notebooklm-py is not installed.", err=True)
        click.echo("Run: pip install 'notebooklm-py[browser]'", err=True)
        sys.exit(1)


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


# --- user-named helpers ---

def _load_team_config() -> dict:
    """Return {"emails": [...], "role": "editor"|"viewer"} or {}.
    Absent / empty / malformed → {} (warns once for malformed JSON)."""
    if not TEAM_CONFIG_PATH.exists():
        return {}
    try:
        with open(TEAM_CONFIG_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        emails = data.get("emails") or []
        role = data.get("role", "editor")
        if not isinstance(emails, list):
            emails = []
        return {"emails": [str(e) for e in emails if e], "role": str(role)}
    except (OSError, ValueError, json.JSONDecodeError):
        if not TEAM_WARNED_FLAG.exists():
            click.echo(
                f"[team-config] {TEAM_CONFIG_PATH} is malformed; ignoring.",
                err=True,
            )
            _touch(TEAM_WARNED_FLAG)
        return {}


def _topic_title(topic: str) -> str:
    """Normalize a topic name: strip, lowercase, whitespace→-, apply prefix.
    Raises click.ClickException on empty/whitespace-only input."""
    if topic is None:
        raise click.ClickException("topic is required")
    normalized = "-".join(topic.strip().lower().split())
    if not normalized:
        raise click.ClickException("topic is empty after normalization")
    return f"{TOPIC_PREFIX}{normalized}"


def _strip_prefix(title: str) -> str:
    if TOPIC_PREFIX and title.startswith(TOPIC_PREFIX):
        return title[len(TOPIC_PREFIX):]
    return title


async def _list_notebooks(client):
    """Return list of notebooks. Last-updated sort fallback order:
    nb.last_updated → nb.updated_at → list-order."""
    try:
        notebooks_api = getattr(client, "notebooks", None)
        if notebooks_api is None or not hasattr(notebooks_api, "list"):
            return []
        result = await notebooks_api.list()
        return list(result) if result else []
    except (AttributeError, NotImplementedError, TypeError):
        return []


def _nb_sort_key(nb):
    return (
        getattr(nb, "last_updated", None)
        or getattr(nb, "updated_at", None)
        or ""
    )


async def _get_or_create_topic_notebook(client, topic: str):
    """Look up a topic notebook by normalized title; create if missing.
    On create, invoke _share_notebook_with_team.
    Returns (notebook, created_bool). Lex-smallest id wins on duplicate."""
    title = _topic_title(topic)

    legacy = os.environ.get("NOTEBOOKLM_NOTEBOOK")
    if legacy:
        try:
            if _topic_title(legacy) == title:
                click.echo(
                    f"[legacy] NOTEBOOKLM_NOTEBOOK='{legacy}' collides with topic "
                    f"'{topic}'. Unset NOTEBOOKLM_NOTEBOOK or choose a different topic.",
                    err=True,
                )
                sys.exit(2)
        except click.ClickException:
            pass

    notebooks = await _list_notebooks(client)
    matches = [nb for nb in notebooks if getattr(nb, "title", "") == title]
    if matches:
        matches.sort(key=lambda nb: str(getattr(nb, "id", "")))
        return matches[0], False

    click.echo(f"Creating notebook '{title}'...", err=True)
    nb = await client.notebooks.create(title)

    # Race check: re-list, prefer lex-smallest id if duplicates appeared.
    notebooks_after = await _list_notebooks(client)
    duplicates = [n for n in notebooks_after if getattr(n, "title", "") == title]
    if len(duplicates) > 1:
        duplicates.sort(key=lambda n: str(getattr(n, "id", "")))
        click.echo(
            f"[race] duplicate notebook for topic '{topic}'; keeping oldest id.",
            err=True,
        )
        nb = duplicates[0]

    await _share_notebook_with_team(client, getattr(nb, "id", None))
    return nb, True


async def _list_sources(client, nb_id):
    """Feature-detected source listing. Returns None when API unavailable."""
    try:
        sources_api = getattr(client, "sources", None)
        if sources_api is None or not hasattr(sources_api, "list"):
            return None
        result = await sources_api.list(nb_id)
        return list(result) if result else []
    except (AttributeError, NotImplementedError, TypeError):
        return None


async def _get_source_text(client, src):
    """Duck-typed retrieval: .content, .text, or client.sources.get().
    Returns None when unavailable. Never swallows AuthError."""
    for attr in ("content", "text"):
        val = getattr(src, attr, None)
        if val:
            return val
    sources_api = getattr(client, "sources", None)
    if sources_api is None or not hasattr(sources_api, "get"):
        return None
    try:
        src_id = getattr(src, "id", None)
        if src_id is None:
            return None
        full = await sources_api.get(src_id)
        for attr in ("content", "text"):
            val = getattr(full, attr, None)
            if val:
                return val
    except (AttributeError, NotImplementedError, TypeError):
        return None
    return None


async def _notebook_url(client, nb_id) -> str:
    """Best-effort notebook URL; constructed fallback uses the public pattern."""
    try:
        notebooks_api = getattr(client, "notebooks", None)
        if notebooks_api is not None and hasattr(notebooks_api, "get"):
            nb = await notebooks_api.get(nb_id)
            for attr in ("url", "share_url"):
                val = getattr(nb, attr, None)
                if val:
                    return val
    except (AttributeError, NotImplementedError, TypeError):
        pass
    return f"https://notebooklm.google.com/notebook/{nb_id}"


async def _share_notebook_with_team(client, nb_id, emails=None, role=None) -> None:
    """Feature-detect sharing API; on total failure, print manual URL.
    Never blocks the caller, never raises."""
    if nb_id is None:
        return
    cfg = _load_team_config()
    if emails is None:
        emails = list(cfg.get("emails") or [])
    if role is None:
        role = cfg.get("role", "editor") or "editor"
    if not emails:
        return

    candidates = []
    notebooks_api = getattr(client, "notebooks", None)
    sharing_api = getattr(client, "sharing", None)
    if notebooks_api is not None and hasattr(notebooks_api, "share"):
        candidates.append(("notebooks.share", notebooks_api.share))
    if sharing_api is not None and hasattr(sharing_api, "invite"):
        candidates.append(("sharing.invite", sharing_api.invite))
    if notebooks_api is not None and hasattr(notebooks_api, "add_collaborator"):
        candidates.append(("notebooks.add_collaborator", notebooks_api.add_collaborator))

    for name, fn in candidates:
        for role_try in (str(role).lower(), str(role).upper()):
            try:
                await fn(nb_id, emails=emails, role=role_try)
                click.echo(f"Shared with {', '.join(emails)}", err=True)
                click.echo(f"[share] using role={role_try} via {name}", err=True)
                return
            except (ValueError, TypeError):
                continue  # wrong case; try the other
            except (AttributeError, NotImplementedError):
                break  # this variant not available; try next candidate
            except Exception as e:
                click.echo(f"[share] {name} failed: {e}", err=True)
                break

    # All attempts exhausted — print manual fallback.
    url = await _notebook_url(client, nb_id)
    click.echo(
        f"[share unavailable] manually share {url} with: {', '.join(emails)}",
        err=True,
    )


async def _merge_sources_if_needed(client, nb_id, force: bool = False) -> None:
    """Archive and (best-effort) delete sources when count >= MERGE_AT.
    Advisory fcntl lock, same-UTC-day short-circuit, stalled-merge warning."""
    sources = await _list_sources(client, nb_id)
    if sources is None:
        click.echo(
            "[merge] skipped: sources.list API unavailable in this SDK.",
            err=True,
        )
        return
    if not force and len(sources) < MERGE_AT:
        return

    try:
        MERGE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        lockfh = open(MERGE_LOCK_PATH, "a+")
    except OSError as e:
        click.echo(f"[merge] cannot open lock {MERGE_LOCK_PATH}: {e}", err=True)
        return

    try:
        try:
            fcntl.flock(lockfh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # another process is merging; skip silently

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not force:
            for src in sources:
                t = getattr(src, "title", "") or ""
                if t.startswith(f"Merged Archive {today}"):
                    return  # same-day short-circuit

        parts = []
        for src in sources:
            text = await _get_source_text(client, src)
            if text is None:
                click.echo(
                    f"[merge] aborted: source "
                    f"'{getattr(src, 'title', '<unknown>')}' unreadable.",
                    err=True,
                )
                return
            stitle = getattr(src, "title", "") or "<untitled>"
            sdate = (
                getattr(src, "created_at", None)
                or getattr(src, "last_updated", None)
                or ""
            )
            parts.append(f"=== Source: {stitle} | {sdate} ===\n{text}")

        merged = "\n\n".join(parts)
        utc_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        archive_title = f"Merged Archive {utc_ts} ({len(sources)} sources)"
        try:
            await client.sources.add_text(nb_id, title=archive_title, content=merged)
        except (AttributeError, NotImplementedError, TypeError) as e:
            click.echo(f"[merge] cannot write archive: {e}", err=True)
            return

        delete_api = getattr(getattr(client, "sources", None), "delete", None)
        if delete_api is None:
            click.echo(
                "[merge] archive created but delete API unavailable; "
                "originals retained.",
                err=True,
            )
        else:
            for src in sources:
                try:
                    await delete_api(getattr(src, "id", None))
                except (AttributeError, NotImplementedError, TypeError):
                    pass

        after = await _list_sources(client, nb_id)
        if after is not None and len(after) >= MERGE_AT + 10:
            click.echo(
                f"[merge-stalled] originals undeletable; archive exists; "
                f"source count={len(after)}",
                err=True,
            )
    finally:
        try:
            fcntl.flock(lockfh, fcntl.LOCK_UN)
        except OSError:
            pass
        lockfh.close()


def _resolve_topic(explicit, fallback_hint=None) -> str:
    """Return the raw topic string (without prefix).
    explicit non-empty    → stripped topic.
    empty + CLAUDE_HOOK=1 → fallback_hint or DEFAULT_FALLBACK_TOPIC.
    empty + TTY           → stderr + exit 2. No fuzzy matching."""
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    if IS_HOOK:
        fb = (fallback_hint or DEFAULT_FALLBACK_TOPIC).strip()
        return fb or DEFAULT_FALLBACK_TOPIC
    click.echo(
        "no topic provided; run 'list-topics' and retry with --topic=<name>",
        err=True,
    )
    sys.exit(2)


# --- legacy one-shot notice ---

async def _maybe_emit_legacy_notice(client) -> None:
    """First-run notice when the legacy single notebook (by title or
    NOTEBOOKLM_NOTEBOOK env) is still present. Flag-gated."""
    if LEGACY_NOTICE_FLAG.exists():
        return
    legacy_env = os.environ.get("NOTEBOOKLM_NOTEBOOK")
    notebooks = await _list_notebooks(client)
    legacy_nb = None
    for nb in notebooks:
        t = getattr(nb, "title", "")
        if t == LEGACY_NOTEBOOK_TITLE or (legacy_env and t == legacy_env):
            legacy_nb = nb
            break
    if not (legacy_env or legacy_nb):
        return
    url = (
        await _notebook_url(client, getattr(legacy_nb, "id", ""))
        if legacy_nb
        else "https://notebooklm.google.com/"
    )
    click.echo(
        f"[legacy-notice] Old memory notebook detected at {url}. "
        f"Content not migrated; use the URL to access legacy material.",
        err=True,
    )
    _touch(LEGACY_NOTICE_FLAG)


# --- topic cache (1-hour TTL for list-topics / load --all-topics) ---

def _read_topic_cache():
    if not TOPIC_CACHE_PATH.exists():
        return None
    try:
        mtime = TOPIC_CACHE_PATH.stat().st_mtime
        if (datetime.now().timestamp() - mtime) > TOPIC_CACHE_TTL_SEC:
            return None
        with open(TOPIC_CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_topic_cache(entries) -> None:
    try:
        TOPIC_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOPIC_CACHE_PATH, "w") as f:
            json.dump(entries, f)
    except OSError:
        pass


# --- CLI ---

@click.group()
def cli():
    """Topic-partitioned NotebookLM memory for Claude Code."""
    pass


@cli.command(name="save")
@click.option("--topic", default=None, help="Topic name (required in TTY).")
@click.option("--as-source", "as_source", is_flag=True, default=False,
              help="Write as a source (counts toward 50-source cap).")
@click.argument("text")
def save_cmd(topic, as_source, text):
    """Save a note (default) or source to the topic notebook."""
    resolved = _resolve_topic(topic)

    async def _save(client):
        nb, _created = await _get_or_create_topic_notebook(client, resolved)
        nb_id = getattr(nb, "id", None)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"[{resolved}] Note [{timestamp}]"
        if as_source:
            await _merge_sources_if_needed(client, nb_id)
            await client.sources.add_text(nb_id, title=title, content=text)
            click.echo(f"Saved source: {title}")
        else:
            await client.notes.create(nb_id, title=title, content=text)
            click.echo(f"Saved note: {title}")

    _run(_save)


@cli.command(name="query")
@click.option("--topic", default=None, help="Topic to query.")
@click.argument("question")
def query_cmd(topic, question):
    """Query a topic notebook (cross-topic requires opt-in)."""
    if not topic or not str(topic).strip():
        if os.environ.get("NOTEBOOKLM_CROSS_TOPIC_QUERY") != "1":
            click.echo(
                "cross-topic query refused; pass --topic=<name> or set "
                "NOTEBOOKLM_CROSS_TOPIC_QUERY=1",
                err=True,
            )
            sys.exit(2)

        async def _query_all(client):
            nbs = await _list_notebooks(client)
            for nb in nbs:
                nb_title = getattr(nb, "title", "") or ""
                if not nb_title or nb_title == LEGACY_NOTEBOOK_TITLE:
                    continue
                if TOPIC_PREFIX and not nb_title.startswith(TOPIC_PREFIX):
                    continue
                label = _strip_prefix(nb_title)
                try:
                    result = await client.chat.ask(nb.id, question)
                    click.echo(f"--- {label} ---")
                    click.echo(getattr(result, "answer", str(result)))
                except Exception as e:
                    click.echo(f"--- {label} (error: {e}) ---", err=True)

        _run(_query_all)
        return

    resolved = _resolve_topic(topic)

    async def _query_one(client):
        nb, _created = await _get_or_create_topic_notebook(client, resolved)
        result = await client.chat.ask(nb.id, question)
        click.echo(getattr(result, "answer", str(result)))

    _run(_query_one)


@cli.command(name="load")
@click.option("--topic", default=None, help="Single topic to load.")
@click.option("--project", default=None, help="Project directory hint.")
@click.option("--all-topics", "all_topics", is_flag=True, default=False,
              help="Summarize top-5 topics by last_updated.")
def load_cmd(topic, project, all_topics):
    """Load project-relevant context from NotebookLM."""
    project_hint = project or os.getcwd()
    project_name = Path(project_hint).name

    if all_topics:
        async def _load_all(client):
            notebooks = await _list_notebooks(client)
            topic_nbs = []
            for nb in notebooks:
                t = getattr(nb, "title", "") or ""
                if not t or t == LEGACY_NOTEBOOK_TITLE:
                    continue
                if TOPIC_PREFIX and not t.startswith(TOPIC_PREFIX):
                    continue
                topic_nbs.append(nb)
            topic_nbs.sort(key=_nb_sort_key, reverse=True)
            top = topic_nbs[:5]
            _write_topic_cache([
                {
                    "title": _strip_prefix(getattr(nb, "title", "")),
                    "id": str(getattr(nb, "id", "")),
                    "last_updated": str(_nb_sort_key(nb)),
                }
                for nb in top
            ])
            click.echo(
                f"[NotebookLM Memory — top {len(top)} topics, project={project_name}]"
            )
            for nb in top:
                label = _strip_prefix(getattr(nb, "title", ""))
                try:
                    result = await client.chat.ask(
                        nb.id,
                        f"Summarize recent notes in 2 sentences for project "
                        f"'{project_name}'.",
                    )
                    click.echo(f"\n--- {label} ---")
                    click.echo(getattr(result, "answer", str(result)))
                except Exception as e:
                    click.echo(f"\n--- {label} (error: {e}) ---", err=True)

        _run(_load_all)
        return

    if topic:
        resolved = _resolve_topic(topic)

        async def _load_one(client):
            nb, _created = await _get_or_create_topic_notebook(client, resolved)
            question = (
                f"What relevant notes, decisions, or context exist for "
                f"project '{project_name}'? Summarize concisely."
            )
            result = await client.chat.ask(nb.id, question)
            click.echo(f"[NotebookLM Memory — {resolved}]")
            click.echo(getattr(result, "answer", str(result)))

        _run(_load_one)
        return

    async def _load_default(client):
        notebooks = await _list_notebooks(client)
        titles = sorted({
            _strip_prefix(getattr(nb, "title", ""))
            for nb in notebooks
            if getattr(nb, "title", "")
            and getattr(nb, "title", "") != LEGACY_NOTEBOOK_TITLE
            and (not TOPIC_PREFIX or getattr(nb, "title", "").startswith(TOPIC_PREFIX))
        })
        click.echo(
            f"[NotebookLM Memory — {len(titles)} topics for project={project_name}]"
        )
        for t in titles:
            click.echo(f"  - {t}")

    _run(_load_default)


@cli.command(name="summarize")
@click.option("--topic", default=None, help="Override destination topic.")
@click.argument("transcript_path")
def summarize_cmd(topic, transcript_path):
    """Append a session summary to the session-log topic."""
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

    excerpt_body = "\n".join(messages[-40:]).strip()
    if not messages or not excerpt_body:
        click.echo("No messages found in transcript, skipping summary.", err=True)
        return

    topic_resolved = (topic or SESSION_TOPIC).strip() or "session-log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_name = Path(os.getcwd()).name
    title = f"Session [{project_name}] {timestamp}"
    summary_content = (
        f"Session Summary — {project_name} — {timestamp}\n\n"
        f"Recent conversation excerpt:\n\n{excerpt_body}"
    )

    async def _summarize(client):
        nb, _created = await _get_or_create_topic_notebook(client, topic_resolved)
        nb_id = getattr(nb, "id", None)
        await _merge_sources_if_needed(client, nb_id)
        await client.sources.add_text(nb_id, title=title, content=summary_content)
        click.echo(f"Session summary saved: {title}")

    _run(_summarize)


@cli.command(name="list-topics")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Emit JSON.")
def list_topics_cmd(as_json):
    """List all topic notebooks (TOPIC_PREFIX stripped). Cached 1h."""
    cached = _read_topic_cache()
    if cached is not None:
        if as_json:
            click.echo(json.dumps({"topics": cached}))
        else:
            for e in cached:
                if isinstance(e, dict) and e.get("title"):
                    click.echo(e["title"])
        return

    async def _list(client):
        await _maybe_emit_legacy_notice(client)
        notebooks = await _list_notebooks(client)
        entries = []
        for nb in notebooks:
            t = getattr(nb, "title", "") or ""
            if not t or t == LEGACY_NOTEBOOK_TITLE:
                continue
            if TOPIC_PREFIX and not t.startswith(TOPIC_PREFIX):
                continue
            entries.append({
                "title": _strip_prefix(t),
                "id": str(getattr(nb, "id", "")),
                "source_count": None,
            })
        entries.sort(key=lambda e: e["title"])
        _write_topic_cache(entries)
        if as_json:
            click.echo(json.dumps({"topics": entries}))
        else:
            for e in entries:
                click.echo(e["title"])

    _run(_list)


@cli.command(name="share")
@click.option("--topic", required=True, help="Topic to share.")
@click.option("--email", "emails", multiple=True,
              help="Collaborator email (repeatable).")
@click.option("--role", default=None, type=click.Choice(["editor", "viewer"]))
def share_cmd(topic, emails, role):
    """Share a topic notebook with collaborators."""
    resolved = _resolve_topic(topic)

    async def _share(client):
        nb, _created = await _get_or_create_topic_notebook(client, resolved)
        nb_id = getattr(nb, "id", None)
        emails_list = list(emails) if emails else None
        await _share_notebook_with_team(
            client, nb_id, emails=emails_list, role=role
        )

    _run(_share)


@cli.command(name="merge")
@click.option("--topic", required=True, help="Topic to merge.")
@click.option("--force", is_flag=True, default=False,
              help="Bypass MERGE_AT threshold and same-day short-circuit.")
def merge_cmd(topic, force):
    """Manually merge sources into a dated archive."""
    resolved = _resolve_topic(topic)

    async def _merge(client):
        nb, _created = await _get_or_create_topic_notebook(client, resolved)
        nb_id = getattr(nb, "id", None)
        await _merge_sources_if_needed(client, nb_id, force=force)
        click.echo(f"Merge attempted for topic '{resolved}'.")

    _run(_merge)


if __name__ == "__main__":
    cli()
