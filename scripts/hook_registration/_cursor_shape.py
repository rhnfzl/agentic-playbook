"""Cursor-shaped emitter + reconciler.

Cursor's hooks.json uses camelCase events and a flat per-entry shape:
{command, matcher, timeout}, not the nested {hooks: [...]} shape Claude
uses. The user-level vs project-level path convention is the caller's
responsibility (this emitter only produces entries; the adapter decides
the write target).

Tool-name remapping (Bash -> Shell) and edit-family expansion
(append StrReplace) are applied in resolve_cursor_matcher so a hook
declaring `# PLAYBOOK-HOOK-MATCHER: Bash|Edit` registers under Cursor as
`Shell|Edit|StrReplace`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ._common import resolve_hook_event, resolve_hook_matcher

if TYPE_CHECKING:
    from adapters._protocol import Hook


_HOOK_CURSOR_MATCHER_HEADER_RE = re.compile(
    r"^#\s*PLAYBOOK-HOOK-CURSOR-MATCHER:\s*(.+?)\s*$"
)


_CLAUDE_TO_CURSOR_EVENT = {
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
    "SessionStart": "sessionStart",
    "Stop": "stop",
}

_CLAUDE_TO_CURSOR_TOOL = {
    "Bash": "Shell",
}


def cursor_event_for(hook: Hook) -> str:
    """Resolve the camelCase Cursor event for a hook (per ADR-0034).

    Pure delegation to the _CLAUDE_TO_CURSOR_EVENT registry; lifted from
    cursor.py's inline dicts so every call site uses one map. PostToolUse
    is the default for unmapped events because Cursor's safest non-blocking
    surface is post-tool.
    """
    return _CLAUDE_TO_CURSOR_EVENT.get(resolve_hook_event(hook), "postToolUse")


def resolve_cursor_matcher(hook: Hook) -> str | None:
    """Resolve a Cursor-flavored matcher for the hook.

    Order of precedence:
      1. Explicit PLAYBOOK-HOOK-CURSOR-MATCHER header (overrides auto-derive)
      2. Auto-derived from PLAYBOOK-HOOK-MATCHER:
           Bash -> Shell
           Edit/Write/MultiEdit family -> append StrReplace to cover the
             Cursor-specific edit primitive
      3. None (no matcher field; Cursor treats as match-all)
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_CURSOR_MATCHER_HEADER_RE.match(line.strip())
        if m:
            value = m.group(1).strip()
            return None if value == "*" else value
    base = resolve_hook_matcher(hook)
    if not base:
        return None
    tokens = [_CLAUDE_TO_CURSOR_TOOL.get(tok, tok) for tok in base.split("|")]
    edit_family = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
    if edit_family.intersection(tokens) and "StrReplace" not in tokens:
        tokens.append("StrReplace")
    return "|".join(tokens)


def cursor_shaped_entry(hook: Hook, command_path: str) -> tuple[str, dict]:
    """Emit a Cursor hooks.json entry (camelCase event + flat shape).

    Cursor's hooks.json uses {command, matcher, timeout} per entry, not the
    nested {hooks: [...]} shape Claude uses. Returns (camelCase event name,
    entry dict).

    Per the cross-agent gap analysis: the user-level vs project-level path
    convention is the caller's responsibility (this emitter only produces
    the entry; the adapter decides what to write into).
    """
    event = cursor_event_for(hook)
    matcher = resolve_cursor_matcher(hook)
    entry: dict = {"command": command_path, "timeout": 30}
    if matcher:
        entry["matcher"] = matcher
    return event, entry


def cursor_entry_references_command(entry: object, command_path: str) -> bool:
    """Cursor-shaped variant: entries are flat {command, matcher, timeout}."""
    return isinstance(entry, dict) and entry.get("command") == command_path


def strip_cursor_command_from_entries(entries: list, command_path: str) -> list:
    """Cursor-shaped variant: entries are flat {command, matcher, timeout}.
    Remove only entries whose command exactly matches command_path; preserve
    all other entries (which may be user-authored hooks under any matcher).
    """
    return [
        entry
        for entry in entries
        if not (isinstance(entry, dict) and entry.get("command") == command_path)
    ]


def reconcile_cursor_shaped_hooks_in_json(
    json_path,
    new_hooks: dict[str, set[str]],
    prior_hooks: dict[str, set[str]],
) -> int:
    """Cursor variant: entries under each camelCase event are flat
    {command, matcher, timeout}. Remove playbook entries whose command is in
    prior - new; preserve user-authored entries entirely.
    """
    json_path = Path(json_path)
    if not json_path.exists() or not prior_hooks:
        return 0
    try:
        doc = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    hook_block = doc.get("hooks")
    if not isinstance(hook_block, dict):
        return 0

    removed = 0
    for event, event_entries in list(hook_block.items()):
        if not isinstance(event_entries, list):
            continue
        prior_for_event = set(prior_hooks.get(event, set()))
        new_for_event = set(new_hooks.get(event, set()))
        to_drop = prior_for_event - new_for_event
        if not to_drop:
            continue
        before = len(event_entries)
        for cmd in to_drop:
            event_entries[:] = strip_cursor_command_from_entries(event_entries, cmd)
        removed += before - len(event_entries)
        hook_block[event] = event_entries

    if removed:
        json_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return removed
