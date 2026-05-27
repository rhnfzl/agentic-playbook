"""Skill size budget check (delegates to scripts/size_check.py)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main("size_check", summary="skill size budget")
