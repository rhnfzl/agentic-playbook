"""Shared parsers + adapter shape registry for native hook-config files.

ADR-0036 layer-3 verification needs three pieces of adapter-specific
knowledge:

  1. Which native config files does each adapter actually write?
  2. How do we extract `{event: [command, ...]}` from each shape (Claude
     nested, Cursor flat, Windsurf flat)?
  3. How do we compare a lockfile-recorded path against a native config
     command string (absolute, `bash <rel>` prefixed, or `<translator>
     <core>` Cascade-wrapped)?

Both `scripts/install_verify.py` (production verification) and the
lifecycle test suite (`tests/lifecycle/test_lifecycle.py`) consume this
module so there is one source of truth for the shape contract. Without
the consolidation, the verify code path and the test asserts had two
copies of the same JSON walking logic that drifted on the first review
pass.

Per ADR-0034 the canonical adapter shape lives in
`scripts/hook_registration.py`; this module is the verification-side
companion, not a replacement.
"""

from __future__ import annotations

import json
from pathlib import Path


# Native config writes per adapter. v0.7 fix: Cursor and Windsurf write
# BOTH user-level AND project-level config when target is set; checking
# only user-level lets a stale or deleted project-level file pass verify
# even though that workspace can't fire any playbook hook.


def config_paths_for(adapter_name: str, target: Path | None) -> list[Path]:
    """Return every native hook-config path the adapter actually writes."""
    home = Path.home()
    paths: list[Path] = []
    if adapter_name == "claude-code":
        paths.append(home / ".claude" / "settings.json")
    elif adapter_name == "codex":
        paths.append(home / ".codex" / "hooks.json")
    elif adapter_name == "cline":
        paths.append(home / ".cline" / "hooks.json")
    elif adapter_name == "cursor":
        paths.append(home / ".cursor" / "hooks.json")
        if target is not None and target.resolve() != home.resolve():
            paths.append(target / ".cursor" / "hooks.json")
    elif adapter_name == "copilot":
        scope = target if target is not None else home
        paths.append(scope / ".github" / "hooks.json")
    elif adapter_name == "windsurf":
        # WindsurfAdapter.install only writes user-level Cascade hooks
        # when ~/.codeium exists (so non-Windsurf machines don't get
        # polluted). Mirror that gate here; otherwise doctor-verify
        # TARGET=... reports every Cascade hook missing for users who
        # installed the Windsurf app but never opened it.
        if (home / ".codeium").is_dir():
            paths.append(home / ".codeium" / "windsurf" / "hooks.json")
        if target is not None:
            paths.append(target / ".windsurf" / "hooks.json")
    return paths


# Cursor + Windsurf use a flat shape ({event: [{command, ...}]}); Claude /
# Codex / Cline / Copilot use the nested Claude shape
# ({event: [{matcher, hooks: [{command, ...}]}]}).
_FLAT_HOOK_ADAPTERS = {"cursor", "windsurf"}

# Map lockfile event names (always Claude-shape PascalCase) to the native
# config event names per adapter. Cursor uses camelCase in its hooks.json;
# every other adapter mirrors Claude's PascalCase. Without this normalization
# every Cursor entry in the lockfile looks "missing" because PreToolUse !=
# preToolUse in a dict lookup.
_LOCKFILE_TO_NATIVE_EVENT = {
    "cursor": {
        "PreToolUse": "preToolUse",
        "PostToolUse": "postToolUse",
        "SessionStart": "sessionStart",
        "Stop": "stop",
    },
}


def is_flat_hook_adapter(adapter_name: str) -> bool:
    return adapter_name in _FLAT_HOOK_ADAPTERS


def lockfile_to_native_event(adapter_name: str, lockfile_event: str) -> str:
    """Translate a lockfile event name to the adapter's native config form.

    Cursor stores PascalCase in the lockfile (PreToolUse) but camelCase in
    `~/.cursor/hooks.json` (preToolUse); every other adapter mirrors
    Claude. Defaults to identity when no mapping is registered.
    """
    return _LOCKFILE_TO_NATIVE_EVENT.get(adapter_name, {}).get(
        lockfile_event, lockfile_event
    )


def parse_native_hook_commands(
    config_path: Path, adapter_name: str
) -> dict[str, list[str]]:
    """Return {event: [command, ...]} from an adapter's native config file.

    Empty dict on missing file or parse failure. Callers treat that as
    "native config absent" rather than a crash; cmd_verify surfaces it as
    a layer-3 gap.
    """
    if not config_path.is_file():
        return {}
    try:
        doc = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, list[str]] = {}
    flat = is_flat_hook_adapter(adapter_name)
    for event, entries in (doc.get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if flat:
                cmd = entry.get("command")
                if isinstance(cmd, str):
                    out.setdefault(event, []).append(cmd)
            else:
                for handler in entry.get("hooks", []) or []:
                    if not isinstance(handler, dict):
                        continue
                    cmd = handler.get("command")
                    if isinstance(cmd, str):
                        out.setdefault(event, []).append(cmd)
    return out


def _last_token_basename(command: str) -> str:
    """Extract the script basename from a native hook command string.

    Accepts every shape an adapter emits:

      "/abs/path/foo.sh"                                  -> "foo.sh"
      "bash .cursor/hooks/foo.sh"                         -> "foo.sh"
      "<translator>.sh /abs/path/.windsurf/hooks/foo.sh"  -> "foo.sh"

    Empty string if the command is malformed (no whitespace tokens).
    """
    tokens = command.strip().split()
    if not tokens:
        return ""
    return Path(tokens[-1]).name


def command_registers(native_command: str, expected_path: str) -> bool:
    """Return True when `native_command`'s hook script matches `expected_path`.

    v0.7 fix: replaces the previous substring `basename in cmd` heuristic
    with an exact basename comparison anchored on the last whitespace
    token. The old form let `lint-guard.sh` match `lint-guard-backup.sh`
    and similar adjacent-path collisions; the new form is precise
    regardless of `bash ` prefix or Cascade translator wrap.

    Comparison rules:
      * Exact-string equality wins (covers user-level absolute paths).
      * Otherwise compare `Path(last_token).name` to `Path(expected).name`.

    Returns False when either side has no token to compare.
    """
    expected_path = expected_path.strip()
    native = native_command.strip()
    if not native or not expected_path:
        return False
    if native == expected_path:
        return True
    native_name = _last_token_basename(native)
    expected_name = Path(expected_path).name
    return bool(native_name) and native_name == expected_name


__all__ = [
    "command_registers",
    "config_paths_for",
    "is_flat_hook_adapter",
    "lockfile_to_native_event",
    "parse_native_hook_commands",
]
