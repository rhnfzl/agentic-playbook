"""Check `.human-html-allowlist` files for syntactic validity.

The human-html skill (skills/meta/human-html/) ships an advisory hook
that reads `.human-html-allowlist` at the workspace root. Each non-empty,
non-comment line is a shell glob carving extra paths out of the baseline
allowlist. The hook is forgiving (a bad glob causes a benign miss, not
a crash), but a typo or accidentally-pasted snippet of shell can sit
there for months without a workflow noticing.

This check validates every `.human-html-allowlist` it finds in the
playbook tree (today: zero; the check is forward-looking infrastructure)
and reports two failure modes:

  fail: the line contains characters that would enable command
        substitution if a future hook author mis-quoted the read loop.
        Specifically `$(`, backtick, `||`, `&&`, and `; ` are flagged.
        The current hook uses `case ... esac` which is glob-safe, but
        the rule errs on the conservative side so a future rewrite
        cannot regress.

  warn: the line ends in `\\` (continuation chars don't combine across
        lines in the read loop) or contains `..` (path traversal-ish
        patterns), since both are usually drift.

A malformed file does not fail loudly today (the hook silently misses);
this check makes the malformed line visible at `make check` time.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import CheckContext, CheckResult


_DANGEROUS_RE = re.compile(r"\$\(|`|\|\||&&|;\s")
# v0.8 Codex review fix: match a SINGLE trailing backslash, not two.
# The previous pattern `\\\\$` was raw-string-encoded as `\\$` which
# requires two literal backslashes at end of string; the docstring says
# we warn on continuation characters which are one trailing backslash.
_WARN_RE = re.compile(r"\\$|\.\.")


name = "human-html-allowlist"


def _find_allowlists(repo_root: Path) -> list[Path]:
    """Walk the playbook for .human-html-allowlist files. Skips vendored
    skill imports and tooling caches; if a real workspace ever ends up
    nested under the playbook this check still scans it."""
    skip_parts = {".git", ".venv", "__pycache__", "node_modules", "skills-archived"}
    found: list[Path] = []
    for path in repo_root.rglob(".human-html-allowlist"):
        if any(part in skip_parts for part in path.parts):
            continue
        found.append(path)
    return found


def _classify_line(line: str) -> str:
    """Return 'ok' / 'warn' / 'fail' for one allowlist line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return "ok"
    if _DANGEROUS_RE.search(stripped):
        return "fail"
    if _WARN_RE.search(stripped):
        return "warn"
    return "ok"


def run(ctx: CheckContext) -> CheckResult:
    allowlists = _find_allowlists(ctx.repo_root)
    if not allowlists:
        return CheckResult(
            status="ok",
            summary="no .human-html-allowlist files in scope",
            details=[],
        )

    issues: list[str] = []
    has_fail = False
    has_warn = False
    scanned_lines = 0

    for allowlist in allowlists:
        try:
            text = allowlist.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"{allowlist}: could not read ({exc})")
            has_fail = True
            continue
        for idx, raw_line in enumerate(text.splitlines(), start=1):
            scanned_lines += 1
            verdict = _classify_line(raw_line)
            if verdict == "ok":
                continue
            tag = "FAIL" if verdict == "fail" else "WARN"
            issues.append(
                f"{allowlist}:{idx}: {tag}: {raw_line.strip()[:120]!r}"
            )
            if verdict == "fail":
                has_fail = True
            else:
                has_warn = True

    status = "fail" if has_fail else ("warn" if has_warn else "ok")
    summary = (
        f"scanned {scanned_lines} line(s) in "
        f"{len(allowlists)} .human-html-allowlist file(s)"
    )
    return CheckResult(status=status, summary=summary, details=issues)
