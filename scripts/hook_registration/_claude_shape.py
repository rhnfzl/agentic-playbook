"""Claude-shaped emitter + reconciler (claude-code, codex, cline, copilot).

These adapters all register hooks in a Claude-compatible settings.json
shape: PascalCase events, nested {hooks: [{type, command}], matcher} entries.

Codex differs only in event resolution: PreToolUse reliably intercepts
only Bash per OpenAI's 2026 docs, so non-Bash matchers auto-promote to
PostToolUse. The auto-promote rule lives in codex_event_for() and is
intentionally distinct from the Claude/Cline/Copilot path which keeps the
authored event verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ._common import resolve_hook_event, resolve_hook_matcher

if TYPE_CHECKING:
    from adapters._protocol import Hook


_CODEX_PRE_TOOL_USE_SUPPORTED = {"Bash"}


def claude_shaped_entry(hook: Hook, command_path: str) -> tuple[str, dict]:
    """Emit a Claude-compatible settings.json entry.

    Used by claude_code, codex, cline, copilot adapters. Each registers a
    settings.json-shaped JSON file with PascalCase events and nested
    {hooks: [{type, command}], matcher} entries.
    """
    event = resolve_hook_event(hook)
    matcher = resolve_hook_matcher(hook)
    entry: dict = {"hooks": [{"type": "command", "command": command_path}]}
    if matcher:
        entry["matcher"] = matcher
    return event, entry


def codex_event_for(hook: Hook) -> str:
    """Resolve the effective Codex event for a hook (per ADR-0034).

    OpenAI Codex's PreToolUse reliably intercepts only Bash tools per the
    2026 docs (developers.openai.com/codex/hooks). Edit/Write/MultiEdit
    fire only PostToolUse; apply_patch + MCP tools are listed but flaky.

    v0.6 auto-promotion: when the PLAYBOOK-HOOK-EVENT is PreToolUse and
    the PLAYBOOK-HOOK-MATCHER excludes Bash, the effective Codex event
    becomes PostToolUse. The hook script body stays unchanged; only the
    JSON registration shifts the event so the script actually fires.

    Rules:
      PreToolUse + Bash in matcher  -> PreToolUse (Bash IS supported)
      PreToolUse + no Bash in match -> PostToolUse (auto-promote)
      PreToolUse + no matcher       -> PreToolUse ('*' matches Bash too)
      <any other event>             -> unchanged
    """
    event = resolve_hook_event(hook)
    if event != "PreToolUse":
        return event
    matcher = resolve_hook_matcher(hook)
    if matcher is None:
        return "PreToolUse"
    tokens = set(matcher.split("|"))
    if _CODEX_PRE_TOOL_USE_SUPPORTED & tokens:
        return "PreToolUse"
    return "PostToolUse"


def codex_shaped_entry(hook: Hook, command_path: str) -> tuple[str, dict]:
    """Emit a Codex hooks.json entry (Claude-compatible JSON shape) with
    PreToolUse->PostToolUse auto-promotion for non-Bash matchers.

    Differs from claude_shaped_entry only in event resolution. The body of
    the registered entry (nested {hooks:[{type,command}], matcher}) stays
    Claude-compatible because Codex accepts the Claude settings.json schema.

    See codex_event_for() for the promotion logic.
    """
    event = codex_event_for(hook)
    matcher = resolve_hook_matcher(hook)
    entry: dict = {"hooks": [{"type": "command", "command": command_path}]}
    if matcher:
        entry["matcher"] = matcher
    return event, entry


def entry_references_command(entry: object, command_path: str) -> bool:
    """True if the settings.json-shaped entry references command_path in its
    nested hooks list. Used by Claude-shaped adapters to de-dupe by command
    path across registration shapes (e.g. v0.4 -> v0.5 matcher upgrade).
    """
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list):
        return False
    return any(
        isinstance(h, dict) and h.get("command") == command_path for h in hooks_list
    )


def strip_claude_command_from_entries(entries: list, command_path: str) -> list:
    """Return a new entries list with command_path surgically removed from each
    Claude-shaped entry's nested hooks list. Entries whose hooks list becomes
    empty are dropped; mixed entries that still reference user-authored
    commands are preserved with only the playbook command gone.

    Used by claude_code, codex, cline, copilot adapters so a user-authored
    hook sharing a matcher with a playbook hook is NOT silently deleted
    during a v0.4 -> v0.5 upgrade (or any subsequent re-install).
    """
    out: list = []
    for entry in entries:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        hooks_list = entry.get("hooks")
        if not isinstance(hooks_list, list):
            out.append(entry)
            continue
        kept = [
            h
            for h in hooks_list
            if not (isinstance(h, dict) and h.get("command") == command_path)
        ]
        if len(kept) == len(hooks_list):
            out.append(entry)
            continue
        if not kept:
            continue
        out.append({**entry, "hooks": kept})
    return out


def reconcile_claude_shaped_hooks_in_json(
    json_path,
    new_hooks: dict[str, set[str]],
    prior_hooks: dict[str, set[str]],
) -> int:
    """Remove playbook-managed hook commands from a Claude-shaped hooks.json
    (codex / cline / copilot project file) that fell out of the new install.

    Per-event semantics: prior - new commands get surgically stripped from
    each entry's nested hooks list. User-authored entries (any command NOT
    in prior_hooks) are preserved. Returns count of removed commands.

    Companion to claude_code's settings.json reconciler in _protocol.py;
    factored here so codex/cline/copilot can share the logic without each
    re-implementing it.
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
        before = sum(
            len(e.get("hooks", []))
            for e in event_entries
            if isinstance(e, dict) and isinstance(e.get("hooks"), list)
        )
        for cmd in to_drop:
            event_entries[:] = strip_claude_command_from_entries(event_entries, cmd)
        after = sum(
            len(e.get("hooks", []))
            for e in event_entries
            if isinstance(e, dict) and isinstance(e.get("hooks"), list)
        )
        removed += before - after
        hook_block[event] = event_entries

    if removed:
        json_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return removed
