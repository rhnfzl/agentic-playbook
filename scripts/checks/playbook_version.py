"""Validate VERSION file is canonical and no hardcoded version constant drifts.

Per ADR-0040 (v0.11): the `VERSION` file at the repo root is the single
source of truth for the playbook version. A hardcoded
`PLAYBOOK_VERSION = "..."` Python constant must NOT exist (it drifted
from 0.4.0 to 0.10.0 across multiple release cycles before the v0.11
refactor caught the gap).

This check:
  - Asserts VERSION file exists and contains a well-formed semver string.
  - Asserts `scripts/install.py` does NOT contain a hardcoded
    `PLAYBOOK_VERSION = "X.Y.Z"` (string-literal) line. A function-call
    form (`PLAYBOOK_VERSION = _read_playbook_version()`) is the post-v0.11
    shape and passes.

Per ADR-0040: there is currently no root `pyproject.toml`. Asserting
match against `[project] version` is out of scope (would require
introducing a pyproject.toml file, which is separately tracked).
"""

from __future__ import annotations

import re

from . import CheckContext, CheckResult


name = "playbook-version"

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][\w.]+)?$")
_HARDCODED_CONST_RE = re.compile(
    r'^\s*PLAYBOOK_VERSION\s*=\s*"\d+\.\d+\.\d+',
    re.MULTILINE,
)


def run(ctx: CheckContext) -> CheckResult:
    version_file = ctx.repo_root / "VERSION"
    if not version_file.is_file():
        return CheckResult(
            status="fail",
            summary="VERSION file missing at repo root",
            details=[],
        )

    try:
        content = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return CheckResult(
            status="fail",
            summary=f"VERSION file unreadable: {exc}",
            details=[],
        )

    if not _SEMVER_RE.match(content):
        return CheckResult(
            status="fail",
            summary=f"VERSION file content not semver: {content!r}",
            details=[],
        )

    install_py = ctx.repo_root / "scripts" / "install.py"
    if install_py.is_file():
        try:
            install_text = install_py.read_text(encoding="utf-8")
        except OSError as exc:
            return CheckResult(
                status="fail",
                summary=f"scripts/install.py unreadable: {exc}",
                details=[],
            )
        match = _HARDCODED_CONST_RE.search(install_text)
        if match:
            line_no = install_text.count("\n", 0, match.start()) + 1
            return CheckResult(
                status="fail",
                summary=(
                    "scripts/install.py hardcodes PLAYBOOK_VERSION "
                    "(must read from VERSION file instead)"
                ),
                details=[
                    f"scripts/install.py:{line_no}: {match.group(0).strip()}"
                ],
            )

    return CheckResult(
        status="ok",
        summary=f"VERSION file canonical: {content}",
        details=[],
    )
