"""Shared header parsing + Hook resolution helpers (per ADR-0034).

Every hook-shape module (_claude_shape, _cursor_shape, _windsurf_shape)
calls into this module to read PLAYBOOK-HOOK-* metadata from a Hook's
body. The regexes, capability sets, and resolver functions live here so
the shape modules can stay focused on emit + reconcile.

Header conventions (full reference -- each is optional unless noted):

  # PLAYBOOK-HOOK-EVENT: <event>            required (v0.4)
  # PLAYBOOK-HOOK-MATCHER: <matcher>        required (v0.5)
  # PLAYBOOK-HOOK-CURSOR-MATCHER: <matcher> overrides Cursor matcher
  # PLAYBOOK-HOOK-CURSOR-WRAPPER: <name>.sh cursor wraps a different file
  # PLAYBOOK-HOOK-CURSOR-ONLY: true         non-cursor skip
  # PLAYBOOK-HOOK-ADAPTERS: <slug>[,<slug>] restrict to listed slugs
  # PLAYBOOK-HOOK-WINDSURF-EVENT: <event>   pin Cascade event
  # PLAYBOOK-HOOK-WINDSURF-SHOW-OUTPUT: false  silence Cascade output
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters._protocol import Hook


_HOOK_EVENT_HEADER_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-EVENT:\s*(\w+)\s*$")
_HOOK_MATCHER_HEADER_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-MATCHER:\s*(.+?)\s*$")
_HOOK_CURSOR_WRAPPER_HEADER_RE = re.compile(
    r"^#\s*PLAYBOOK-HOOK-CURSOR-WRAPPER:\s*(\S+?)\s*$"
)
_HOOK_CURSOR_ONLY_HEADER_RE = re.compile(
    r"^#\s*PLAYBOOK-HOOK-CURSOR-ONLY:\s*(true|false)\s*$",
    re.IGNORECASE,
)
_HOOK_ADAPTERS_HEADER_RE = re.compile(
    r"^#\s*PLAYBOOK-HOOK-ADAPTERS:\s*(.+?)\s*$"
)

_HOOK_CAPABLE_ADAPTERS = frozenset(
    {"claude-code", "codex", "cursor", "cline", "copilot", "windsurf"}
)


def resolve_hook_event(hook: Hook) -> str:
    """Read the PLAYBOOK-HOOK-EVENT header; default to PostToolUse if absent."""
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_EVENT_HEADER_RE.match(line.strip())
        if m:
            return m.group(1)
    return "PostToolUse"


def resolve_hook_matcher(hook: Hook) -> str | None:
    """Read the PLAYBOOK-HOOK-MATCHER header; None if absent or '*'."""
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_MATCHER_HEADER_RE.match(line.strip())
        if m:
            matcher = m.group(1).strip()
            return None if matcher == "*" else matcher
    return None


def resolve_hook_adapters(hook: Hook) -> frozenset[str] | None:
    """Parse PLAYBOOK-HOOK-ADAPTERS header into a set of allowed adapter slugs.

    Returns None when the header is absent: hook applies to every hook-capable
    adapter (subject to CURSOR-ONLY filtering).

    Returns a frozenset of slugs when the header is present. Unknown slugs are
    discarded so a typo cannot silently widen scope. An empty result (e.g.,
    header lists only unknown slugs) returns frozenset() which means "no
    adapter installs this hook" (a deliberately conservative degenerate case).

    Used by bundle-coupled hooks (anchored-fs) that only make sense under a
    specific adapter's hook payload format. See ADR-0037.
    """
    for line in hook.body.splitlines()[:20]:
        m = _HOOK_ADAPTERS_HEADER_RE.match(line.strip())
        if m:
            raw = m.group(1).strip()
            slugs = {tok.strip() for tok in raw.split(",") if tok.strip()}
            return frozenset(slugs & _HOOK_CAPABLE_ADAPTERS)
    return None


def is_hook_for_adapter(hook: Hook, adapter_name: str) -> bool:
    """Return True iff the named adapter is allowed to install this hook.

    Encapsulates the precedence: CURSOR-ONLY takes priority (legacy header,
    cheaper check), then PLAYBOOK-HOOK-ADAPTERS scoping, then default-allow.

    Adapter authors call this in their install() filter and in
    install.py:_hook_command_keys so plan-time and write-time agree.
    """
    if is_cursor_only(hook):
        return adapter_name == "cursor"
    allowed = resolve_hook_adapters(hook)
    if allowed is None:
        return True
    return adapter_name in allowed


def is_cursor_only(hook: Hook) -> bool:
    """Return True when the hook declares PLAYBOOK-HOOK-CURSOR-ONLY: true.

    Cursor-only hooks (e.g., the JSON-stdout advisory wrapper) are skipped by
    every non-Cursor adapter for BOTH copy and registration. They live in the
    canonical hook source tree so the cursor adapter and target materializer
    can pick them up, but they are dead weight under ~/.claude/hooks/ etc.
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_CURSOR_ONLY_HEADER_RE.match(line.strip())
        if m:
            return m.group(1).lower() == "true"
    return False


def resolve_cursor_wrapper(hook: Hook) -> str | None:
    """Resolve the optional PLAYBOOK-HOOK-CURSOR-WRAPPER header.

    When set, the cursor adapter registers the wrapper script (resolved as a
    sibling file in the hooks_dir) instead of the core hook. The wrapper is
    expected to live in the same hook source tree and be loaded as a separate
    Hook entry tagged with PLAYBOOK-HOOK-CURSOR-ONLY: true.

    Returns the wrapper basename (with .sh) or None.
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_CURSOR_WRAPPER_HEADER_RE.match(line.strip())
        if m:
            return m.group(1)
    return None


def is_wrapped_core(hook: Hook) -> bool:
    """True when the hook has a PLAYBOOK-HOOK-CURSOR-WRAPPER and is itself
    NOT a cursor-only wrapper. The cursor adapter copies the core script
    but DOES NOT register it; the wrapper script (CURSOR-ONLY: true)
    registers in cursor's hooks.json instead.

    Centralized so install.py's lockfile bookkeeping, cursor.py's
    pre-reconcile pass, and the target materializer all agree on which
    hooks count as cursor-registerable. Per ADR-0034.
    """
    return resolve_cursor_wrapper(hook) is not None and not is_cursor_only(hook)
