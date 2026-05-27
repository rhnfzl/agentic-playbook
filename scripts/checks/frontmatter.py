"""SKILL.md frontmatter lint (delegates to scripts/frontmatter_lint.py)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main("frontmatter_lint", summary="frontmatter lint")
