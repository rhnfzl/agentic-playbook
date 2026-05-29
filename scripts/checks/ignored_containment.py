"""Scan the working tree (including gitignored files) for containment leaks.

This check exists to catch a class of leak that tracked-file greps
(`git ls-files | xargs grep`) miss: a stale row in a gitignored file
(such as a generated index, a local cache, or any path under
docs/human-html/) that references content the team intends to keep
outside the repo dir entirely. The path's mere presence on disk is the
leak surface, not whether git tracks it.

The check is driven by an external configuration file. The path comes
from `$PLAYBOOK_CONTAINMENT_TERMS`. The file is NEVER committed to the
repo; listing the term patterns inside the audit surface would defeat
the purpose.

Schema (TOML):

    terms = ["pattern-1", "pattern-2", ...]
    exclude_dirs = [".git", ".claude/worktrees"]

Behavior:
  - `$PLAYBOOK_CONTAINMENT_TERMS` unset, no strict flag: WARN with
    instructions for how to enable. Does not fail CI; contributors
    who do not need this safety net stay unburdened.
  - `$PLAYBOOK_CONTAINMENT_STRICT=1` + env var unset: FAIL.
  - Env var set + file missing or unreadable: FAIL.
  - Config valid + match found: FAIL with file:line:content details.
  - Config valid + no match: OK.

Matching is case-insensitive. Each term is a regex; invalid regexes
fail at compile time with a clear message.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from . import CheckContext, CheckResult


name = "ignored-containment"

_DEFAULT_EXCLUDES = [".git", ".claude/worktrees"]
_MAX_DETAILS = 50


def _is_excluded(rel_path: Path, excludes: list[str]) -> bool:
    """True if `rel_path` (relative to repo_root) matches any exclude entry.

    An exclude matches when the relative path equals it exactly or starts
    with it followed by a separator. This makes ".git" prune the .git
    directory tree, and ".claude/worktrees" prune that specific subtree
    without touching ".claude" itself.
    """
    rel_str = str(rel_path)
    return any(rel_str == exc or rel_str.startswith(exc + "/") for exc in excludes)


def _scan(
    repo_root: Path,
    patterns: list[re.Pattern[str]],
    excludes: list[str],
) -> list[str]:
    """Walk repo_root, return up to _MAX_DETAILS file:line: content findings."""
    findings: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        try:
            rel_dir = Path(dirpath).relative_to(repo_root)
        except ValueError:
            continue
        dirnames[:] = [
            d for d in sorted(dirnames) if not _is_excluded(rel_dir / d, excludes)
        ]
        for fname in sorted(filenames):
            path = Path(dirpath) / fname
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pat in patterns:
                    if pat.search(line):
                        rel = path.relative_to(repo_root)
                        snippet = line.strip()[:120]
                        findings.append(f"{rel}:{lineno}: {snippet!r}")
                        if len(findings) >= _MAX_DETAILS:
                            return findings
                        break
    return findings


def _load_config(config_path: Path) -> tuple[list[str], list[str]]:
    """Load terms + exclude_dirs from the external TOML file."""
    with config_path.open("rb") as f:
        data = tomllib.load(f)
    terms_raw = data.get("terms", [])
    if not isinstance(terms_raw, list) or not all(
        isinstance(t, str) for t in terms_raw
    ):
        raise ValueError("'terms' must be a list of strings")
    excludes_raw = data.get("exclude_dirs", _DEFAULT_EXCLUDES)
    if not isinstance(excludes_raw, list) or not all(
        isinstance(e, str) for e in excludes_raw
    ):
        raise ValueError("'exclude_dirs' must be a list of strings")
    return terms_raw, excludes_raw


def run(ctx: CheckContext) -> CheckResult:
    config_env = os.environ.get("PLAYBOOK_CONTAINMENT_TERMS")
    strict = os.environ.get("PLAYBOOK_CONTAINMENT_STRICT") == "1"

    if not config_env:
        if strict:
            return CheckResult(
                status="fail",
                summary=(
                    "PLAYBOOK_CONTAINMENT_TERMS not set "
                    "(PLAYBOOK_CONTAINMENT_STRICT=1 forces fail)"
                ),
                details=[],
            )
        return CheckResult(
            status="warn",
            summary=(
                "containment check unconfigured; set "
                "$PLAYBOOK_CONTAINMENT_TERMS to a TOML file path to enable"
            ),
            details=[],
        )

    config_path = Path(config_env).expanduser()
    if not config_path.is_file():
        return CheckResult(
            status="fail",
            summary=(
                f"PLAYBOOK_CONTAINMENT_TERMS points at non-existent file: {config_path}"
            ),
            details=[],
        )

    try:
        terms, excludes = _load_config(config_path)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return CheckResult(
            status="fail",
            summary=f"failed to parse {config_path}: {exc}",
            details=[],
        )

    if not terms:
        return CheckResult(
            status="warn",
            summary=f"{config_path} has empty terms list; nothing to scan",
            details=[],
        )

    try:
        patterns = [re.compile(t, re.IGNORECASE) for t in terms]
    except re.error as exc:
        return CheckResult(
            status="fail",
            summary=f"invalid regex in {config_path}: {exc}",
            details=[],
        )

    findings = _scan(ctx.repo_root, patterns, excludes)

    if findings:
        return CheckResult(
            status="fail",
            summary=f"{len(findings)} containment leak(s) found",
            details=findings,
        )

    return CheckResult(
        status="ok",
        summary=f"no containment leaks ({len(terms)} term(s) scanned)",
        details=[],
    )
