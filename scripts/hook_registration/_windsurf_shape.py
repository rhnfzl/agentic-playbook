"""Windsurf Cascade emitter + reconciler (v0.6).

Cascade has 12 event surfaces compared to Claude's 4; a Claude PostToolUse
hook with matcher `Edit|Write|Bash` registers under BOTH `post_write_code`
and `post_run_command` so it fires for either tool family.

Tool-info stdin format: Cascade emits `tool_info` rather than Claude-shaped
`tool_input`. The translator wrapper (hooks/_cascade-translate.sh) re-encodes
stdin before invoking the core hook. windsurf_shaped_entry() takes the
translator path so adapters can opt in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ._common import resolve_hook_event, resolve_hook_matcher

if TYPE_CHECKING:
    from adapters._protocol import Hook


_HOOK_WINDSURF_EVENT_HEADER_RE = re.compile(
    r"^#\s*PLAYBOOK-HOOK-WINDSURF-EVENT:\s*(\w+)\s*$"
)

# Windsurf Cascade event names (per docs.windsurf.com/windsurf/cascade/hooks +
# Tavily 2026 confirmation). 12 events total.
_WINDSURF_EVENTS = frozenset(
    {
        "pre_read_code",
        "post_read_code",
        "pre_write_code",
        "post_write_code",
        "pre_run_command",
        "post_run_command",
        "pre_mcp_tool_use",
        "post_mcp_tool_use",
        "pre_user_prompt",
        "post_cascade_response",
        "post_cascade_response_with_transcript",
        "post_setup_worktree",
    }
)

# Auto-derive from (Claude event, matcher token) to Cascade event. A hook
# with mixed matcher tokens (Bash|Edit|...) registers once per applicable
# Cascade event so both pre_run_command + pre_write_code fire.
_WINDSURF_EDIT_TOOLS = frozenset(
    {"Edit", "Write", "MultiEdit", "NotebookEdit", "StrReplace"}
)
_WINDSURF_BASH_TOOLS = frozenset({"Bash", "Shell"})


def resolve_windsurf_event_override(hook: Hook) -> str | None:
    """Read PLAYBOOK-HOOK-WINDSURF-EVENT (optional override). Returns None
    if absent; returns the configured event name if present, validated
    against the known Cascade event set. An invalid override returns None
    (falls back to auto-derive).
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_WINDSURF_EVENT_HEADER_RE.match(line.strip())
        if m:
            event = m.group(1).strip()
            return event if event in _WINDSURF_EVENTS else None
    return None


def resolve_windsurf_events(hook: Hook) -> list[str]:
    """Resolve the list of Cascade events for a hook (per ADR-0034).

    Cascade has 12 events spread across read/write/run/mcp/prompt/response
    surfaces; Claude has 4 (PreToolUse, PostToolUse, SessionStart, Stop).
    Auto-derive from PLAYBOOK-HOOK-EVENT + PLAYBOOK-HOOK-MATCHER:

      PreToolUse + Bash-family in matcher  -> pre_run_command
      PreToolUse + Edit-family in matcher  -> pre_write_code
      PostToolUse + Bash-family in matcher -> post_run_command
      PostToolUse + Edit-family in matcher -> post_write_code
      SessionStart                         -> post_setup_worktree
      Stop                                 -> post_cascade_response

    A hook whose Claude matcher spans BOTH Bash and Edit families (e.g.
    code-review-graph-update: 'Edit|Write|MultiEdit|Bash') registers under
    BOTH Cascade events so it fires for either tool family.

    Explicit override via PLAYBOOK-HOOK-WINDSURF-EVENT takes precedence
    over auto-derive; the override returns a single event.

    Returns empty list when the hook has no Cascade equivalent (e.g. an
    event the auto-derive doesn't recognize and no override). Adapter
    skips registration in that case.
    """
    override = resolve_windsurf_event_override(hook)
    if override is not None:
        return [override]

    event = resolve_hook_event(hook)
    matcher = resolve_hook_matcher(hook)

    if event == "SessionStart":
        return ["post_setup_worktree"]
    if event == "Stop":
        return ["post_cascade_response"]
    if event not in ("PreToolUse", "PostToolUse"):
        return []

    if matcher is None:
        # Wildcard matcher: register for the broader run_command event
        # (Bash interception fires on every shell call, the closest
        # analog to a no-matcher Pre/PostToolUse).
        return [
            "pre_run_command" if event == "PreToolUse" else "post_run_command",
        ]

    tokens = set(matcher.split("|"))
    events: list[str] = []
    if tokens & _WINDSURF_BASH_TOOLS:
        events.append(
            "pre_run_command" if event == "PreToolUse" else "post_run_command"
        )
    if tokens & _WINDSURF_EDIT_TOOLS:
        events.append("pre_write_code" if event == "PreToolUse" else "post_write_code")
    return events


def windsurf_show_output(hook) -> bool:
    """Return PLAYBOOK-HOOK-WINDSURF-SHOW-OUTPUT for the hook (default True).

    v0.7 Cascade per-hook visibility knob. Default True so advisory output
    (lint warnings, sonar drift, push-guard messages) surfaces back to the
    model. Silent state-only hooks (autoindex regeneration, embedding
    refresh) set `# PLAYBOOK-HOOK-WINDSURF-SHOW-OUTPUT: false` to keep their
    chatter out of the chat. Recognized false values (case-insensitive):
    false, 0, no.
    """
    body = getattr(hook, "body", "") or ""
    for line in body.splitlines()[:30]:
        stripped = line.lstrip("#").strip()
        if not stripped.startswith("PLAYBOOK-HOOK-WINDSURF-SHOW-OUTPUT:"):
            continue
        value = stripped.split(":", 1)[1].strip().lower()
        return value not in ("false", "0", "no", "off")
    return True


def windsurf_shaped_entry(
    command_path: str,
    *,
    translator_path: str | None = None,
    show_output: bool = True,
) -> dict:
    """Emit a Cascade hooks.json entry (one per event; caller iterates).

    Cascade entry shape (per docs.windsurf.com + Tavily 2026): {command,
    show_output?, working_directory?}. The translator path wraps the core
    hook so Cascade's tool_info stdin gets re-encoded to Claude-shaped
    {tool_input}. When translator_path is None, the command runs the core
    hook directly (used for hooks already authored for Cascade shape).

    show_output=False emits an explicit `"show_output": false` so Cascade
    suppresses the hook's stdout/stderr from the chat. Default True keeps
    the entry shape minimal (no extra key) for backward-compat with hand-
    edited hooks.json.
    """
    cmd = f"{translator_path} {command_path}" if translator_path else command_path
    entry: dict = {"command": cmd}
    if not show_output:
        entry["show_output"] = False
    return entry


def strip_windsurf_command_from_entries(entries: list, command_substring: str) -> list:
    """Cascade variant: entry.command is a string; remove entries whose
    command contains command_substring (matching either the core hook path
    or the wrapper-prefixed string).
    """
    return [
        entry
        for entry in entries
        if not (
            isinstance(entry, dict)
            and isinstance(entry.get("command"), str)
            and command_substring in entry["command"]
        )
    ]


def reconcile_windsurf_shaped_hooks_in_json(
    json_path,
    new_hook_paths: set[str],
    prior_hook_paths: set[str],
) -> int:
    """Remove playbook-managed Cascade entries that fell out of the new
    profile. Cascade entries are keyed by command-string-contains-path
    (not exact match) because the registered command is
    `<translator> <hook-path>` so a substring check on the hook path
    locates both.

    Returns the count of entries removed across all events. User-authored
    entries (entries whose command doesn't reference a managed hook path)
    are preserved.
    """
    json_path = Path(json_path)
    if not json_path.exists() or not prior_hook_paths:
        return 0
    try:
        doc = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    hook_block = doc.get("hooks")
    if not isinstance(hook_block, dict):
        return 0

    to_drop = prior_hook_paths - new_hook_paths
    if not to_drop:
        return 0

    removed = 0
    for event, event_entries in list(hook_block.items()):
        if not isinstance(event_entries, list):
            continue
        before = len(event_entries)
        for hook_path in to_drop:
            event_entries[:] = strip_windsurf_command_from_entries(
                event_entries, hook_path
            )
        removed += before - len(event_entries)
        hook_block[event] = event_entries

    if removed:
        json_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return removed
