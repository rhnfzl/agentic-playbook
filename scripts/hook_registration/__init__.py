"""Shared hook-registration emitters across all adapters with a documented
hook surface (per ADR-0034).

Per the 2026-05-25 cross-agent gap analysis: through v0.4 only Claude Code's
adapter copied + registered playbook hooks. v0.5 brought Codex, Cline,
Copilot, and Cursor (camelCase) into the fold via Claude-shaped and
Cursor-shaped emitters. v0.6 added Codex Bash-only auto-promote and the
full Windsurf Cascade translator (12 snake_case events, tool_info stdin
re-encoded via hooks/_cascade-translate.sh). v0.10 split this module
into per-shape sub-modules so each shape's emit + reconcile logic lives
in one file.

Three emitter shapes:

  claude_shaped_entry(hook, command_path) -> (event_pascal, entry_dict)
    Claude-compatible settings.json entry. Used by claude_code, codex
    (without auto-promote), cline, copilot.

  codex_shaped_entry(hook, command_path) -> (event_pascal, entry_dict)
    Claude-compatible JSON shape but applies the PreToolUse + non-Bash ->
    PostToolUse auto-promote rule. Used by codex (the only adapter whose
    native PreToolUse reliably intercepts only Bash per OpenAI's 2026 docs).

  cursor_shaped_entry(hook, command_path) -> (event_camel, entry_dict)
    Cursor hooks.json entry. Cursor uses camelCase events and a flatter
    shape ({command, matcher, timeout} per entry, no nested hooks list).
    Tool names also differ (Bash -> Shell; edit hooks append StrReplace).
    Used by cursor.

  windsurf_shaped_entry(command_path, translator_path) -> entry_dict
    Cascade hooks.json entry. Each command wraps the core hook through
    _cascade-translate.sh so Cascade's tool_info stdin gets re-encoded
    to Claude-shaped tool_input before invocation. Used by windsurf.
"""

from __future__ import annotations

from ._claude_shape import (
    claude_shaped_entry,
    codex_event_for,
    codex_shaped_entry,
    entry_references_command,
    reconcile_claude_shaped_hooks_in_json,
    strip_claude_command_from_entries,
)
from ._common import (
    is_cursor_only,
    is_hook_for_adapter,
    is_wrapped_core,
    resolve_cursor_wrapper,
    resolve_hook_adapters,
    resolve_hook_event,
    resolve_hook_matcher,
)
from ._cursor_shape import (
    cursor_entry_references_command,
    cursor_event_for,
    cursor_shaped_entry,
    reconcile_cursor_shaped_hooks_in_json,
    resolve_cursor_matcher,
    strip_cursor_command_from_entries,
)
from ._windsurf_shape import (
    reconcile_windsurf_shaped_hooks_in_json,
    resolve_windsurf_event_override,
    resolve_windsurf_events,
    strip_windsurf_command_from_entries,
    windsurf_shaped_entry,
    windsurf_show_output,
)


__all__ = [
    "claude_shaped_entry",
    "codex_event_for",
    "codex_shaped_entry",
    "cursor_entry_references_command",
    "cursor_event_for",
    "cursor_shaped_entry",
    "entry_references_command",
    "is_cursor_only",
    "is_hook_for_adapter",
    "is_wrapped_core",
    "reconcile_claude_shaped_hooks_in_json",
    "reconcile_cursor_shaped_hooks_in_json",
    "reconcile_windsurf_shaped_hooks_in_json",
    "resolve_cursor_matcher",
    "resolve_cursor_wrapper",
    "resolve_hook_adapters",
    "resolve_hook_event",
    "resolve_hook_matcher",
    "resolve_windsurf_event_override",
    "resolve_windsurf_events",
    "strip_claude_command_from_entries",
    "strip_cursor_command_from_entries",
    "strip_windsurf_command_from_entries",
    "windsurf_shaped_entry",
    "windsurf_show_output",
]
