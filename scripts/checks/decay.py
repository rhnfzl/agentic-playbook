"""Skill last_reviewed decay check (delegates to scripts/decay_check.py)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main("decay_check", summary="skill last_reviewed decay")
