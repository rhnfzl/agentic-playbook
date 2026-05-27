"""Fuzzy path matching via difflib.SequenceMatcher with basename-match bonus."""

from __future__ import annotations
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import time

DEFAULT_IGNORE = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    ".pytest_cache",
}
DEFAULT_FILE_SCAN_CAP = 5000
DEFAULT_TIME_BUDGET_SECONDS = 0.5


@dataclass
class PathCandidate:
    path: Path
    similarity: float


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_candidates(
    target: str,
    workspace_root: Path,
    *,
    limit: int = 5,
    file_scan_cap: int = DEFAULT_FILE_SCAN_CAP,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    ignore_dirs: set[str] | None = None,
) -> list[PathCandidate]:
    target_path = Path(target)
    target_basename = target_path.name
    target_full = target
    ignore = ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE
    start = time.monotonic()
    scored: list[PathCandidate] = []
    scanned = 0
    for path in workspace_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore for part in path.parts):
            continue
        scanned += 1
        if scanned > file_scan_cap or time.monotonic() - start > time_budget_seconds:
            break
        basename_score = _ratio(target_basename, path.name)
        try:
            relative_str = str(path.relative_to(workspace_root))
        except ValueError:
            relative_str = str(path)
        full_score = _ratio(target_full, relative_str)
        combined = max(full_score, basename_score * 0.9 + full_score * 0.1)
        if combined > 0.5:
            scored.append(PathCandidate(path=path, similarity=combined))
    scored.sort(key=lambda c: c.similarity, reverse=True)
    return scored[:limit]
