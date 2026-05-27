"""Workspace-root resolution and containment check. Symlinks resolved before comparison."""

from __future__ import annotations
from pathlib import Path

ROOT_MARKERS = (".git", "pyproject.toml", "package.json", ".hg", ".svn")


def is_within_root(candidate: Path, root: Path) -> bool:
    try:
        real_candidate = Path(candidate).resolve()
        real_root = Path(root).resolve()
        real_candidate.relative_to(real_root)
        return True
    except (ValueError, OSError):
        return False


def resolve_root(start: Path) -> Path:
    current = Path(start).resolve()
    while current != current.parent:
        for marker in ROOT_MARKERS:
            if (current / marker).exists():
                return current
        current = current.parent
    return Path(start).resolve()
