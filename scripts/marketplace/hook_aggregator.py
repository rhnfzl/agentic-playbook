"""Aggregate hooks into hooks/hooks.json per profile."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .content_ops import ResolvedRef
from .types import EmitterConfig, Profile


_HOOK_EVENT_RE = re.compile(r"PLAYBOOK-HOOK-EVENT:\s*(\w+)")
_HOOK_MATCHER_RE = re.compile(r"PLAYBOOK-HOOK-MATCHER:\s*(.+)")


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _build_hooks_json(
    profile: Profile,
    resolved: tuple[ResolvedRef, ...],
    config: EmitterConfig,
    plugin_dir: Path,
) -> int:
    hook_entries = [r for r in resolved if r.spec.kind == "hooks"]
    if not hook_entries:
        out = plugin_dir / "hooks" / "hooks.json"
        if out.exists() and not config.dry_run:
            out.unlink()
        return 0

    hooks_by_event: dict[str, list[dict[str, str]]] = {}
    for entry in hook_entries:
        source = entry.source
        try:
            content = source.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _stderr(
                f"WARN: profile '{profile.name}' hook '{entry.ref}' unreadable at "
                f"{source} ({type(exc).__name__}); drop the ref or restore the file"
            )
            continue
        event_match = _HOOK_EVENT_RE.search(content)
        if not event_match:
            _stderr(
                f"WARN: profile '{profile.name}' hook '{entry.ref}' at {source} has "
                "no PLAYBOOK-HOOK-EVENT header; add the header (PreToolUse / "
                "PostToolUse / SessionStart / Stop) or drop the ref"
            )
            continue
        matcher_match = _HOOK_MATCHER_RE.search(content)
        event = event_match.group(1)
        # Point at the MATERIALIZED filename (entry.plugin_rel.name keeps the
        # .sh suffix), not the bare profile ref. The ref is a stem; the file
        # on disk and in the plugin dir is `<stem>.sh`.
        cmd: dict[str, str] = {
            "type": "command",
            "command": f"${{PLUGIN_ROOT}}/hooks/{entry.plugin_rel.name}",
        }
        if matcher_match:
            cmd["matcher"] = matcher_match.group(1).strip()
        hooks_by_event.setdefault(event, []).append(cmd)

    if not hooks_by_event:
        return 0

    payload = {"hooks": hooks_by_event}
    out = plugin_dir / "hooks" / "hooks.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if config.dry_run:
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return 0
    out.write_text(text, encoding="utf-8")
    return 1
