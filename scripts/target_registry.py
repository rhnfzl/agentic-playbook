"""Multi-target registry (per ADR-0038).

A machine running the coding-agents-playbook against multiple project
targets ends up with one `.playbook-config.yaml` per target, but no way
to ask "which projects do I have this installed in?" at the playbook
root. This module owns a machine-wide registry at
`~/.coding-agents-playbook-targets.json` that records every successful
playbook_init.py + playbook_update.py run.

Schema (versioned so a future widen is non-breaking):

  {
    "version": 1,
    "targets": {
      "<absolute project path>": {
        "profile": "backend-developer",
        "install_mode": "symlink",
        "registered_at": "2026-05-25T16:00:00+00:00",
        "last_updated_at": "2026-05-25T16:00:00+00:00"
      },
      ...
    }
  }

Path keys are absolute, resolved, and stable per target. A target that
disappears (the project dir was deleted) is left in the registry until
the next prune_missing_targets() call so the user can investigate the
drift instead of having entries silently vanish.

The registry is best-effort:

  * load_registry() returns an empty registry on missing or malformed
    file instead of raising. The downstream commands tolerate a missing
    registry gracefully (most installs are still single-target).
  * save_registry() writes atomically via a rename so a crashed write
    cannot leave a half-formed JSON file behind.
  * Locking is intentionally not implemented. Concurrent installs
    against different targets on the same machine are not a v0.8
    requirement; if multi-process safety becomes load-bearing, file-
    locking via the existing fcntl/msvcrt scaffold in install.py is
    the natural follow-up.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path.home() / ".coding-agents-playbook-targets.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TargetRecord:
    path: Path
    profile: str
    install_mode: str
    registered_at: str
    last_updated_at: str


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_target(target: Path) -> str:
    return str(target.expanduser().resolve())


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Read the registry. Returns an empty dict on missing/corrupt file."""
    if path is None:
        path = REGISTRY_PATH
    if not path.is_file():
        return {"version": SCHEMA_VERSION, "targets": {}}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"version": SCHEMA_VERSION, "targets": {}}
    if not text.strip():
        return {"version": SCHEMA_VERSION, "targets": {}}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"version": SCHEMA_VERSION, "targets": {}}
    if not isinstance(data, dict):
        return {"version": SCHEMA_VERSION, "targets": {}}
    data.setdefault("version", SCHEMA_VERSION)
    if not isinstance(data.get("targets"), dict):
        data["targets"] = {}
    return data


def save_registry(registry: dict[str, Any], *, path: Path | None = None) -> None:
    """Atomic write via temp + rename so partial writes can't corrupt."""
    if path is None:
        path = REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def record_target(
    target: Path,
    *,
    profile: str,
    install_mode: str,
    path: Path | None = None,
) -> None:
    """Insert or update a target entry. registered_at is preserved across
    updates; last_updated_at gets refreshed every call.
    """
    registry = load_registry(path)
    key = _normalize_target(target)
    now = _utcnow_iso()
    existing = registry["targets"].get(key, {})
    registered_at = existing.get("registered_at", now)
    registry["targets"][key] = {
        "profile": profile,
        "install_mode": install_mode,
        "registered_at": registered_at,
        "last_updated_at": now,
    }
    save_registry(registry, path=path)


def forget_target(target: Path, *, path: Path | None = None) -> bool:
    """Remove a target entry. Returns True iff an entry was removed."""
    registry = load_registry(path)
    key = _normalize_target(target)
    if key not in registry["targets"]:
        return False
    del registry["targets"][key]
    save_registry(registry, path=path)
    return True


def list_targets(*, path: Path | None = None) -> list[TargetRecord]:
    """Return every recorded target, sorted by absolute path."""
    registry = load_registry(path)
    records: list[TargetRecord] = []
    for key in sorted(registry["targets"].keys()):
        entry = registry["targets"][key]
        records.append(
            TargetRecord(
                path=Path(key),
                profile=entry.get("profile", ""),
                install_mode=entry.get("install_mode", ""),
                registered_at=entry.get("registered_at", ""),
                last_updated_at=entry.get("last_updated_at", ""),
            )
        )
    return records


def prune_missing_targets(*, path: Path | None = None) -> list[Path]:
    """Drop registry entries that point at a directory that no longer
    exists on disk. Returns the list of paths pruned so the caller can
    surface them.
    """
    registry = load_registry(path)
    pruned: list[Path] = []
    for key in list(registry["targets"]):
        candidate = Path(key)
        if not candidate.is_dir():
            del registry["targets"][key]
            pruned.append(candidate)
    if pruned:
        save_registry(registry, path=path)
    return pruned


def cmd_targets_list() -> int:
    """`make targets-list` entry point: print the registry as a table."""
    records = list_targets()
    if not records:
        print(
            "No targets registered. Run `make init TARGET=/path` from this "
            "playbook to register one."
        )
        return 0
    print(f"{'TARGET':<60} {'PROFILE':<22} {'MODE':<8} LAST UPDATED")
    for rec in records:
        path_str = str(rec.path)
        if len(path_str) > 58:
            path_str = "..." + path_str[-55:]
        print(
            f"{path_str:<60} {rec.profile:<22} {rec.install_mode:<8} "
            f"{rec.last_updated_at}"
        )
    return 0


def cmd_targets_doctor(*, prune: bool = False) -> int:
    """`make targets-doctor` entry point: report the registry state plus
    any directories that look missing. The full doctor-verify pass per
    target is intentionally NOT run inline here; the recommended flow
    is `make targets-list` + a per-target `python3 scripts/install.py
    --verify --target <path>` because each verify needs HOME redirected
    differently and the user typically wants to interleave with their
    own debugging.

    v0.8 Codex adversarial fix: default mode is REPORT-ONLY. A
    temporarily unmounted workspace, permission issue, or transient
    path problem must not silently drop the target's metadata. Users
    who actually want to prune entries pass `--prune` (wired through
    Makefile via the env). The default mode prints each missing entry
    with a clear marker so the user can review before destruction.
    """
    if prune:
        pruned = prune_missing_targets()
    else:
        pruned = []
    records = list_targets()

    if pruned:
        print(f"Pruned {len(pruned)} stale target(s) (directory not found):")
        for p in pruned:
            print(f"  - {p}")
        print()

    if not records:
        if not pruned:
            print("No targets registered.")
        return 0

    print(f"{len(records)} target(s) registered:")
    missing: list[Path] = []
    for rec in records:
        is_dir = rec.path.is_dir()
        marker = "ok" if is_dir else "MISSING"
        if not is_dir:
            missing.append(rec.path)
        config = rec.path / ".playbook-config.yaml"
        config_marker = "config" if config.is_file() else "no-config"
        print(
            f"  [{marker:<7}] {rec.path}  ({rec.profile}, "
            f"{rec.install_mode}, {config_marker})"
        )

    if missing and not prune:
        print()
        print(
            f"{len(missing)} target(s) above are MISSING on disk. To remove "
            f"them from the registry, re-run with `make targets-doctor "
            f"PRUNE=1` (destructive). Until then they stay in the registry "
            f"so a temporarily-unmounted workspace is not silently dropped."
        )
    return 0


__all__ = [
    "REGISTRY_PATH",
    "SCHEMA_VERSION",
    "TargetRecord",
    "cmd_targets_doctor",
    "cmd_targets_list",
    "forget_target",
    "list_targets",
    "load_registry",
    "prune_missing_targets",
    "record_target",
    "save_registry",
]
